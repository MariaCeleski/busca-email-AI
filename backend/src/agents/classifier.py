"""Classifier Agent — classifies emails using Google Gemini LLM."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

import google.generativeai as genai

from src.config import get_settings
from src.models.classification import ClassificationResult
from src.models.email import RawEmail
from src.models.enums import EmailCategory, PriorityLevel

logger = logging.getLogger(__name__)


class ClassificationError(Exception):
    """Raised when email classification fails (timeout, invalid response, etc.)."""


class ClassifierAgent:
    """Classifies emails into categories and priorities using Google Gemini LLM."""

    # Categories that require a response draft
    _RESPONSE_CATEGORIES = {EmailCategory.URGENT, EmailCategory.PERSONAL}
    # Priorities that qualify for response generation
    _RESPONSE_PRIORITIES = {PriorityLevel.HIGH, PriorityLevel.MEDIUM}
    # Categories that qualify for summarization
    _SUMMARY_CATEGORIES = {EmailCategory.URGENT, EmailCategory.INFORMATIVE}
    # Word count threshold for summarization
    _SUMMARY_WORD_THRESHOLD = 200

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 10,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key or settings.gemini_api_key
        self._model_name = model or settings.gemini_model
        self._timeout = timeout

        # Configure the Gemini SDK
        genai.configure(api_key=self._api_key)
        self._model = genai.GenerativeModel(self._model_name)

    async def classify(self, email: RawEmail) -> ClassificationResult:
        """Analyze email and return classification within 10s timeout.

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
                self._call_gemini(prompt),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            raise ClassificationError(
                f"Classification timed out after {self._timeout}s"
            )
        except ClassificationError:
            raise
        except Exception as exc:
            raise ClassificationError(f"Gemini API call failed: {exc}") from exc

        return self.validate_result(raw_output, email)

    def build_classification_prompt(self, email: RawEmail) -> str:
        """Construct the structured classification prompt for Gemini."""
        return f"""You are an email classification assistant. Analyze the following email and classify it.

Return ONLY a valid JSON object with these exact fields:
- "category": exactly one of "Urgent", "Informative", "Promotional", "Spam", "Transactional", "Personal"
- "priority": exactly one of "High", "Medium", "Low"
- "confidence": a float between 0.0 and 1.0 indicating how confident you are in the classification

Classification guidelines:
- "Urgent": Time-sensitive emails requiring immediate attention (deadlines, emergencies, critical requests)
- "Informative": News, updates, reports, or FYI messages that don't need a reply
- "Promotional": Marketing emails, offers, newsletters from businesses
- "Spam": Unwanted, unsolicited, or suspicious emails
- "Transactional": Order confirmations, receipts, shipping notifications, account alerts
- "Personal": Personal messages from individuals requiring a personal reply

Priority guidelines:
- "High": Requires immediate attention or action
- "Medium": Important but not time-critical
- "Low": Can be addressed later or is purely informational

Email details:
- From: {email.sender}
- Subject: {email.subject}
- Body: {email.body[:2000]}

Respond with ONLY the JSON object, no additional text or formatting."""

    def validate_result(self, raw_output: str, email: Optional[RawEmail] = None) -> ClassificationResult:
        """Parse and validate LLM output against ClassificationResult schema.

        Computes requires_response, requires_summary, and flagged_for_review
        based on the classification results and email content.

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
        except (KeyError, ValueError) as exc:
            raise ClassificationError(
                f"Missing or invalid field in LLM response: {exc}"
            ) from exc

        # Clamp confidence to valid range
        confidence = max(0.0, min(1.0, confidence))

        # Compute derived fields based on classification logic
        requires_response = (
            category in self._RESPONSE_CATEGORIES
            and priority in self._RESPONSE_PRIORITIES
        )

        # Compute requires_summary based on category and word count
        word_count = 0
        if email is not None:
            word_count = len(email.body.split())
        requires_summary = (
            category in self._SUMMARY_CATEGORIES
            and word_count > self._SUMMARY_WORD_THRESHOLD
        )

        flagged_for_review = confidence < 0.6

        return ClassificationResult(
            category=category,
            priority=priority,
            confidence=confidence,
            requires_response=requires_response,
            requires_summary=requires_summary,
            flagged_for_review=flagged_for_review,
        )

    async def _call_gemini(self, prompt: str) -> str:
        """Call Gemini API and return raw text response."""
        response = await self._model.generate_content_async(prompt)

        if response.text is None:
            raise ClassificationError("Gemini returned empty response")

        return response.text
