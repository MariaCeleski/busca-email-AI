"""Agent Orchestrator — coordinates email processing pipeline using LangGraph StateGraph."""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, Optional

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


class EmailWorkflowState(TypedDict, total=False):
    """State that flows through the LangGraph workflow."""

    email: RawEmail
    classification: Optional[ClassificationResult]
    summary: Optional[SummaryResult]
    draft_reply: Optional[DraftReply]
    retry_counts: Dict[str, int]
    current_stage: str
    error: Optional[str]
    flagged_for_review: bool


def route_after_classification(state: EmailWorkflowState) -> str:
    """Determine next node based on classification results.

    Routing logic:
    - If confidence < 0.6: route to publish_results (flagged for review)
    - If category in [Urgent, Personal] AND priority in [High, Medium]:
        route to generate_response
    - If category is Urgent AND body > 200 words: route to summarize first
    - Otherwise: route to summarize
    """
    classification = state.get("classification")
    if classification is None:
        return "publish_results"

    # Low confidence → manual review
    if classification.confidence < 0.6:
        return "publish_results"

    email = state.get("email")
    category = classification.category
    priority = classification.priority

    # Urgent with long body → summarize first (before response)
    if category == EmailCategory.URGENT and email is not None:
        word_count = len(email.body.split())
        if word_count > 200 and priority in (PriorityLevel.HIGH, PriorityLevel.MEDIUM):
            return "summarize"

    # Urgent or Personal with High/Medium priority → generate response
    if category in (EmailCategory.URGENT, EmailCategory.PERSONAL) and priority in (
        PriorityLevel.HIGH,
        PriorityLevel.MEDIUM,
    ):
        return "generate_response"

    # Default: summarize
    return "summarize"


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
    - publish_results: aggregates results

    Edges:
    - Entry → classify
    - classify → conditional routing via route_after_classification
    - summarize → publish_results
    - generate_response → publish_results
    - publish_results → END
    """

    async def classify_node(state: EmailWorkflowState) -> dict:
        """Run classification on the email."""
        email = state["email"]
        try:
            result = await classifier.classify(email)
            flagged = result.confidence < 0.6
            return {
                "classification": result,
                "current_stage": WorkflowStage.CLASSIFYING.value,
                "flagged_for_review": flagged,
            }
        except Exception as exc:
            logger.error("Classification failed: %s", exc)
            return {
                "classification": None,
                "current_stage": WorkflowStage.FAILED.value,
                "error": str(exc),
                "flagged_for_review": True,
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
            "publish_results": "publish_results",
        },
    )

    # After summarize or generate_response → publish_results
    workflow.add_edge("summarize", "publish_results")
    workflow.add_edge("generate_response", "publish_results")

    # After publish_results → END
    workflow.add_edge("publish_results", END)

    return workflow


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

        # Determine route
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
