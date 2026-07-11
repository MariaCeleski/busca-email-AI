# =============================================================================
# Orquestrador de Agentes — coordena o pipeline de processamento de e-mails
# usando LangGraph StateGraph.
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
# - Retry por agente (até 3 tentativas) com timeout de 30s por execução
# - Processamento concorrente de até 10 e-mails simultâneos (via semáforo)
# - Estado isolado por e-mail (sem compartilhamento entre execuções paralelas)
#
# Entrada: RawEmail
# Saída: Dict com classification, summary, draft_reply, current_stage, error
# =============================================================================
"""Orquestrador de Agentes — coordena o pipeline de processamento de e-mails usando LangGraph StateGraph."""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, Optional

from typing_extensions import TypedDict

from langgraph.graph import END, StateGraph

from src.agents.classifier import ClassifierAgent
from src.agents.response import ResponseAgent
from src.agents.summarizer import SummarizerAgent
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
    - If the email was routed to summarize because it's Urgent with body > 200 words
      AND priority High/Medium, then after summarization it also needs response generation.
    - Otherwise, go directly to publish_results.
    """
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
        """Run classification on the email."""
        email = state["email"]
        try:
            result = await classifier.classify(email)
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

            return {
                "classification": result,
                "current_stage": WorkflowStage.CLASSIFYING.value,
                "flagged_for_review": flagged,
                "needs_dual_path": needs_dual,
            }
        except Exception as exc:
            logger.error("Classification failed: %s", exc)
            return {
                "classification": None,
                "current_stage": WorkflowStage.FAILED.value,
                "error": str(exc),
                "flagged_for_review": True,
                "needs_dual_path": False,
            }

    async def summarize_node(state: EmailWorkflowState) -> dict:
        """Run summarization on the email."""
        email = state["email"]
        try:
            result = await summarizer.summarize(email)
            return {
                "summary": result,
                "current_stage": WorkflowStage.SUMMARIZING.value,
            }
        except Exception as exc:
            logger.error("Summarization failed: %s", exc)
            return {
                "summary": None,
                "current_stage": WorkflowStage.FAILED.value,
                "error": str(exc),
            }

    async def generate_response_node(state: EmailWorkflowState) -> dict:
        """Run response generation on the email."""
        email = state["email"]
        classification = state.get("classification")
        if classification is None:
            return {
                "draft_reply": None,
                "current_stage": WorkflowStage.FAILED.value,
                "error": "Cannot generate response without classification",
            }
        try:
            result = await response_agent.generate_reply(email, classification)
            return {
                "draft_reply": result,
                "current_stage": WorkflowStage.GENERATING_REPLY.value,
            }
        except Exception as exc:
            logger.error("Response generation failed: %s", exc)
            return {
                "draft_reply": None,
                "current_stage": WorkflowStage.FAILED.value,
                "error": str(exc),
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

        # Build the workflow graph
        self._workflow = build_email_workflow(classifier, summarizer, response_agent)
        self._compiled = self._workflow.compile()

    async def process_email(self, email: RawEmail) -> Dict:
        """Execute the full pipeline for an email with retry and timeout logic.

        Uses a semaphore to limit concurrent processing.

        Args:
            email: The raw email to process.

        Returns:
            Dict with classification, summary, draft_reply, stage, and error info.
        """
        async with self._semaphore:
            return await self._process_with_retries(email)

    async def _process_with_retries(self, email: RawEmail) -> Dict:
        """Process email through the pipeline with per-agent retry logic."""
        state: EmailWorkflowState = {
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

        # Step 1: Classify with retry
        classification = await self._execute_agent_with_retry(
            "classifier",
            self._classify_email,
            email,
            state,
        )
        if classification is None:
            # Retry exhausted — mark failed
            return self._build_result(state)

        state["classification"] = classification
        state["flagged_for_review"] = classification.confidence < 0.6

        # If flagged for review, skip remaining agents
        if state["flagged_for_review"]:
            state["current_stage"] = WorkflowStage.MANUAL_REVIEW.value
            return self._build_result(state)

        # Determine route and whether dual path is needed
        needs_dual_path = (
            classification.category == EmailCategory.URGENT
            and classification.priority in (PriorityLevel.HIGH, PriorityLevel.MEDIUM)
            and len(email.body.split()) > 200
        )
        state["needs_dual_path"] = needs_dual_path

        route = route_after_classification(state)

        # Step 2: Execute based on route
        if route == "summarize":
            summary = await self._execute_agent_with_retry(
                "summarizer",
                self._summarize_email,
                email,
                state,
            )
            state["summary"] = summary

            # Dual path: after summarization, also generate response
            if needs_dual_path and state.get("error") is None:
                draft = await self._execute_agent_with_retry(
                    "response_agent",
                    self._generate_response,
                    email,
                    classification,
                    state,
                )
                state["draft_reply"] = draft

        elif route == "generate_response":
            draft = await self._execute_agent_with_retry(
                "response_agent",
                self._generate_response,
                email,
                classification,
                state,
            )
            state["draft_reply"] = draft

        # Finalize
        if state.get("error"):
            state["current_stage"] = WorkflowStage.FAILED.value
        else:
            state["current_stage"] = WorkflowStage.COMPLETED.value

        return self._build_result(state)

    async def _execute_agent_with_retry(
        self, agent_name: str, func, *args
    ) -> object:
        """Execute an agent function with retry and timeout logic.

        Args:
            agent_name: Name of the agent for logging/tracking.
            func: The async callable to execute.
            *args: Arguments to pass (last arg is state dict for retry tracking).

        Returns:
            The result of the agent call, or None on exhaustion.
        """
        # The last positional arg is always the state dict
        state = args[-1]
        call_args = args[:-1]

        retry_counts = state.get("retry_counts", {})
        retry_counts.setdefault(agent_name, 0)

        for attempt in range(1, self._max_retries + 1):
            try:
                result = await asyncio.wait_for(
                    func(*call_args),
                    timeout=self._hard_timeout,
                )
                return result
            except asyncio.TimeoutError:
                logger.warning(
                    "Agent %s timed out (attempt %d/%d)",
                    agent_name,
                    attempt,
                    self._max_retries,
                )
                retry_counts[agent_name] = attempt
            except Exception as exc:
                logger.warning(
                    "Agent %s failed (attempt %d/%d): %s",
                    agent_name,
                    attempt,
                    self._max_retries,
                    exc,
                )
                retry_counts[agent_name] = attempt

        # Retry exhausted
        state["retry_counts"] = retry_counts
        state["error"] = f"Agent {agent_name} failed after {self._max_retries} retries"
        state["current_stage"] = WorkflowStage.FAILED.value
        return None

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

    async def _classify_email(self, email: RawEmail) -> ClassificationResult:
        """Wrapper for classifier agent call."""
        return await self._classifier.classify(email)

    async def _summarize_email(self, email: RawEmail) -> SummaryResult:
        """Wrapper for summarizer agent call."""
        return await self._summarizer.summarize(email)

    async def _generate_response(
        self, email: RawEmail, classification: ClassificationResult
    ) -> DraftReply:
        """Wrapper for response agent call."""
        return await self._response_agent.generate_reply(email, classification)

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
