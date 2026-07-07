"""Response Agent — generates draft replies using OpenAI LLM with historical context."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import List, Optional

from openai import AsyncOpenAI

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
    """Generates draft email replies using OpenAI LLM with historical tone context."""

    def __init__(
        self,
        vector_store: VectorStoreService,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 15,
    ) -> None:
        settings = get_settings()
        self._vector_store = vector_store
        self._api_key = api_key or settings.openai_api_key
        self._model_name = model or settings.openai_model
        self._timeout = timeout

        self._client = AsyncOpenAI(api_key=self._api_key)

    async def generate_reply(
        self, email: RawEmail, classification: ClassificationResult
    ) -> DraftReply:
        """Generate a draft reply within the configured timeout.

        Args:
            email: The incoming email to reply to.
            classification: Classification result for context.

        Returns:
            DraftReply with reply_body, suggested_subject, and referenced_email_ids.

        Raises:
            ResponseTimeoutError: If generation exceeds timeout.
            ResponseGenerationError: If the LLM service is unavailable.
        """
        try:
            return await asyncio.wait_for(
                self._generate(email, classification),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            raise ResponseTimeoutError(
                f"Response generation timed out after {self._timeout}s"
            )

    async def _generate(
        self, email: RawEmail, classification: ClassificationResult
    ) -> DraftReply:
        """Internal generation logic."""
        history = self.retrieve_context(email)
        prompt = self.build_response_prompt(email, history)

        try:
            raw_output = await self._call_openai(prompt)
        except Exception as exc:
            raise ResponseGenerationError(
                f"LLM service unavailable: {exc}"
            ) from exc

        referenced_ids = [r.email_id for r in history]
        return self.validate_draft(raw_output, email.subject, referenced_ids)

    def retrieve_context(self, email: RawEmail, k: int = 5) -> List[SearchResult]:
        """Query vector store for similar past emails.

        Args:
            email: The incoming email to find context for.
            k: Number of similar results to retrieve.

        Returns:
            List of SearchResult with similarity >= threshold.
        """
        query_text = f"{email.subject} {email.body[:1000]}"
        results = self._vector_store.search_similar(query_text=query_text, k=k)

        # Filter out results below similarity threshold
        relevant = [r for r in results if r.similarity_score >= SIMILARITY_THRESHOLD]
        return relevant

    def build_response_prompt(
        self, email: RawEmail, history: List[SearchResult]
    ) -> str:
        """Construct prompt with current email + historical tone context.

        Args:
            email: The incoming email to reply to.
            history: Similar past emails for tone reference.

        Returns:
            Complete prompt string for the LLM.
        """
        tone_section = self._build_tone_section(history)

        return f"""You are an email reply assistant. Generate a professional reply to the following email.

Rules:
- Reply body must be at most 500 words
- Suggested subject must be at most 150 characters
- Match the tone and style from historical email context if provided
- If no historical context is provided, use a neutral professional tone
- Be concise and address the email content directly

{tone_section}

Current email to reply to:
- From: {email.sender}
- Subject: {email.subject}
- Body: {email.body[:3000]}

Generate a reply with:
1. reply_body: The body text of the reply (max 500 words)
2. suggested_subject: A subject line for the reply (max 150 characters, typically "Re: <original subject>")

Return ONLY the reply in the following format:
SUBJECT: <suggested subject>
BODY:
<reply body text>"""

    def validate_draft(
        self, draft_text: str, subject: str, referenced_ids: List[str]
    ) -> DraftReply:
        """Parse and enforce constraints on draft reply.

        Args:
            draft_text: Raw LLM output text.
            subject: Original email subject for fallback.
            referenced_ids: IDs of referenced historical emails.

        Returns:
            Validated DraftReply model.
        """
        suggested_subject, reply_body = self._parse_draft_output(draft_text, subject)

        # Enforce max 150 chars on subject
        if len(suggested_subject) > 150:
            suggested_subject = suggested_subject[:150]

        # Enforce max 500 words on body
        words = reply_body.split()
        if len(words) > 500:
            reply_body = " ".join(words[:500])

        return DraftReply(
            reply_body=reply_body,
            suggested_subject=suggested_subject,
            referenced_email_ids=referenced_ids,
            status=DraftStatus.PENDING,
            generated_at=datetime.utcnow(),
        )

    def _build_tone_section(self, history: List[SearchResult]) -> str:
        """Build the historical tone context section of the prompt."""
        if not history:
            return "No historical email context available. Use a neutral professional tone."

        tone_examples = []
        for i, result in enumerate(history[:3], 1):
            snippet = result.text_snippet or ""
            tone_examples.append(
                f"  Example {i} (similarity: {result.similarity_score:.2f}): {snippet}"
            )

        examples_text = "\n".join(tone_examples)
        return f"""Historical email context (match tone and style):
{examples_text}"""

    def _parse_draft_output(self, raw_output: str, fallback_subject: str) -> tuple:
        """Parse LLM output into subject and body."""
        suggested_subject = f"Re: {fallback_subject}"
        reply_body = raw_output.strip()

        lines = raw_output.strip().split("\n")

        # Try to parse structured output
        body_start_idx = 0
        for i, line in enumerate(lines):
            if line.strip().upper().startswith("SUBJECT:"):
                suggested_subject = line.split(":", 1)[1].strip()
            elif line.strip().upper().startswith("BODY:"):
                body_start_idx = i + 1
                break

        if body_start_idx > 0:
            reply_body = "\n".join(lines[body_start_idx:]).strip()

        # If we couldn't parse, use the entire output as body
        if not reply_body:
            reply_body = raw_output.strip()

        return suggested_subject, reply_body

    async def _call_openai(self, prompt: str) -> str:
        """Call OpenAI API and return raw text response."""
        response = await self._client.chat.completions.create(
            model=self._model_name,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content or ""
