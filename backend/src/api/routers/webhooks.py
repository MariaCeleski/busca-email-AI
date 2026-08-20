"""Webhook endpoints for low-code integrations (Zapier, Make.com).

Provides endpoints to receive webhook calls from external automation platforms
and send data to them, enabling no-code workflow automation.

Validates: Requirements 4.9 (Low-Code/No-Code Integration)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


# --- Request/Response models ---

class ZapierPayload(BaseModel):
    """Payload structure for Zapier webhooks."""
    
    event_type: str = Field(..., description="Type of event (email_processed, agent_completed, error)")
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    
    # Email data
    email: Optional[Dict[str, Any]] = Field(None, description="Email processing result")
    
    # System data
    system: Optional[Dict[str, Any]] = Field(None, description="System metadata")
    
    # Error data (for error events)
    error: Optional[Dict[str, Any]] = Field(None, description="Error information")


class MakePayload(BaseModel):
    """Payload structure for Make.com webhooks."""
    
    trigger_type: str = Field(..., description="Type of trigger")
    data: Dict[str, Any] = Field(..., description="Event data")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class WebhookResponse(BaseModel):
    """Standard webhook response."""
    
    status: str
    message: str
    received_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


# --- Webhook Endpoints ---

@router.post("/zapier")
async def zapier_webhook(payload: ZapierPayload) -> WebhookResponse:
    """Receive webhook calls from Zapier automation.
    
    This endpoint receives data from the AI Email Agent system and forwards
    it to Zapier for automated workflow execution (Slack notifications, etc.).
    
    Expected payload structure:
    {
        "event_type": "email_processed",
        "email": {
            "id": "uuid",
            "sender": "email@example.com",
            "subject": "Email subject",
            "category": "Urgent",
            "priority": "High",
            "confidence": 0.95,
            "summary": "Brief email summary"
        },
        "system": {
            "processing_time": "2.3s",
            "model_used": "gpt-4o-mini"
        }
    }
    """
    try:
        logger.info(f"Received Zapier webhook: {payload.event_type}")
        
        # Log payload for debugging (without sensitive data)
        safe_payload = {
            "event_type": payload.event_type,
            "timestamp": payload.timestamp,
            "has_email": payload.email is not None,
            "has_system": payload.system is not None,
            "has_error": payload.error is not None
        }
        logger.info(f"Zapier payload structure: {safe_payload}")
        
        # Validate required fields based on event type
        if payload.event_type == "email_processed" and not payload.email:
            raise HTTPException(
                status_code=400, 
                detail="Email data required for email_processed event"
            )
        
        if payload.event_type == "error" and not payload.error:
            raise HTTPException(
                status_code=400,
                detail="Error data required for error event"
            )
        
        return WebhookResponse(
            status="success",
            message=f"Webhook received: {payload.event_type}"
        )
        
    except Exception as e:
        logger.error(f"Error processing Zapier webhook: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Webhook processing failed: {str(e)}")


@router.post("/make")
async def make_webhook(payload: MakePayload) -> WebhookResponse:
    """Receive webhook calls from Make.com automation.
    
    This endpoint receives data from Make.com scenarios for advanced
    visual workflow automation.
    """
    try:
        logger.info(f"Received Make.com webhook: {payload.trigger_type}")
        
        # Log payload structure
        logger.info(f"Make.com payload keys: {list(payload.data.keys())}")
        
        return WebhookResponse(
            status="success", 
            message=f"Make.com webhook received: {payload.trigger_type}"
        )
        
    except Exception as e:
        logger.error(f"Error processing Make.com webhook: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Webhook processing failed: {str(e)}")


# --- Test Endpoints ---

@router.post("/test/zapier")
async def test_zapier_webhook() -> WebhookResponse:
    """Send a test payload to Zapier webhook URL.
    
    Used for testing the integration during setup.
    """
    import httpx
    from src.config import get_settings
    
    settings = get_settings()
    
    if not settings.zapier_webhook_url:
        raise HTTPException(
            status_code=400,
            detail="Zapier webhook URL not configured. Set ZAPIER_WEBHOOK_URL in .env"
        )
    
    # Create test payload
    test_payload = {
        "event_type": "email_processed",
        "timestamp": datetime.utcnow().isoformat(),
        "email": {
            "id": "test-email-123",
            "sender": "teste@exemplo.com",
            "subject": "🧪 Teste de Integração Zapier",
            "category": "Urgent",
            "priority": "High", 
            "confidence": 0.98,
            "summary": "Este é um teste da integração com Zapier. Se você está vendo isso no Slack, funcionou! 🎉"
        },
        "system": {
            "processing_time": "1.2s",
            "model_used": "gpt-4o-mini",
            "environment": "test"
        }
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                settings.zapier_webhook_url,
                json=test_payload,
                headers={"Content-Type": "application/json"}
            )
            
        if response.status_code == 200:
            logger.info("Test payload sent to Zapier successfully")
            return WebhookResponse(
                status="success",
                message=f"Test payload sent to Zapier (status: {response.status_code})"
            )
        else:
            logger.warning(f"Zapier returned status {response.status_code}: {response.text}")
            return WebhookResponse(
                status="warning",
                message=f"Zapier returned status {response.status_code}, but webhook may still work"
            )
            
    except httpx.TimeoutException:
        raise HTTPException(status_code=408, detail="Timeout connecting to Zapier webhook")
    except Exception as e:
        logger.error(f"Failed to send test to Zapier: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to send test: {str(e)}")


@router.get("/health")
async def webhook_health() -> Dict[str, Any]:
    """Check webhook system health and configuration."""
    from src.config import get_settings
    
    settings = get_settings()
    
    return {
        "status": "healthy",
        "webhooks_enabled": settings.enable_webhooks,
        "zapier_configured": bool(settings.zapier_webhook_url),
        "make_configured": bool(settings.make_webhook_url),
        "endpoints": {
            "zapier": "/api/v1/webhooks/zapier",
            "make": "/api/v1/webhooks/make",
            "test_zapier": "/api/v1/webhooks/test/zapier"
        }
    }