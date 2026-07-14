"""Email fetch endpoint.

Provides:
- POST /api/v1/emails/fetch — trigger manual email fetch

Requirements: 8.4
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/emails", tags=["fetch"])


class FetchAcknowledgment(BaseModel):
    """Response for manual fetch trigger."""

    status: str
    task_id: Optional[str] = None
    message: str


@router.post("/fetch", response_model=FetchAcknowledgment)
async def trigger_fetch():
    """Trigger a manual email fetch from connected email providers.

    Enqueues the poll_emails_task as a Celery task and returns immediately
    with an acknowledgment containing the task ID.

    Returns:
        FetchAcknowledgment with status="fetch_initiated" and the Celery task ID.
    """
    try:
        from src.tasks.poll_emails import poll_emails_task

        result = poll_emails_task.delay()
        task_id = result.id

        logger.info("Manual email fetch triggered, task_id=%s", task_id)

        return FetchAcknowledgment(
            status="fetch_initiated",
            task_id=task_id,
            message="Email fetch has been initiated. Processing will occur in the background.",
        )
    except Exception as exc:
        logger.error("Failed to trigger email fetch: %s", exc)
        return FetchAcknowledgment(
            status="error",
            task_id=None,
            message=f"Failed to initiate email fetch: {str(exc)}",
        )


# =============================================================================
# ENDPOINT DE DEMONSTRAÇÃO (dados fictícios para testes)
# Usado apenas quando não há conta Gmail/Outlook conectada.
# Em produção, o botão "Buscar E-mails" chama POST /fetch (acima),
# que dispara o Celery task para buscar e-mails reais via Gmail API.
# =============================================================================
@router.post("/demo", response_model=FetchAcknowledgment)
async def insert_demo_emails():
    """Insere e-mails de demonstração no banco e processa com IA.

    Útil para demonstrar o sistema sem precisar de conta Gmail/Outlook conectada.
    Insere 3 e-mails simulados e processa cada um pelo pipeline de classificação.
    """
    import asyncio
    import uuid
    from datetime import datetime, timezone

    from sqlalchemy.ext.asyncio import AsyncSession

    from src.models.database import get_session_factory

    demo_emails = [
        {
            "provider_message_id": f"demo-{uuid.uuid4().hex[:8]}",
            "sender": "chefe@empresa.com",
            "subject": "URGENTE: Reunião amanhã às 9h sobre o projeto",
            "body": "Olá equipe, precisamos nos reunir amanhã às 9h para discutir o andamento do projeto. A entrega está atrasada e o cliente está cobrando. Tragam os relatórios atualizados. É imprescindível a presença de todos.",
            "provider": "gmail",
        },
        {
            "provider_message_id": f"demo-{uuid.uuid4().hex[:8]}",
            "sender": "newsletter@techblog.com.br",
            "subject": "As 10 tendências de IA para 2026",
            "body": "Confira as principais tendências de Inteligência Artificial para este ano: modelos de linguagem mais eficientes, agentes autônomos, computação quântica aplicada ao ML, edge AI em dispositivos móveis, IA generativa para código, automação de processos empresariais com LLMs, novos frameworks de orquestração de agentes como LangGraph e CrewAI, avanços em visão computacional para medicina, IA responsável e governança de dados, e democratização do acesso a modelos open-source. Cada uma dessas áreas está transformando a forma como empresas e desenvolvedores trabalham no dia a dia. Leia mais em nosso blog para entender como se preparar para essas mudanças e quais habilidades desenvolver para se manter relevante no mercado de tecnologia.",
            "provider": "gmail",
        },
        {
            "provider_message_id": f"demo-{uuid.uuid4().hex[:8]}",
            "sender": "promocoes@loja.com.br",
            "subject": "🔥 MEGA SALE: 70% OFF em tudo!",
            "body": "Aproveite nossa mega promoção! Descontos de até 70% em todos os produtos. Oferta válida somente hoje. Clique aqui para conferir.",
            "provider": "gmail",
        },
    ]

    try:
        session_factory = get_session_factory()

        async with session_factory() as session:
            from src.models.repositories import ProcessedEmailRepository, UserRepository

            # Criar user demo se não existir
            user_repo = UserRepository(session)
            demo_user_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
            existing_user = await user_repo.get_by_id(demo_user_id)
            if not existing_user:
                from src.models.orm import User
                demo_user = User(id=demo_user_id, email="demo@example.com")
                session.add(demo_user)
                await session.flush()

            repo = ProcessedEmailRepository(session)
            inserted = 0

            for email_data in demo_emails:
                # Verificar duplicata
                existing = await repo.get_by_provider_message_id(email_data["provider_message_id"])
                if existing:
                    continue

                # Inserir no banco
                await repo.create(
                    provider_message_id=email_data["provider_message_id"],
                    sender=email_data["sender"],
                    subject=email_data["subject"],
                    body=email_data["body"],
                    timestamp=datetime.utcnow(),
                    provider=email_data["provider"],
                    workflow_stage="queued",
                    # user_id placeholder
                    user_id=uuid.UUID("12345678-1234-5678-1234-567812345678"),
                )
                inserted += 1

            await session.commit()

            # Agora classificar cada e-mail inserido
            from src.agents.classifier import ClassifierAgent, ClassificationError
            from src.models.email import RawEmail

            classifier = ClassifierAgent()

            async with session_factory() as session2:
                repo2 = ProcessedEmailRepository(session2)
                for email_data in demo_emails:
                    try:
                        raw = RawEmail(
                            provider_message_id=email_data["provider_message_id"],
                            sender=email_data["sender"],
                            subject=email_data["subject"],
                            body=email_data["body"],
                            timestamp=datetime.now(timezone.utc),
                            provider=email_data["provider"],
                        )
                        result = await classifier.classify(raw)

                        # Atualizar no banco
                        email_record = await repo2.get_by_provider_message_id(
                            email_data["provider_message_id"]
                        )
                        if email_record:
                            await repo2.update_classification(
                                email_record.id,
                                category=result.category.value,
                                priority=result.priority.value,
                                confidence=result.confidence,
                                flagged_for_review=result.flagged_for_review,
                            )
                            await repo2.update_workflow_stage(
                                email_record.id, workflow_stage="completed"
                            )
                    except ClassificationError as e:
                        logger.warning("Demo classification failed: %s", e)
                    except Exception as e:
                        logger.warning("Demo processing error: %s", e)

                await session2.commit()

        return FetchAcknowledgment(
            status="demo_complete",
            task_id=None,
            message=f"{inserted} e-mails de demonstração inseridos e processados com IA.",
        )

    except Exception as exc:
        logger.error("Demo failed: %s", exc)
        return FetchAcknowledgment(
            status="error",
            task_id=None,
            message=f"Erro ao inserir demos: {str(exc)}",
        )
