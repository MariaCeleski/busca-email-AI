"""Response Agent — generates draft replies using Google Gemini with historical context.

Uses gemini-2.0-flash for generation and VectorStoreService for semantic search
of historical emails to match tone and style.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime
from typing import List, Optional

import google.generativeai as genai

from src.config import get_settings
from src.models.classification import ClassificationResult
from src.models.draft import DraftReply
from src.models.email import RawEmail
from src.models.enums import DraftStatus
from src.models.vector_store import SearchResult
from src.services.vector_store import VectorStoreService

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.3


class ResponseTimeoutError(Exception):
    """Raised when response generation exceeds the timeout."""


class ResponseGenerationError(Exception):
    """Raised when the LLM service is unavailable or fails."""


class ResponseAgent:
    """Generates draft email replies using Google Gemini with historical tone context.

    Implements semantic search for top-5 similar past emails, tone matching from
    historical emails, 15-second timeout, and output constraint enforcement.
    """

    def __init__(
        self,
        vector_store: VectorStoreService,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> None:
        settings = get_settings()
        self._vector_store = vector_store
        self._api_key = api_key or settings.gemini_api_key
        self._model_name = model or settings.gemini_model
        self._timeout = timeout if timeout is not None else settings.response_timeout_seconds

        # Configure Gemini API
        genai.configure(api_key=self._api_key)
        self._model = genai.GenerativeModel(self._model_name)

    async def generate_reply(
        self, email: RawEmail, classification: ClassificationResult
    ) -> DraftReply:
        """Generate a draft reply within the configured timeout (15s default).

        Retrieves historical context via semantic search, builds a tone-aware prompt,
        generates a reply via Gemini, and validates output constraints.

        Args:
            email: The incoming email to reply to.
            classification: Classification result for context.

        Returns:
            DraftReply with reply_body, suggested_subject, and referenced_email_ids.

        Raises:
            ResponseTimeoutError: If generation exceeds timeout — partial draft is discarded.
            ResponseGenerationError: If the LLM service is unavailable.
        """
        try:
            return await asyncio.wait_for(
                self._generate(email, classification),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            logger.error(
                "Response generation timed out after %ds for email %s",
                self._timeout,
                email.provider_message_id,
            )
            raise ResponseTimeoutError(
                f"Response generation timed out after {self._timeout}s"
            )

    async def _generate(
        self, email: RawEmail, classification: ClassificationResult
    ) -> DraftReply:
        """Internal generation logic."""
        # Retrieve historical context via semantic search
        history = await self.retrieve_context(email)

        # Build prompt with tone context
        prompt = self.build_response_prompt(email, history)

        # Call Gemini for generation
        try:
            raw_output = await self._call_gemini(prompt)
        except Exception as exc:
            raise ResponseGenerationError(
                f"LLM service unavailable: {exc}"
            ) from exc

        # Collect referenced email IDs from history
        referenced_ids = [r.email_id for r in history]

        # Parse LLM output, enforce constraints, and build DraftReply
        return self._build_validated_draft(raw_output, email.subject, referenced_ids)

    async def retrieve_context(self, email: RawEmail, k: int = 5) -> List[SearchResult]:
        """Query vector store for the top-k semantically similar past emails.

        Filters results by SIMILARITY_THRESHOLD (0.3). Results with similarity
        below this threshold are excluded.

        Args:
            email: The incoming email to find context for.
            k: Number of similar results to retrieve (default 5).

        Returns:
            List of SearchResult with similarity >= 0.3, or empty list if none qualify.
        """
        query_text = f"{email.subject} {email.body[:1000]}"
        results = await self._vector_store.search_similar(query_text=query_text, k=k)

        # Filter out results below similarity threshold
        relevant = [r for r in results if r.similarity_score >= SIMILARITY_THRESHOLD]
        return relevant

    def build_response_prompt(
        self, email: RawEmail, history: List[SearchResult]
    ) -> str:
        """Construct prompt with current email + historical tone context.

        When history is available (similarity >= 0.3): analyzes tone patterns
        including greeting style, sign-off style, sentence structure, and
        average sentence length from retrieved historical emails.

        When no history is available (all similarity < 0.3): instructs the LLM
        to use a neutral professional tone.

        Args:
            email: The incoming email to reply to.
            history: Similar past emails for tone reference.

        Returns:
            Complete prompt string requesting JSON output.
        """
        tone_section = self._build_tone_section(history)

        return f"""You are an email reply assistant. Generate a professional reply to the following email.

{tone_section}

Current email to reply to:
- From: {email.sender}
- Subject: {email.subject}
- Body: {email.body[:3000]}

Instructions:
- The reply body must be at most 500 words.
- The suggested subject must be at most 150 characters.
- Incorporate the sender's name, subject line, and key statements from the email.
- Address the email content directly and be concise.

Return your response as a valid JSON object with exactly these fields:
{{
  "reply_body": "<the body text of the reply>",
  "suggested_subject": "<a subject line for the reply>"
}}

Respond ONLY with the JSON object, no additional text."""

    def validate_draft(self, draft: DraftReply) -> DraftReply:
        """Enforce output constraints: max 500 words body, max 150 chars subject.

        Truncates reply_body to 500 words and suggested_subject to 150 characters
        if they exceed the limits.

        Args:
            draft: The DraftReply to validate.

        Returns:
            DraftReply with enforced constraints.
        """
        reply_body = draft.reply_body
        suggested_subject = draft.suggested_subject
        needs_rebuild = False

        # Enforce max 150 chars on subject
        if len(suggested_subject) > 150:
            suggested_subject = suggested_subject[:150]
            needs_rebuild = True

        # Enforce max 500 words on body
        words = reply_body.split()
        if len(words) > 500:
            reply_body = " ".join(words[:500])
            needs_rebuild = True

        if not needs_rebuild:
            return draft

        return DraftReply(
            reply_body=reply_body,
            suggested_subject=suggested_subject,
            referenced_email_ids=draft.referenced_email_ids,
            status=draft.status,
            generated_at=draft.generated_at,
        )

    def _build_validated_draft(
        self, raw_output: str, fallback_subject: str, referenced_ids: List[str]
    ) -> DraftReply:
        """Parse LLM output, enforce constraints, and build a valid DraftReply.

        Handles truncation before creating the Pydantic model to avoid validation errors.
        """
        reply_body, suggested_subject = self._extract_reply_fields(
            raw_output, fallback_subject
        )

        # Enforce max 150 chars on subject before model creation
        if len(suggested_subject) > 150:
            suggested_subject = suggested_subject[:150]

        # Enforce max 500 words on body before model creation
        words = reply_body.split()
        if len(words) > 500:
            reply_body = " ".join(words[:500])

        # Enforce max_length=2500 chars (Pydantic field constraint)
        if len(reply_body) > 2500:
            reply_body = reply_body[:2500]

        return DraftReply(
            reply_body=reply_body,
            suggested_subject=suggested_subject,
            referenced_email_ids=referenced_ids,
            status=DraftStatus.PENDING,
            generated_at=datetime.utcnow(),
        )

    def _build_tone_section(self, history: List[SearchResult]) -> str:
        """Build the historical tone context section of the prompt.

        When history is present, analyzes tone patterns including:
        - Greeting style (e.g., "Hi", "Dear", "Hello")
        - Sign-off style (e.g., "Best regards", "Thanks", "Cheers")
        - Average sentence length
        - Sentence structure patterns
        """
        if not history:
            return "Tone guidance: No historical email context available. Use a neutral professional tone."

        # Analyze tone patterns from historical emails
        greetings = []
        sign_offs = []
        sentence_lengths = []
        tone_examples = []

        for result in history:
            snippet = result.text_snippet or ""
            if not snippet:
                continue

            tone_examples.append(snippet)

            # Extract greeting style (first line patterns)
            lines = snippet.strip().split("\n")
            first_line = lines[0].strip() if lines else ""
            if any(g in first_line.lower() for g in ["hi", "hello", "dear", "hey", "good morning", "good afternoon"]):
                greetings.append(first_line)

            # Extract sign-off style (last lines patterns)
            last_line = lines[-1].strip() if lines else ""
            if any(s in last_line.lower() for s in ["regards", "thanks", "cheers", "best", "sincerely", "take care"]):
                sign_offs.append(last_line)

            # Calculate sentence lengths
            sentences = re.split(r'[.!?]+', snippet)
            for sent in sentences:
                words = sent.strip().split()
                if words:
                    sentence_lengths.append(len(words))

        # Build tone analysis summary
        avg_sentence_length = (
            sum(sentence_lengths) / len(sentence_lengths) if sentence_lengths else 15
        )

        greeting_style = greetings[0] if greetings else "Professional greeting"
        sign_off_style = sign_offs[0] if sign_offs else "Professional sign-off"

        examples_text = "\n".join(
            f"  Example {i+1} (similarity: {h.similarity_score:.2f}): {h.text_snippet}"
            for i, h in enumerate(history[:5])
            if h.text_snippet
        )

        return f"""Tone guidance from historical emails (match this style):
- Greeting style: {greeting_style}
- Sign-off style: {sign_off_style}
- Average sentence length: ~{avg_sentence_length:.0f} words per sentence
- Sentence structure: Match the style and rhythm of the examples below

Historical email examples:
{examples_text}

Adopt the sentence structure, greeting style, sign-off style, and average sentence length from these historical emails."""

    def _extract_reply_fields(
        self, raw_output: str, fallback_subject: str
    ) -> tuple:
        """Extract reply_body and suggested_subject from Gemini output.

        Expected JSON format:
        {
            "reply_body": "...",
            "suggested_subject": "..."
        }

        Falls back to structured text parsing or raw output as body.
        """
        reply_body = ""
        suggested_subject = f"Re: {fallback_subject}"

        try:
            # Try to extract JSON from the response (handle markdown code blocks)
            json_text = raw_output.strip()
            if json_text.startswith("```"):
                # Remove markdown code block markers
                json_text = re.sub(r'^```(?:json)?\s*', '', json_text)
                json_text = re.sub(r'\s*```$', '', json_text)

            parsed = json.loads(json_text)
            reply_body = parsed.get("reply_body", "").strip()
            suggested_subject = parsed.get("suggested_subject", suggested_subject).strip()
        except (json.JSONDecodeError, AttributeError):
            # Fallback: try to parse structured text format
            reply_body, suggested_subject = self._fallback_parse(
                raw_output, fallback_subject
            )

        if not reply_body:
            reply_body = raw_output.strip()

        if not suggested_subject:
            suggested_subject = f"Re: {fallback_subject}"

        return reply_body, suggested_subject

    def _fallback_parse(self, raw_output: str, fallback_subject: str) -> tuple:
        """Fallback parsing for non-JSON output."""
        suggested_subject = f"Re: {fallback_subject}"
        reply_body = raw_output.strip()

        lines = raw_output.strip().split("\n")
        body_start_idx = 0

        for i, line in enumerate(lines):
            stripped = line.strip().upper()
            if stripped.startswith("SUBJECT:"):
                suggested_subject = line.split(":", 1)[1].strip()
            elif stripped.startswith("BODY:"):
                body_start_idx = i + 1
                break

        if body_start_idx > 0:
            reply_body = "\n".join(lines[body_start_idx:]).strip()

        if not reply_body:
            reply_body = raw_output.strip()

        return reply_body, suggested_subject

    async def _call_gemini(self, prompt: str) -> str:
        """Call Gemini API and return raw text response.

        Uses asyncio.to_thread to avoid blocking the event loop since
        google-generativeai SDK uses synchronous calls.
        """
        response = await asyncio.to_thread(
            self._model.generate_content, prompt
        )
        return response.text or ""
