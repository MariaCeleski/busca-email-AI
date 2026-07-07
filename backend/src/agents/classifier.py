"""Classifier Agent — classifies emails using OpenAI LLM."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from openai import AsyncOpenAI

from src.config import get_settings
from src.models.classification import ClassificationResult
from src.models.email import RawEmail
from src.models.enums import EmailCategory, PriorityLevel

logger = logging.getLogger(__name__)


class ClassificationError(Exception):
    """Raised when email classification fails (timeout, invalid response, etc.)."""


class ClassifierAgent:
    """Classifies emails into categories and priorities using OpenAI LLM."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 10,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key or settings.openai_api_key
        self._model_name = model or settings.openai_model
        self._timeout = timeout

        self._client = AsyncOpenAI(api_key=self._api_key)

    async def classify(self, email: RawEmail) -> ClassificationResult:
        """Analyze email and return classification within timeout.

        Raises ClassificationError on timeout or invalid response.
        """
        # Handle empty email (empty subject + body)
        if not email.subject.strip() and not email.body.strip():
            return ClassificationResult(
                category=EmailCategory.INFORMATIVE,
                priority=PriorityLevel.LOW,
                confidence=0.0,
                requires_response=False,
                requires_summary=False,
                flagged_for_review=True,
            )

        prompt = self.build_classification_prompt(email)

        try:
            raw_output = await asyncio.wait_for(
                self._call_openai(prompt),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            raise ClassificationError(
                f"Classification timed out after {self._timeout}s"
            )
        except Exception as exc:
            raise ClassificationError(f"OpenAI API call failed: {exc}") from exc

        return self.validate_result(raw_output)

    def build_classification_prompt(self, email: RawEmail) -> str:
        """Construct structured prompt for Gemini classification."""
        return f"""You are an email classification assistant. Analyze the following email and classify it.

Return ONLY valid JSON with the following fields:
- "category": one of "Urgent", "Informative", "Promotional", "Spam", "Transactional", "Personal"
- "priority": one of "High", "Medium", "Low"
- "confidence": a float between 0.0 and 1.0 indicating classification confidence
- "requires_response": boolean, true if the email requires a reply
- "requires_summary": boolean, true if the email is long enough to benefit from summarization

Email details:
- From: {email.sender}
- Subject: {email.subject}
- Body: {email.body[:2000]}

Respond with ONLY the JSON object, no additional text."""

    def validate_result(self, raw_output: str) -> ClassificationResult:
        """Parse and validate LLM output against schema.

        Raises ClassificationError if parsing or validation fails.
        """
        try:
            # Strip markdown code fences if present
            cleaned = raw_output.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                # Remove first and last lines (code fences)
                lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                cleaned = "\n".join(lines)

            data = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ClassificationError(
                f"Invalid JSON in LLM response: {exc}"
            ) from exc

        try:
            category = EmailCategory(data["category"])
            priority = PriorityLevel(data["priority"])
            confidence = float(data["confidence"])
            requires_response = bool(data["requires_response"])
            requires_summary = bool(data["requires_summary"])
        except (KeyError, ValueError) as exc:
            raise ClassificationError(
                f"Missing or invalid field in LLM response: {exc}"
            ) from exc

        # Clamp confidence to valid range
        confidence = max(0.0, min(1.0, confidence))

        flagged_for_review = confidence < 0.6

        return ClassificationResult(
            category=category,
            priority=priority,
            confidence=confidence,
            requires_response=requires_response,
            requires_summary=requires_summary,
            flagged_for_review=flagged_for_review,
        )

    async def _call_openai(self, prompt: str) -> str:
        """Call OpenAI API and return raw text response."""
        response = await self._client.chat.completions.create(
            model=self._model_name,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content or ""
