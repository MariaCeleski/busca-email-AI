"""Summarizer Agent — generates email summaries using OpenAI LLM."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import List, Optional

from openai import AsyncOpenAI

from src.config import get_settings
from src.models.email import RawEmail
from src.models.summary import SummaryResult

logger = logging.getLogger(__name__)


class SummarizerAgent:
    """Summarizes emails and extracts action items using OpenAI LLM."""

    WORD_THRESHOLD = 200

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 8,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key or settings.openai_api_key
        self._model_name = model or settings.openai_model
        self._timeout = timeout

        self._client = AsyncOpenAI(api_key=self._api_key)

    async def summarize(self, email: RawEmail) -> SummaryResult:
        """Generate summary within timeout.

        Returns fallback summary on LLM failure/timeout.
        """
        # No extractable text
        if not email.body.strip():
            return SummaryResult(summary="", no_content=True)

        # Body under threshold — return original body unmodified
        if not self.should_summarize(email):
            return SummaryResult(summary=email.body, action_items=[])

        prompt = self.build_summary_prompt(email)

        try:
            raw_output = await asyncio.wait_for(
                self._call_openai(prompt),
                timeout=self._timeout,
            )
            return self._parse_summary(raw_output)
        except (asyncio.TimeoutError, Exception) as exc:
            logger.warning("Summarization failed, using fallback: %s", exc)
            return self.fallback_summary(email)

    def should_summarize(self, email: RawEmail) -> bool:
        """Check if email body exceeds 200-word threshold."""
        return self._count_words(email.body) >= self.WORD_THRESHOLD

    def build_summary_prompt(self, email: RawEmail) -> str:
        """Construct prompt for summarization and action item extraction."""
        return f"""You are an email summarization assistant. Summarize the following email.

Rules:
- Summary must be at most 3 sentences
- Extract up to 10 action items (things the recipient needs to do)
- If there are no action items, return an empty list

Return ONLY valid JSON with the following fields:
- "summary": string (max 3 sentences)
- "action_items": list of strings (max 10 items)

Email details:
- From: {email.sender}
- Subject: {email.subject}
- Body: {email.body[:3000]}

Respond with ONLY the JSON object, no additional text."""

    def fallback_summary(self, email: RawEmail) -> SummaryResult:
        """Return first 3 sentences as fallback when LLM fails."""
        summary = self._extract_first_sentences(email.body, n=3)
        return SummaryResult(
            summary=summary,
            action_items=[],
            is_fallback=True,
        )

    def _count_words(self, text: str) -> int:
        """Count words in text."""
        return len(text.split())

    def _extract_first_sentences(self, text: str, n: int = 3) -> str:
        """Extract first n sentences from text."""
        # Split on sentence-ending punctuation followed by whitespace
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        selected = sentences[:n]
        return " ".join(selected)

    def _parse_summary(self, raw_output: str) -> SummaryResult:
        """Parse LLM output into SummaryResult."""
        cleaned = raw_output.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)

        data = json.loads(cleaned)

        summary = str(data.get("summary", ""))
        action_items: List[str] = [
            str(item) for item in data.get("action_items", [])
        ]
        # Cap action items at 10
        action_items = action_items[:10]

        return SummaryResult(
            summary=summary,
            action_items=action_items,
        )

    async def _call_openai(self, prompt: str) -> str:
        """Call OpenAI API and return raw text response."""
        response = await self._client.chat.completions.create(
            model=self._model_name,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content or ""
