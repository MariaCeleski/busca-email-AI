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
#
# O demo executa o pipeline COMPLETO:
# 1. Classificação (ClassifierAgent)
# 2. Sumarização (SummarizerAgent)
# 3. Geração de resposta (ResponseAgent) → cria draft_reply com status=pending
#
# Isso permite testar o fluxo de aprovação/rejeição no frontend sem Gmail.
# =============================================================================
@router.post("/demo", response_model=FetchAcknowledgment)
async def insert_demo_emails():
    """Insere e-mails de demonstração e processa pipeline COMPLETO com IA.

    Pipeline: Classificar → Resumir → Gerar Resposta (draft_reply).
    Após processamento, os e-mails terão draft_reply com status 'pending',
    permitindo testar approve/reject no frontend.
    """
    import uuid
    from datetime import datetime, timezone

    from src.models.database import get_session_factory

    demo_emails = [
        # --- URGENTE / Prioridade ALTA ---
        {
            "provider_message_id": f"demo-{uuid.uuid4().hex[:8]}",
            "sender": "ceo@empresa.com",
            "subject": "URGENTE: Sistema fora do ar - cliente reclamando",
            "body": "O sistema de produção caiu há 30 minutos e o cliente principal está ligando a cada 5 minutos. Preciso de alguém do time de infraestrutura verificando AGORA. O SLA de 99.9% está sendo violado. Já tentei reiniciar o serviço via dashboard mas não resolveu. Os logs indicam problema de memória no servidor principal. Preciso de um status report em 15 minutos. Se não resolvermos em 1 hora, vamos perder o contrato de R$ 500 mil. Quem puder ajudar, entre na call de emergência imediatamente.",
            "provider": "gmail",
        },
        # --- PESSOAL / Prioridade MÉDIA ---
        {
            "provider_message_id": f"demo-{uuid.uuid4().hex[:8]}",
            "sender": "joao.amigo@gmail.com",
            "subject": "Churras no sábado - confirma?",
            "body": "E aí, beleza? To organizando um churrasco lá em casa no sábado a partir das 14h. Vai ter cerveja, carne de primeira e aquele futebol de sempre. O pessoal da faculdade vai estar lá também. Me avisa se você vem pra eu calcular a quantidade de carne. Pode trazer alguém se quiser. Endereço: Rua das Flores, 123. Abraço!",
            "provider": "gmail",
        },
        # --- INFORMATIVO / Prioridade BAIXA ---
        {
            "provider_message_id": f"demo-{uuid.uuid4().hex[:8]}",
            "sender": "rh@empresa.com",
            "subject": "Comunicado: Novo horário de funcionamento do refeitório",
            "body": "Prezados colaboradores, informamos que a partir da próxima segunda-feira o refeitório da empresa passará a funcionar no seguinte horário: Café da manhã: 7h às 9h. Almoço: 11h30 às 14h. Lanche da tarde: 15h às 16h30. A mudança visa atender melhor os turnos da equipe de operações. Dúvidas podem ser encaminhadas ao RH pelo ramal 2345. Atenciosamente, Departamento de Recursos Humanos.",
            "provider": "gmail",
        },
        # --- SPAM / Prioridade BAIXA ---
        {
            "provider_message_id": f"demo-{uuid.uuid4().hex[:8]}",
            "sender": "ganhe-dinheiro-facil@promo99.xyz",
            "subject": "🔥💰 GANHE R$50.000 TRABALHANDO DE CASA!!! Clique AGORA!!!",
            "body": "PARABÉNS!!! Você foi selecionado para ganhar R$50.000 por mês trabalhando apenas 2 horas por dia do conforto da sua casa!!! Não é pirâmide!!! Milhares de pessoas já estão lucrando!!! Clique no link abaixo AGORA antes que as vagas acabem!!! OFERTA POR TEMPO LIMITADO!!! www.dinheiro-facil-nao-e-golpe.xyz/cadastro. Não perca essa oportunidade ÚNICA na vida!!!",
            "provider": "gmail",
        },
        # --- PROMOCIONAL / Prioridade BAIXA ---
        {
            "provider_message_id": f"demo-{uuid.uuid4().hex[:8]}",
            "sender": "ofertas@magazineluiza.com.br",
            "subject": "🎉 Black Friday antecipada: até 60% OFF em eletrônicos",
            "body": "Aproveite nossa Black Friday antecipada! Notebooks a partir de R$ 2.499, smartphones com até 60% de desconto, TVs 4K com preço especial para você. Ofertas válidas até domingo ou enquanto durarem os estoques. Frete grátis para compras acima de R$ 299. Use o cupom BLACKFRIDAY2025 para 10% extra. Confira as melhores ofertas no nosso app. Magazine Luiza - De gente pra gente.",
            "provider": "gmail",
        },
        # --- TRANSACIONAL / Prioridade MÉDIA ---
        {
            "provider_message_id": f"demo-{uuid.uuid4().hex[:8]}",
            "sender": "noreply@nubank.com.br",
            "subject": "Compra aprovada: R$ 189,90 no Mercado Livre",
            "body": "Olá! Informamos que uma compra foi aprovada no seu cartão Nubank. Valor: R$ 189,90. Estabelecimento: Mercado Livre. Data: 15/07/2025. Parcelas: 3x de R$ 63,30. Se você não reconhece essa compra, bloqueie seu cartão imediatamente pelo app e entre em contato conosco. Nubank - Seu dinheiro, do seu jeito.",
            "provider": "gmail",
        },
        # --- PESSOAL / Prioridade ALTA (requer resposta) ---
        {
            "provider_message_id": f"demo-{uuid.uuid4().hex[:8]}",
            "sender": "maria.silva@cliente.com",
            "subject": "Precisamos conversar sobre o prazo do módulo 3",
            "body": "Bom dia! Gostaria de saber se o módulo 3 do projeto será entregue na data prevista (próxima quarta-feira). Nosso time de QA precisa planejar os testes de integração e precisamos de pelo menos 2 dias de antecedência para preparar o ambiente. Se houver algum atraso, por favor nos avise o quanto antes para que possamos ajustar nosso cronograma interno. Também gostaria de agendar uma call para discutir os requisitos do módulo 4. Qual a melhor data para vocês na próxima semana? Aguardo retorno urgente pois tenho reunião com diretoria amanhã. Atenciosamente, Maria Silva - Gerente de Projetos.",
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
                    user_id=demo_user_id,
                )
                inserted += 1

            await session.commit()

        # =====================================================================
        # PIPELINE COMPLETO: Classificar → Resumir → Gerar Resposta
        # =====================================================================
        from src.agents.classifier import ClassifierAgent, ClassificationError
        from src.agents.summarizer import SummarizerAgent
        from src.models.email import RawEmail

        classifier = ClassifierAgent()
        summarizer = SummarizerAgent()

        processed_count = 0

        async with session_factory() as session2:
            from src.models.orm import DraftReply as DraftReplyORM
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

                    # --- Etapa 1: Classificação ---
                    classification = await classifier.classify(raw)

                    email_record = await repo2.get_by_provider_message_id(
                        email_data["provider_message_id"]
                    )
                    if not email_record:
                        continue

                    await repo2.update_classification(
                        email_record.id,
                        category=classification.category.value,
                        priority=classification.priority.value,
                        confidence=classification.confidence,
                        flagged_for_review=classification.flagged_for_review,
                    )

                    # --- Etapa 2: Sumarização ---
                    try:
                        summary_result = await summarizer.summarize(raw)
                        await repo2.update_summary(
                            email_record.id,
                            summary=summary_result.summary,
                            action_items=summary_result.action_items,
                            summary_is_fallback=summary_result.is_fallback,
                        )
                    except Exception as e:
                        logger.warning("Demo summarization failed for %s: %s", email_data["subject"], e)

                    # --- Etapa 3: Gerar resposta (draft_reply) ---
                    try:
                        from openai import AsyncOpenAI
                        from src.config import get_settings

                        settings = get_settings()
                        client = AsyncOpenAI(api_key=settings.openai_api_key)

                        response_prompt = f"""Você é um assistente que gera respostas profissionais para e-mails.
Gere uma resposta para o seguinte e-mail:

De: {email_data["sender"]}
Assunto: {email_data["subject"]}
Corpo: {email_data["body"]}

Instruções:
- Resposta no máximo 200 palavras
- Tom profissional e cordial
- Assunto sugerido no máximo 100 caracteres
- Responda diretamente ao conteúdo do e-mail

Retorne APENAS JSON:
{{"reply_body": "<texto da resposta>", "suggested_subject": "<assunto sugerido>"}}"""

                        response = await client.chat.completions.create(
                            model=settings.openai_model,
                            messages=[{"role": "user", "content": response_prompt}],
                        )
                        raw_output = response.choices[0].message.content or ""

                        # Parse JSON response
                        import json
                        import re
                        cleaned = raw_output.strip()
                        if cleaned.startswith("```"):
                            cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
                            cleaned = re.sub(r'\s*```$', '', cleaned)

                        parsed = json.loads(cleaned)
                        reply_body = parsed.get("reply_body", "Obrigado pelo contato.")
                        suggested_subject = parsed.get("suggested_subject", f"Re: {email_data['subject']}")[:150]

                        # Inserir draft_reply no banco com status='pending'
                        draft = DraftReplyORM(
                            email_id=email_record.id,
                            reply_body=reply_body,
                            suggested_subject=suggested_subject,
                            referenced_email_ids=[],
                            status="pending",
                            generated_at=datetime.utcnow(),
                        )
                        session2.add(draft)

                    except Exception as e:
                        logger.warning("Demo response generation failed for %s: %s", email_data["subject"], e)

                    # Marcar como completo
                    await repo2.update_workflow_stage(
                        email_record.id, workflow_stage="completed"
                    )
                    processed_count += 1

                except ClassificationError as e:
                    logger.warning("Demo classification failed: %s", e)
                except Exception as e:
                    logger.warning("Demo processing error: %s", e)

            await session2.commit()

        return FetchAcknowledgment(
            status="demo_complete",
            task_id=None,
            message=f"{inserted} e-mails inseridos, {processed_count} processados com pipeline completo (classificar + resumir + resposta).",
        )

    except Exception as exc:
        logger.error("Demo failed: %s", exc)
        return FetchAcknowledgment(
            status="error",
            task_id=None,
            message=f"Erro ao inserir demos: {str(exc)}",
        )
