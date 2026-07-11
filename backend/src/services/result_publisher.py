"""Result Publisher Service — persists workflow results and notifies the Dashboard.

Handles the final stage of the email processing pipeline:
1. Stores classification, summary, and workflow_stage in PostgreSQL (processed_emails)
2. Creates a draft_reply record in PostgreSQL if one was generated
3. Stores the email embedding in ChromaDB via VectorStoreService
4. Publishes a WebSocket notification to connected Dashboard clients

Validates: Requirements 6.6, 5.1
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from src.models.classification import ClassificationResult
from src.models.draft import DraftReply
from src.models.email import RawEmail
from src.models.enums import EmailCategory, WorkflowStage
from src.models.repositories import DraftReplyRepository, ProcessedEmailRepository
from src.models.summary import SummaryResult
from src.models.vector_store import EmailMetadata

logger = logging.getLogger(__name__)


class ResultPublisher:
    """Publishes aggregated workflow results to PostgreSQL, ChromaDB, and WebSocket.

    This service is invoked after all designated agents complete processing for an
    email. It handles persistence and real-time notification as the final pipeline step.
    """

    def __init__(
        self,
        session_factory,
        vector_store_service,
        connection_manager,
    ) -> None:
        """Initialize the ResultPublisher.

        Args:
            session_factory: SQLAlchemy async_sessionmaker for DB sessions.
            vector_store_service: VectorStoreService instance for ChromaDB operations.
            connection_manager: WebSocket ConnectionManager for broadcasting notifications.
        """
        self._session_factory = session_factory
        self._vector_store = vector_store_service
        self._connection_manager = connection_manager

    async def publish(self, workflow_result: Dict[str, Any]) -> Dict[str, Any]:
        """Persist processing results and notify connected clients.

        Aggregates classification + summary + draft reply from the workflow result,
        stores them in PostgreSQL and ChromaDB, and broadcasts a WebSocket notification.

        Args:
            workflow_result: Dict from AgentOrchestrator._build_result() containing:
                - email: RawEmail
                - classification: ClassificationResult | None
                - summary: SummaryResult | None
                - draft_reply: DraftReply | None
                - current_stage: str (WorkflowStage value)
                - error: str | None
                - flagged_for_review: bool
                - retry_counts: dict

        Returns:
            Dict with publishing status and any created record IDs.
        """
        email: Optional[RawEmail] = workflow_result.get("email")
        classification: Optional[ClassificationResult] = workflow_result.get("classification")
        summary: Optional[SummaryResult] = workflow_result.get("summary")
        draft_reply: Optional[DraftReply] = workflow_result.get("draft_reply")
        current_stage: str = workflow_result.get("current_stage", WorkflowStage.COMPLETED.value)
        error: Optional[str] = workflow_result.get("error")
        flagged_for_review: bool = workflow_result.get("flagged_for_review", False)

        if email is None:
            logger.error("Cannot publish results: no email in workflow_result")
            return {"success": False, "error": "No email in workflow result"}

        result: Dict[str, Any] = {
            "success": True,
            "email_id": None,
            "draft_reply_id": None,
            "embedding_id": None,
        }

        # Step 1: Persist results in PostgreSQL
        email_id = await self._store_in_postgres(
            email=email,
            classification=classification,
            summary=summary,
            draft_reply=draft_reply,
            current_stage=current_stage,
            error=error,
            flagged_for_review=flagged_for_review,
        )
        result["email_id"] = email_id

        # Step 2: Store embedding in ChromaDB (only for successfully classified emails)
        if classification is not None and current_stage != WorkflowStage.FAILED.value:
            embedding_id = await self._store_embedding(
                email=email,
                email_id=str(email_id) if email_id else email.provider_message_id,
                classification=classification,
            )
            result["embedding_id"] = embedding_id

        # Step 3: Publish WebSocket notification
        notification = self._build_notification(
            email_id=email_id,
            email=email,
            classification=classification,
            summary=summary,
            draft_reply=draft_reply,
            current_stage=current_stage,
        )
        await self._broadcast_notification(notification)

        logger.info(
            "Published results for email provider_message_id=%s, stage=%s",
            email.provider_message_id,
            current_stage,
        )
        return result

    async def _store_in_postgres(
        self,
        email: RawEmail,
        classification: Optional[ClassificationResult],
        summary: Optional[SummaryResult],
        draft_reply: Optional[DraftReply],
        current_stage: str,
        error: Optional[str],
        flagged_for_review: bool,
    ) -> Optional[uuid.UUID]:
        """Store or update processing results in PostgreSQL.

        Updates the processed_email record with classification, summary, and
        workflow_stage. Creates a draft_reply record if one was generated.

        Returns:
            The UUID of the processed_email record, or None on failure.
        """
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    email_repo = ProcessedEmailRepository(session)
                    draft_repo = DraftReplyRepository(session)

                    # Find existing processed email by provider_message_id
                    processed_email = await email_repo.get_by_provider_message_id(
                        email.provider_message_id
                    )

                    if processed_email is None:
                        # Create new record if it doesn't exist
                        processed_email = await email_repo.create(
                            provider_message_id=email.provider_message_id,
                            sender=email.sender,
                            subject=email.subject,
                            body=email.body,
                            timestamp=email.timestamp,
                            attachments=[
                                att.model_dump() for att in email.attachments
                            ] if email.attachments else [],
                            thread_id=getattr(email, "thread_id", None),
                            provider=email.provider,
                            # Use a placeholder user_id; in production this would
                            # come from the authenticated context
                            user_id=self._get_user_id_for_email(email),
                            workflow_stage=current_stage,
                            error_message=error,
                            flagged_for_review=flagged_for_review,
                        )

                    email_id = processed_email.id

                    # Update classification fields
                    if classification is not None:
                        await email_repo.update_classification(
                            email_id=email_id,
                            category=classification.category.value,
                            priority=classification.priority.value,
                            confidence=classification.confidence,
                            flagged_for_review=flagged_for_review,
                        )

                    # Update summary fields
                    if summary is not None:
                        await email_repo.update_summary(
                            email_id=email_id,
                            summary=summary.summary,
                            action_items=summary.action_items,
                            summary_is_fallback=summary.is_fallback,
                        )

                    # Update workflow stage
                    await email_repo.update_workflow_stage(
                        email_id=email_id,
                        workflow_stage=current_stage,
                        error_message=error,
                    )

                    # Create draft reply record if one was generated
                    if draft_reply is not None:
                        new_draft = await draft_repo.create(
                            email_id=email_id,
                            reply_body=draft_reply.reply_body,
                            suggested_subject=draft_reply.suggested_subject,
                            referenced_email_ids=draft_reply.referenced_email_ids,
                            status=draft_reply.status.value,
                            generated_at=draft_reply.generated_at,
                        )
                        logger.info(
                            "Created draft_reply id=%s for email_id=%s",
                            new_draft.id,
                            email_id,
                        )

                    return email_id

        except Exception as exc:
            logger.error(
                "Failed to store results in PostgreSQL for email %s: %s",
                email.provider_message_id,
                exc,
            )
            return None

    async def _store_embedding(
        self,
        email: RawEmail,
        email_id: str,
        classification: ClassificationResult,
    ) -> Optional[str]:
        """Store email embedding in ChromaDB via VectorStoreService.

        Args:
            email: The raw email to generate and store an embedding for.
            email_id: The database ID of the processed email.
            classification: The classification result (used for metadata).

        Returns:
            The ChromaDB record ID, or None on failure.
        """
        try:
            # Construct text for embedding: subject + body
            text = f"{email.subject}\n{email.body}" if email.subject else email.body

            metadata = EmailMetadata(
                email_id=email_id,
                sender=email.sender,
                timestamp=email.timestamp,
                category=classification.category,
                provider_message_id=email.provider_message_id,
                thread_id=getattr(email, "thread_id", None),
            )

            record_id = await self._vector_store.store_embedding(
                email_id=email_id,
                text=text,
                metadata=metadata,
            )
            return record_id

        except Exception as exc:
            logger.error(
                "Failed to store embedding in ChromaDB for email %s: %s",
                email.provider_message_id,
                exc,
            )
            return None

    def _build_notification(
        self,
        email_id: Optional[uuid.UUID],
        email: RawEmail,
        classification: Optional[ClassificationResult],
        summary: Optional[SummaryResult],
        draft_reply: Optional[DraftReply],
        current_stage: str,
    ) -> Dict[str, Any]:
        """Build a WebSocket notification payload.

        The notification includes:
        - email_id
        - classification result (category, priority, confidence)
        - whether a summary was generated
        - whether a draft reply was generated
        - workflow_stage (completed/failed/manual_review)

        Returns:
            Dict suitable for JSON serialization and WebSocket broadcast.
        """
        notification: Dict[str, Any] = {
            "type": "email_processing_complete",
            "email_id": str(email_id) if email_id else None,
            "provider_message_id": email.provider_message_id,
            "workflow_stage": current_stage,
            "has_summary": summary is not None,
            "has_draft_reply": draft_reply is not None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if classification is not None:
            notification["classification"] = {
                "category": classification.category.value,
                "priority": classification.priority.value,
                "confidence": classification.confidence,
            }
        else:
            notification["classification"] = None

        return notification

    async def _broadcast_notification(self, notification: Dict[str, Any]) -> None:
        """Broadcast notification to all connected WebSocket clients.

        Args:
            notification: The notification payload to broadcast.
        """
        try:
            await self._connection_manager.broadcast(notification)
            logger.debug(
                "Broadcast notification for email_id=%s",
                notification.get("email_id"),
            )
        except Exception as exc:
            # WebSocket broadcast failure should not break the pipeline
            logger.warning(
                "Failed to broadcast WebSocket notification: %s", exc
            )

    def _get_user_id_for_email(self, email: RawEmail) -> uuid.UUID:
        """Get or derive the user_id for a given email.

        In production, this would resolve from the authenticated session context
        or from the connected_accounts table based on the email provider details.
        For now, returns a deterministic UUID based on the provider info.

        Args:
            email: The raw email being processed.

        Returns:
            A UUID representing the user who owns this email.
        """
        # In a full implementation, this would look up the user from
        # connected_accounts by matching provider + email address.
        # For the service layer, we use a namespace-based UUID as placeholder.
        namespace = uuid.UUID("12345678-1234-5678-1234-567812345678")
        return uuid.uuid5(namespace, f"{email.provider}:{email.sender}")
