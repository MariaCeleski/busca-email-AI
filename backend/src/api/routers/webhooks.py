"""Webhook endpoints for low-code automation integrations."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


class ZapierWebhookPayload(BaseModel):
    """Zapier webhook payload schema."""
    
    event_type: str = Field(..., description="Event type: email_processed, agent_completed, error_occurred")
    data: Dict[str, Any] = Field(..., description="Event-specific data")
    source: str = Field(default="zapier", description="Source system")
    timestamp: Optional[str] = Field(default=None, description="Event timestamp")


class MakeWebhookPayload(BaseModel):
    """Make.com webhook payload schema."""
    
    trigger_type: str = Field(default="scheduled", description="Trigger type: scheduled, manual")
    request_data: Dict[str, Any] = Field(default_factory=dict, description="Request parameters")
    source: str = Field(default="make", description="Source system")


class WebhookResponse(BaseModel):
    """Standard webhook response."""
    
    success: bool = Field(..., description="Request success status")
    message: str = Field(..., description="Response message")
    event_id: Optional[str] = Field(default=None, description="Generated event ID")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Response data")


@router.post("/zapier", response_model=WebhookResponse)
async def zapier_webhook(
    payload: ZapierWebhookPayload,
) -> WebhookResponse:
    """
    Zapier webhook endpoint for automation triggers.
    
    Supported event types:
    - email_processed: When email pipeline completes
    - agent_completed: When specific agent finishes processing
    - error_occurred: When system error needs attention
    
    Returns structured response for Zapier to process.
    """
    try:
        logger.info(f"Zapier webhook received: {payload.event_type} from {payload.source}")
        
        # Process different event types
        response_data = {}
        
        if payload.event_type == "email_processed":
            response_data = _handle_email_processed(payload.data)
        elif payload.event_type == "agent_completed":
            response_data = _handle_agent_completed(payload.data)
        elif payload.event_type == "error_occurred":
            response_data = _handle_error_occurred(payload.data)
        else:
            raise HTTPException(
                status_code=400, 
                detail=f"Unsupported event type: {payload.event_type}"
            )
        
        # Generate event ID for tracking
        event_id = f"evt_{payload.event_type}_{hash(str(payload.data)) % 100000}"
        
        logger.info(f"Zapier webhook processed successfully: {event_id}")
        
        return WebhookResponse(
            success=True,
            message=f"Event {payload.event_type} processed successfully",
            event_id=event_id,
            data=response_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Zapier webhook error: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Webhook processing failed: {str(e)}"
        )


@router.post("/make", response_model=WebhookResponse)
async def make_webhook(
    payload: MakeWebhookPayload,
) -> WebhookResponse:
    """
    Make.com webhook endpoint for visual automation.
    
    Accepts flexible payload structure for Make.com scenarios.
    Returns formatted data suitable for Make.com processing.
    """
    try:
        logger.info(f"Make.com webhook received: {payload.trigger_type} from {payload.source}")
        
        # Extract recent processed emails (mock data for now)
        recent_emails = await _get_recent_processed_emails()
        
        # Format for Make.com
        formatted_data = {
            "total_processed": len(recent_emails),
            "emails": [
                {
                    "id": email["id"],
                    "subject": email["subject"][:50],  # Truncate for readability
                    "classification": email["classification"],
                    "confidence": email["confidence"],
                    "processed_at": email["processed_at"]
                }
                for email in recent_emails[:5]  # Limit to 5 most recent
            ],
            "summary_message": f"📊 Processed {len(recent_emails)} emails in the last 15 minutes",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        logger.info(f"Make.com webhook processed: {len(recent_emails)} emails")
        
        return WebhookResponse(
            success=True,
            message="Recent emails retrieved successfully",
            event_id=f"make_{hash(str(payload.request_data)) % 100000}",
            data=formatted_data
        )
        
    except Exception as e:
        logger.error(f"Make.com webhook error: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Make.com webhook failed: {str(e)}"
        )


def _handle_email_processed(data: Dict[str, Any]) -> Dict[str, Any]:
    """Handle email processing completion events."""
    return {
        "email_id": data.get("email_id"),
        "classification": data.get("classification"),
        "summary": data.get("summary", "")[:100],  # Truncate for Slack
        "confidence": data.get("confidence", 0),
        "status": "completed",
        "notification_text": f"📧 Email {data.get('email_id')} processed - {data.get('classification', 'Unknown')}"
    }


def _handle_agent_completed(data: Dict[str, Any]) -> Dict[str, Any]:
    """Handle agent completion events."""
    return {
        "agent": data.get("agent_name"),
        "email_id": data.get("email_id"),
        "execution_time": data.get("execution_time", 0),
        "status": "completed",
        "notification_text": f"🤖 Agent {data.get('agent_name')} completed processing"
    }


def _handle_error_occurred(data: Dict[str, Any]) -> Dict[str, Any]:
    """Handle error events that need attention."""
    return {
        "error_type": data.get("error_type"),
        "component": data.get("component"),
        "severity": data.get("severity", "medium"),
        "notification_text": f"🚨 Error in {data.get('component')}: {data.get('error_type')}"
    }


async def _get_recent_processed_emails() -> list[Dict[str, Any]]:
    """Get emails processed in the last 15 minutes.
    
    TODO: Replace with actual database query when integrating with orchestrator.
    For now, returns mock data for testing purposes.
    """
    # Mock data for testing - will be replaced with real database query
    mock_emails = [
        {
            "id": "email_001",
            "subject": "Customer inquiry about pricing",
            "classification": "support_request",
            "confidence": 0.89,
            "processed_at": datetime.utcnow().isoformat()
        },
        {
            "id": "email_002", 
            "subject": "Meeting request for next week",
            "classification": "meeting_request",
            "confidence": 0.95,
            "processed_at": datetime.utcnow().isoformat()
        }
    ]
    
    logger.info(f"Retrieved {len(mock_emails)} recent processed emails (mock data)")
    return mock_emails


@router.get("/health")
async def webhook_health_check():
    """Health check endpoint for webhook service."""
    return {
        "status": "healthy",
        "service": "webhooks",
        "endpoints": ["/zapier", "/make"],
        "timestamp": datetime.utcnow().isoformat()
    }