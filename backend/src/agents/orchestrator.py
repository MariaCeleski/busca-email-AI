# =============================================================================
# Orquestrador de Agentes — coordena o pipeline de processamento de e-mails
# usando LangGraph StateGraph com invocação efetiva via ainvoke().
#
# Objetivo: Receber um e-mail bruto e coordenar a execução sequencial/condicional
# dos agentes (Classificador, Sumarizador, Gerador de Resposta) com base na
# classificação obtida.
#
# Fluxo LangGraph:
#   Entry → classify → [routing condicional] → summarize / generate_response / manual_review → publish_results → END
#
# Funcionalidades:
# - Estado tipado (EmailWorkflowState) que flui entre os nós do grafo
# - Routing condicional baseado em categoria, prioridade e confiança
# - Dual path: e-mails urgentes com corpo > 200 palavras recebem resumo E resposta
# - Retry por agente (até 3 tentativas) com timeout de 30s por execução DENTRO dos nós
# - Processamento concorrente de até 10 e-mails simultâneos (via semáforo)
# - Estado isolado por e-mail (sem compartilhamento entre execuções paralelas)
# - CORREÇÃO: Agora usa efetivamente self._compiled.ainvoke() em vez de reimplementação manual
#
# Entrada: RawEmail
# Saída: Dict com classification, summary, draft_reply, current_stage, error
# =============================================================================
"""Orquestrador de Agentes — coordena o pipeline de processamento de e-mails usando LangGraph StateGraph."""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, Optional
import httpx
from datetime import datetime

from typing_extensions import TypedDict

from langgraph.graph import END, StateGraph

from src.agents.classifier import ClassifierAgent
from src.agents.response import ResponseAgent
from src.agents.summarizer import SummarizerAgent
from src.config import get_settings
from src.models.classification import ClassificationResult
from src.models.draft import DraftReply
from src.models.email import RawEmail
from src.models.enums import EmailCategory, PriorityLevel, WorkflowStage
from src.models.summary import SummaryResult

logger = logging.getLogger(__name__)


# Estado que flui através do workflow LangGraph.
# Contém o e-mail original, resultados intermediários de cada agente,
# contadores de retry e flags de controle.
class EmailWorkflowState(TypedDict, total=False):
    """Estado que flui através do workflow LangGraph."""

    email: RawEmail                                  # E-mail bruto de entrada
    classification: Optional[ClassificationResult]   # Resultado da classificação
    summary: Optional[SummaryResult]                 # Resultado da sumarização
    draft_reply: Optional[DraftReply]                # Rascunho de resposta gerado
    retry_counts: Dict[str, int]                     # Contagem de retries por agente
    current_stage: str                               # Estágio atual do workflow
    error: Optional[str]                             # Mensagem de erro (se houver)
    flagged_for_review: bool                         # Sinalizado para revisão manual
    needs_dual_path: bool                            # Precisa de resumo + resposta


# Determina o próximo nó baseado nos resultados da classificação.
#
# Lógica de roteamento (conforme Requisitos 2.7, 2.8, 3.1):
# - Se confiança < 0.6 → revisão manual
# - Se categoria é Urgente E corpo > 200 palavras E prioridade Alta/Média → sumarizar (dual path)
# - Se categoria em {Urgente, Pessoal} E prioridade {Alta, Média} → gerar resposta
# - Se categoria em {Informativo, Promocional, Transacional, Spam} OU prioridade Baixa → sumarizar
def route_after_classification(state: EmailWorkflowState) -> str:
    """Determine next node based on classification results.

    Routing logic (per Requirements 2.7, 2.8, 3.1):
    - If confidence < 0.6: route to manual_review
    - If category is Urgent AND body > 200 words AND priority in [High, Medium]:
        route to summarize (dual path — will also get response after summarization)
    - If category in [Urgent, Personal] AND priority in [High, Medium]:
        route to generate_response
    - If category in [Informative, Promotional, Transactional, Spam] OR priority = Low:
        route to summarize
    """
    classification = state.get("classification")
    if classification is None:
        return "manual_review"

    # Low confidence → manual review
    if classification.confidence < 0.6:
        return "manual_review"

    email = state.get("email")
    category = classification.category
    priority = classification.priority

    # Dual path: Urgent with long body AND High/Medium priority → summarize first,
    # then generate_response (handled by route_after_summarize)
    if category == EmailCategory.URGENT and email is not None:
        word_count = len(email.body.split())
        if word_count > 200 and priority in (PriorityLevel.HIGH, PriorityLevel.MEDIUM):
            return "summarize"

    # Route to Response_Agent: category in {Urgent, Personal} AND priority in {High, Medium}
    if category in (EmailCategory.URGENT, EmailCategory.PERSONAL) and priority in (
        PriorityLevel.HIGH,
        PriorityLevel.MEDIUM,
    ):
        return "generate_response"

    # Route to Summarizer_Agent: category in {Informative, Promotional, Transactional, Spam}
    # OR priority = Low
    return "summarize"


# Determina o próximo nó após a sumarização.
# Se o e-mail está no dual path (Urgente + >200 palavras + Alta/Média) → gera resposta também.
# Caso contrário → vai direto para publicar resultados.
def route_after_summarize(state: EmailWorkflowState) -> str:
    """Determine next node after summarization.

    Dual path logic:
    - If there was an error in summarization, go directly to publish_results
    - If the email was routed to summarize because it's Urgent with body > 200 words
      AND priority High/Medium AND no errors, then after summarization it also needs response generation.
    - Otherwise, go directly to publish_results.
    """
    # If there was an error during summarization, skip response generation
    if state.get("error"):
        return "publish_results"
        
    if state.get("needs_dual_path", False):
        return "generate_response"
    return "publish_results"


# Constrói o grafo LangGraph StateGraph para o pipeline de processamento de e-mails.
#
# Nós:
# - classify: chama ClassifierAgent.classify()
# - summarize: chama SummarizerAgent.summarize()
# - generate_response: chama ResponseAgent.generate_reply()
# - manual_review: sinaliza o e-mail para revisão humana
# - publish_results: agrega os resultados finais
#
# Arestas:
# - Entrada → classify
# - classify → roteamento condicional via route_after_classification
# - summarize → roteamento condicional via route_after_summarize
# - generate_response → publish_results
# - manual_review → publish_results
# - publish_results → END
def build_email_workflow(
    classifier: ClassifierAgent,
    summarizer: SummarizerAgent,
    response_agent: ResponseAgent,
    max_retries: int = 3,
    hard_timeout: int = 30,
    orchestrator=None,
) -> StateGraph:
    """Construct a LangGraph StateGraph for the email processing pipeline.

    Nodes:
    - classify: calls ClassifierAgent.classify()
    - summarize: calls SummarizerAgent.summarize()
    - generate_response: calls ResponseAgent.generate_reply()
    - manual_review: flags the email for human review
    - publish_results: aggregates results

    Edges:
    - Entry → classify
    - classify → conditional routing via route_after_classification
    - summarize → conditional routing via route_after_summarize
        - If dual path (Urgent + >200 words + High/Medium): → generate_response
        - Otherwise: → publish_results
    - generate_response → publish_results
    - manual_review → publish_results
    - publish_results → END
    """

    async def classify_node(state: EmailWorkflowState) -> dict:
        """Run classification on the email with retry logic."""
        email = state["email"]
        
        retry_counts = state.get("retry_counts", {})
        retry_counts.setdefault("classifier", 0)
        
        for attempt in range(1, max_retries + 1):
            try:
                result = await asyncio.wait_for(
                    classifier.classify(email),
                    timeout=hard_timeout,
                )
                
                flagged = result.confidence < 0.6

                # Determine if this email needs the dual path
                # (Urgent + body > 200 words + High/Medium priority)
                needs_dual = False
                if (
                    result.category == EmailCategory.URGENT
                    and result.priority in (PriorityLevel.HIGH, PriorityLevel.MEDIUM)
                    and len(email.body.split()) > 200
                ):
                    needs_dual = True

                # Trigger webhook for agent completion
                if orchestrator:
                    await orchestrator._trigger_webhook(
                        "agent_completed",
                        {"classification": result.model_dump(mode='json'), "confidence": result.confidence},
                        agent_name="classifier"
                    )

                return {
                    "classification": result,
                    "current_stage": WorkflowStage.CLASSIFYING.value,
                    "flagged_for_review": flagged,
                    "needs_dual_path": needs_dual,
                    "retry_counts": retry_counts,
                }
            except (asyncio.TimeoutError, Exception) as exc:
                retry_counts["classifier"] = attempt
                logger.warning(
                    "Classification failed (attempt %d/%d): %s",
                    attempt,
                    max_retries,
                    exc,
                )
                if attempt == max_retries:
                    # Trigger error webhook
                    if orchestrator:
                        await orchestrator._trigger_webhook(
                            "error_occurred",
                            {"email": email.model_dump(mode='json')},
                            error_info=f"Classification failed after {max_retries} retries: {exc}"
                        )
                    return {
                        "classification": None,
                        "current_stage": WorkflowStage.FAILED.value,
                        "error": f"Classification failed after {max_retries} retries: {exc}",
                        "flagged_for_review": True,
                        "needs_dual_path": False,
                        "retry_counts": retry_counts,
                    }

    async def summarize_node(state: EmailWorkflowState) -> dict:
        """Run summarization on the email with retry logic."""
        email = state["email"]
        
        retry_counts = state.get("retry_counts", {})
        retry_counts.setdefault("summarizer", 0)
        
        for attempt in range(1, max_retries + 1):
            try:
                result = await asyncio.wait_for(
                    summarizer.summarize(email),
                    timeout=hard_timeout,
                )

                # Trigger webhook for agent completion
                if orchestrator:
                    await orchestrator._trigger_webhook(
                        "agent_completed",
                        {"summary": result.model_dump(mode='json')},
                        agent_name="summarizer"
                    )

                return {
                    "summary": result,
                    "current_stage": WorkflowStage.SUMMARIZING.value,
                    "retry_counts": retry_counts,
                }
            except (asyncio.TimeoutError, Exception) as exc:
                retry_counts["summarizer"] = attempt
                logger.warning(
                    "Summarization failed (attempt %d/%d): %s",
                    attempt,
                    max_retries,
                    exc,
                )
                if attempt == max_retries:
                    # Trigger error webhook
                    if orchestrator:
                        await orchestrator._trigger_webhook(
                            "error_occurred",
                            {"email": email.model_dump(mode='json')},
                            error_info=f"Summarization failed after {max_retries} retries: {exc}"
                        )
                    return {
                        "summary": None,
                        "current_stage": WorkflowStage.FAILED.value,
                        "error": f"Summarization failed after {max_retries} retries: {exc}",
                        "retry_counts": retry_counts,
                    }

    async def generate_response_node(state: EmailWorkflowState) -> dict:
        """Run response generation on the email with retry logic."""
        email = state["email"]
        classification = state.get("classification")
        if classification is None:
            return {
                "draft_reply": None,
                "current_stage": WorkflowStage.FAILED.value,
                "error": "Cannot generate response without classification",
            }
        
        retry_counts = state.get("retry_counts", {})
        retry_counts.setdefault("response_agent", 0)
        
        for attempt in range(1, max_retries + 1):
            try:
                result = await asyncio.wait_for(
                    response_agent.generate_reply(email, classification),
                    timeout=hard_timeout,
                )

                # Trigger webhook for agent completion
                if orchestrator:
                    await orchestrator._trigger_webhook(
                        "agent_completed",
                        {"draft_reply": result.model_dump(mode='json')},
                        agent_name="response_agent"
                    )

                return {
                    "draft_reply": result,
                    "current_stage": WorkflowStage.GENERATING_REPLY.value,
                    "retry_counts": retry_counts,
                }
            except (asyncio.TimeoutError, Exception) as exc:
                retry_counts["response_agent"] = attempt
                logger.warning(
                    "Response generation failed (attempt %d/%d): %s",
                    attempt,
                    max_retries,
                    exc,
                )
                if attempt == max_retries:
                    # Trigger error webhook
                    if orchestrator:
                        await orchestrator._trigger_webhook(
                            "error_occurred",
                            {"email": email.model_dump(mode='json'), "classification": classification.model_dump(mode='json')},
                            error_info=f"Response generation failed after {max_retries} retries: {exc}"
                        )
                    return {
                        "draft_reply": None,
                        "current_stage": WorkflowStage.FAILED.value,
                        "error": f"Response generation failed after {max_retries} retries: {exc}",
                        "retry_counts": retry_counts,
                    }

    async def manual_review_node(state: EmailWorkflowState) -> dict:
        """Flag the email for manual human review."""
        return {
            "current_stage": WorkflowStage.MANUAL_REVIEW.value,
            "flagged_for_review": True,
        }

    async def publish_results_node(state: EmailWorkflowState) -> dict:
        """Aggregate and finalize workflow results."""
        flagged = state.get("flagged_for_review", False)
        error = state.get("error")

        if error:
            stage = WorkflowStage.FAILED.value
        elif flagged:
            stage = WorkflowStage.MANUAL_REVIEW.value
        else:
            stage = WorkflowStage.COMPLETED.value

        # Trigger final webhook for email processing completion
        if orchestrator and stage == WorkflowStage.COMPLETED.value:
            email_data = {
                "email": state.get("email").model_dump(mode='json') if state.get("email") else {},
                "classification": state.get("classification").model_dump(mode='json') if state.get("classification") else {},
                "summary": state.get("summary").model_dump(mode='json') if state.get("summary") else {},
                "draft_reply": state.get("draft_reply").model_dump(mode='json') if state.get("draft_reply") else {},
                "stage": stage
            }
            await orchestrator._trigger_webhook("email_processed", email_data)

        return {"current_stage": stage}

    # Build the graph
    workflow = StateGraph(EmailWorkflowState)

    workflow.add_node("classify", classify_node)
    workflow.add_node("summarize", summarize_node)
    workflow.add_node("generate_response", generate_response_node)
    workflow.add_node("manual_review", manual_review_node)
    workflow.add_node("publish_results", publish_results_node)

    # Entry point
    workflow.set_entry_point("classify")

    # Conditional edges after classification
    workflow.add_conditional_edges(
        "classify",
        route_after_classification,
        {
            "summarize": "summarize",
            "generate_response": "generate_response",
            "manual_review": "manual_review",
            "publish_results": "publish_results",
        },
    )

    # Conditional edges after summarize (dual path support)
    workflow.add_conditional_edges(
        "summarize",
        route_after_summarize,
        {
            "generate_response": "generate_response",
            "publish_results": "publish_results",
        },
    )

    # After generate_response → publish_results
    workflow.add_edge("generate_response", "publish_results")

    # After manual_review → publish_results
    workflow.add_edge("manual_review", "publish_results")

    # After publish_results → END
    workflow.add_edge("publish_results", END)

    return workflow


# Orquestrador multi-agente para o pipeline de processamento de e-mails.
#
# Funcionalidades:
# - Retry por agente até max_retries tentativas
# - Timeout rígido de 30 segundos por execução de agente
# - Processamento concorrente de até max_concurrent e-mails simultâneos
# - Estado isolado por e-mail (sem interferência entre execuções paralelas)
class AgentOrchestrator:
    """Orchestrates the multi-agent email processing pipeline.

    Features:
    - Per-agent retry up to max_retries attempts
    - 30-second hard timeout per agent execution
    - Concurrent processing of up to max_concurrent simultaneous emails
    - Isolated state per email
    - Webhook integration for low-code automation platforms
    """

    def __init__(
        self,
        classifier: ClassifierAgent,
        summarizer: SummarizerAgent,
        response_agent: ResponseAgent,
        max_retries: int = 3,
        hard_timeout: int = 30,
        max_concurrent: int = 10,
    ) -> None:
        self._classifier = classifier
        self._summarizer = summarizer
        self._response_agent = response_agent
        self._max_retries = max_retries
        self._hard_timeout = hard_timeout
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._settings = get_settings()

        # Build the workflow graph
        self._workflow = build_email_workflow(
            classifier, summarizer, response_agent, max_retries, hard_timeout, self
        )
        self._compiled = self._workflow.compile()

    async def process_email(self, email: RawEmail) -> Dict:
        """Execute the full pipeline for an email using LangGraph compiled workflow.

        Uses a semaphore to limit concurrent processing.

        Args:
            email: The raw email to process.

        Returns:
            Dict with classification, summary, draft_reply, stage, and error info.
        """
        async with self._semaphore:
            return await self._process_with_langgraph(email)

    async def _process_with_langgraph(self, email: RawEmail) -> Dict:
        """Process email through the LangGraph compiled workflow.
        
        This method actually invokes the compiled LangGraph via ainvoke(),
        replacing the manual reimplementation that was previously used.
        """
        # Initialize state for LangGraph
        initial_state: EmailWorkflowState = {
            "email": email,
            "classification": None,
            "summary": None,
            "draft_reply": None,
            "retry_counts": {},
            "current_stage": WorkflowStage.QUEUED.value,
            "error": None,
            "flagged_for_review": False,
            "needs_dual_path": False,
        }
        
        try:
            # Execute the compiled LangGraph workflow
            # This is the key fix: actually use self._compiled instead of manual implementation
            final_state = await self._compiled.ainvoke(initial_state)
            
            # Build and return result from final state
            return self._build_result(final_state)
            
        except Exception as exc:
            logger.error("LangGraph execution failed: %s", exc)
            # Fallback to manual error state
            error_state = initial_state.copy()
            error_state["error"] = str(exc)
            error_state["current_stage"] = WorkflowStage.FAILED.value
            return self._build_result(error_state)


    def handle_agent_failure(
        self, agent_name: str, state: EmailWorkflowState
    ) -> EmailWorkflowState:
        """Handle agent failure — mark email as failed and skip remaining agents.

        Args:
            agent_name: Name of the failed agent.
            state: Current workflow state.

        Returns:
            Updated state with failure information.
        """
        state["error"] = f"Agent {agent_name} failed after retries exhausted"
        state["current_stage"] = WorkflowStage.FAILED.value
        return state

    async def _trigger_webhook(
        self, 
        event_type: str, 
        email_data: Dict, 
        agent_name: Optional[str] = None,
        error_info: Optional[str] = None
    ) -> None:
        """Trigger webhook notifications for low-code automation platforms.
        
        Args:
            event_type: Type of event (email_processed, agent_completed, error_occurred)
            email_data: Email processing data
            agent_name: Name of the agent (for agent_completed events)
            error_info: Error information (for error_occurred events)
        """
        if not self._settings.enable_webhooks:
            return
            
        # Convert any Pydantic models to JSON-serializable dicts
        def make_serializable(obj):
            if hasattr(obj, 'model_dump'):
                return obj.model_dump(mode='json')
            return obj
            
        serializable_data = {}
        for key, value in email_data.items():
            serializable_data[key] = make_serializable(value)
            
        webhook_payload = {
            "event_type": event_type,
            "data": {
                "email_id": serializable_data.get("email", {}).get("provider_message_id", "unknown"),
                "timestamp": datetime.utcnow().isoformat(),
                **serializable_data
            },
            "source": "orchestrator",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Add agent-specific data
        if agent_name:
            webhook_payload["data"]["agent_name"] = agent_name
            
        # Add error-specific data  
        if error_info:
            webhook_payload["data"]["error_type"] = error_info
            webhook_payload["data"]["component"] = "orchestrator"
            webhook_payload["data"]["severity"] = "high"
        
        # Send to Zapier endpoint (async, non-blocking)
        asyncio.create_task(self._send_webhook_async(webhook_payload))

    async def _send_webhook_async(self, payload: Dict) -> None:
        """Send webhook payload asynchronously without blocking main flow."""
        try:
            async with httpx.AsyncClient(
                timeout=self._settings.webhook_timeout_seconds
            ) as client:
                # Send to internal webhook endpoint (for Make.com and internal processing)
                webhook_url = f"{self._settings.webhook_base_url}/api/v1/webhooks/zapier"
                
                response = await client.post(
                    webhook_url,
                    json=payload,
                    headers={"X-API-Key": self._settings.api_key}
                )
                
                if response.status_code == 200:
                    logger.debug(f"Internal webhook sent successfully: {payload['event_type']}")
                else:
                    logger.warning(f"Internal webhook failed with status {response.status_code}: {payload['event_type']}")
                
                # Send to external Zapier webhook if configured
                if self._settings.zapier_webhook_url:
                    await self._send_zapier_webhook(payload, client)
                    
        except Exception as exc:
            logger.warning(f"Failed to send internal webhook for {payload['event_type']}: {exc}")

    async def _send_zapier_webhook(self, payload: Dict, client: httpx.AsyncClient) -> None:
        """Send webhook to external Zapier endpoint."""
        try:
            response = await client.post(
                self._settings.zapier_webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                logger.info(f"Zapier webhook sent successfully: {payload['event_type']}")
            else:
                logger.warning(f"Zapier webhook failed with status {response.status_code}: {payload['event_type']}")
                
        except Exception as exc:
            logger.warning(f"Failed to send Zapier webhook for {payload['event_type']}: {exc}")

    def _build_result(self, state: EmailWorkflowState) -> Dict:
        """Aggregate results from workflow state into a return dict.

        Returns:
            Dict with all results for the calling layer to persist to DB
            and push via WebSocket.
        """
        return {
            "email": state.get("email"),
            "classification": state.get("classification"),
            "summary": state.get("summary"),
            "draft_reply": state.get("draft_reply"),
            "current_stage": state.get("current_stage", WorkflowStage.COMPLETED.value),
            "error": state.get("error"),
            "flagged_for_review": state.get("flagged_for_review", False),
            "retry_counts": state.get("retry_counts", {}),
        }
