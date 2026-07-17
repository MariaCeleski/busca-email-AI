# =============================================================================
# Serviço de Aprendizado por Feedback
#
# Objetivo: Usar approve/reject do usuário para melhorar classificação ao longo do tempo.
# Estratégia: Few-shot prompting dinâmico — exemplos de feedback são incluídos
#             no prompt do Classifier para guiar classificações futuras.
# =============================================================================
"""Serviço de aprendizado por feedback — melhora classificação com base em ações do usuário."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

MAX_FEEDBACK_EXAMPLES = 5


class FeedbackLearner:
    """Registra e recupera feedback do usuário para enriquecer prompts dos agentes."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record_feedback(
        self,
        email_subject: str,
        email_body_snippet: str,
        email_sender: str,
        predicted_category: str,
        predicted_priority: str,
        confidence: Optional[float],
        feedback: str,  # "approved" ou "rejected"
        correct_category: Optional[str] = None,
        correct_priority: Optional[str] = None,
    ) -> None:
        """Registra feedback (approve/reject) na tabela classification_feedback."""
        await self._session.execute(
            text("""
                INSERT INTO classification_feedback
                (email_subject, email_body_snippet, email_sender,
                 predicted_category, predicted_priority, confidence,
                 feedback, correct_category, correct_priority, created_at)
                VALUES (:subject, :body, :sender, :cat, :pri, :conf,
                        :feedback, :correct_cat, :correct_pri, :now)
            """),
            {
                "subject": email_subject[:500],
                "body": email_body_snippet[:500],
                "sender": email_sender[:255],
                "cat": predicted_category,
                "pri": predicted_priority,
                "conf": confidence,
                "feedback": feedback,
                "correct_cat": correct_category,
                "correct_pri": correct_priority,
                "now": datetime.utcnow(),
            },
        )
        await self._session.commit()
        logger.info("Feedback '%s' registrado para categoria=%s", feedback, predicted_category)

    async def get_recent_examples(self, limit: int = MAX_FEEDBACK_EXAMPLES) -> List[dict]:
        """Retorna os últimos N exemplos de feedback aprovados para few-shot prompting."""
        result = await self._session.execute(
            text("""
                SELECT email_subject, email_sender, predicted_category, predicted_priority, feedback
                FROM classification_feedback
                ORDER BY created_at DESC
                LIMIT :limit
            """),
            {"limit": limit},
        )
        rows = result.fetchall()
        return [
            {
                "subject": row[0],
                "sender": row[1],
                "category": row[2],
                "priority": row[3],
                "feedback": row[4],
            }
            for row in rows
        ]

    @staticmethod
    def build_few_shot_section(examples: List[dict]) -> str:
        """Constrói seção de few-shot para o prompt do Classifier baseado em feedback real."""
        if not examples:
            return ""

        lines = [
            "\n\nExemplos de classificações anteriores com feedback do usuário:"
        ]
        for i, ex in enumerate(examples, 1):
            status = "✓ aprovada" if ex["feedback"] == "approved" else "✗ rejeitada"
            lines.append(
                f"\n  {i}. Assunto: \"{ex['subject']}\" | De: {ex['sender']}"
                f"\n     Classificação: {ex['category']}/{ex['priority']} — {status}"
            )
        lines.append(
            "\nUse esses exemplos como referência. "
            "Classificações aprovadas indicam padrões corretos. "
            "Classificações rejeitadas indicam erros a evitar."
        )
        return "\n".join(lines)
