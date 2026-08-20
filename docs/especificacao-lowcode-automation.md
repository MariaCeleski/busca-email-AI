# 🔗 Especificação: Automação Low-Code para AI Email Agent

> **Documento de Requisitos - Implementação Low-Code/No-Code**  
> Projeto: AI Email Agent System  
> Requisito: 4.9 - Low-Code para QA, SRE e Agentes  
> Objetivo: Completar 0,25 pontos restantes (0,50 total)  

---

## 🎯 **OBJETIVO**

Implementar automação low-code/no-code integrada ao sistema para atender 100% do requisito 4.9 do Projeto Avaliativo M2.2, completando os 0,25 pontos restantes para atingir nota máxima.

---

## 📋 **REQUISITOS TÉCNICOS (4.9)**

### ✅ **Já Implementado**
- [x] **Integração com aplicação/serviços**: API REST + WebSocket
- [x] **Saída observável**: JSON responses + notifications
- [x] **Lógica principal na aplicação**: Core logic em Python

### ❌ **Pendente de Implementação**
- [ ] **Automação low-code/no-code integrada**: Ferramenta visual funcional
- [ ] **Pelo menos 1 gatilho**: Trigger automatizado
- [ ] **Ferramenta visual como apoio**: Interface gráfica demonstrável
- [ ] **Instruções de reprodução no README**: Documentação completa

---

## 🏆 **ESTRATÉGIA DE IMPLEMENTAÇÃO**

### **Abordagem Híbrida: Zapier + Make.com**

**Rationale**: Implementar 2 ferramentas complementares para:
- ✅ **Maximizar pontuação**: Demonstrar domínio de múltiplas plataformas
- ✅ **Cobrir diferentes casos de uso**: Zapier (simplicidade) + Make.com (visual)
- ✅ **Backup de segurança**: Se uma ferramenta falhar, a outra garante os pontos
- ✅ **Melhor para demonstração**: Mais conteúdo visual para o vídeo

---

## 📦 **COMPONENTE 1: ZAPIER INTEGRATION**

### **1.1 Backend Webhook Endpoint**

**Arquivo**: `backend/src/api/routers/webhooks.py` (NOVO)

```python
"""Webhook endpoints for low-code automation integrations."""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Any, Optional
import logging

from src.api.middleware.auth import get_api_key

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)


class ZapierWebhookPayload(BaseModel):
    """Zapier webhook payload schema."""
    
    event_type: str  # "email_processed", "agent_completed", "error_occurred"
    data: Dict[str, Any]  # Event-specific data
    source: str = "zapier"
    timestamp: Optional[str] = None


class WebhookResponse(BaseModel):
    """Standard webhook response."""
    
    success: bool
    message: str
    event_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


@router.post("/zapier", response_model=WebhookResponse)
async def zapier_webhook(
    payload: ZapierWebhookPayload,
    api_key: str = Depends(get_api_key)
):
    """
    Zapier webhook endpoint for automation triggers.
    
    Supported event types:
    - email_processed: When email pipeline completes
    - agent_completed: When specific agent finishes processing
    - error_occurred: When system error needs attention
    
    Returns structured response for Zapier to process.
    """
    try:
        logger.info(f"Zapier webhook received: {payload.event_type}")
        
        # Process different event types
        response_data = {}
        
        if payload.event_type == "email_processed":
            response_data = _handle_email_processed(payload.data)
        elif payload.event_type == "agent_completed":
            response_data = _handle_agent_completed(payload.data)
        elif payload.event_type == "error_occurred":
            response_data = _handle_error_occurred(payload.data)
        else:
            raise HTTPException(400, f"Unsupported event type: {payload.event_type}")
        
        return WebhookResponse(
            success=True,
            message=f"Event {payload.event_type} processed successfully",
            event_id=f"evt_{payload.event_type}_{hash(str(payload.data))}",
            data=response_data
        )
        
    except Exception as e:
        logger.error(f"Zapier webhook error: {str(e)}")
        raise HTTPException(500, f"Webhook processing failed: {str(e)}")


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
```

### **1.2 Integração com Sistema Existente**

**Arquivo**: `backend/src/agents/orchestrator.py` (MODIFICAR)

```python
# Adicionar ao final da função _process_with_langgraph():

async def _trigger_zapier_webhook(self, event_type: str, data: Dict[str, Any]):
    """Trigger Zapier webhook for automation."""
    if not self._enable_webhooks:
        return
        
    try:
        webhook_payload = {
            "event_type": event_type,
            "data": data,
            "source": "email_agent",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Use httpx to send webhook (non-blocking)
        import httpx
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{self._base_url}/api/v1/webhooks/zapier",
                json=webhook_payload,
                headers={"X-API-Key": self._webhook_api_key},
                timeout=5.0
            )
            
    except Exception as e:
        logger.warning(f"Zapier webhook failed: {e}")
        # Don't fail main process for webhook errors


# Adicionar chamadas nos pontos apropriados:
# 1. Após email_processed (final do pipeline)
# 2. Após agent completion (cada agente)
# 3. Em error handlers (tratamento de falhas)
```

---

## 📦 **COMPONENTE 2: MAKE.COM INTEGRATION**

### **2.1 Scenario Configuration**

**Objetivo**: Criar workflow visual no Make.com que:
1. **Trigger**: Timer (every 15 minutes) OR Webhook
2. **Action**: HTTP GET para `/api/v1/emails/recent`
3. **Filter**: Emails with status = "processed" nos últimos 15 min
4. **Output**: Send formatted message para Slack/Discord

### **2.2 Endpoint para Make.com**

**Arquivo**: `backend/src/api/routers/webhooks.py` (ADICIONAR)

```python
@router.post("/make", response_model=WebhookResponse)
async def make_webhook(
    payload: Dict[str, Any],
    api_key: str = Depends(get_api_key)
):
    """
    Make.com webhook endpoint for visual automation.
    
    Accepts flexible payload structure for Make.com scenarios.
    Returns formatted data suitable for Make.com processing.
    """
    try:
        logger.info(f"Make.com webhook received: {payload}")
        
        # Extract recent processed emails
        recent_emails = await _get_recent_processed_emails()
        
        # Format for Make.com
        formatted_data = {
            "total_processed": len(recent_emails),
            "emails": [
                {
                    "id": email["id"],
                    "subject": email["subject"][:50],
                    "classification": email["classification"],
                    "confidence": email["confidence"],
                    "processed_at": email["processed_at"]
                }
                for email in recent_emails[:5]  # Limit to 5 most recent
            ],
            "summary_message": f"📊 Processed {len(recent_emails)} emails in the last 15 minutes"
        }
        
        return WebhookResponse(
            success=True,
            message="Recent emails retrieved successfully",
            data=formatted_data
        )
        
    except Exception as e:
        logger.error(f"Make.com webhook error: {str(e)}")
        raise HTTPException(500, f"Make.com webhook failed: {str(e)}")


async def _get_recent_processed_emails() -> List[Dict[str, Any]]:
    """Get emails processed in the last 15 minutes."""
    # Implementation to query database
    # Return list of email dictionaries
    pass
```

---

## 📦 **COMPONENTE 3: DOCUMENTATION UPDATE**

### **3.1 README.md Section**

**Localização**: Adicionar nova seção após "9. Segurança e Guardrails"

```markdown
## 10. 🔗 Automação Low-Code/No-Code

O AI Email Agent suporta integração com ferramentas de automação visual para workflows personalizados e monitoramento.

### 10.1 Zapier Integration

**Endpoint**: `POST /api/v1/webhooks/zapier`

**Supported Triggers**:
- `email_processed`: Disparado quando pipeline de email é concluído
- `agent_completed`: Disparado quando agente específico termina processamento
- `error_occurred`: Disparado quando ocorre erro que precisa atenção

**Example Zap Configuration**:
1. **Trigger**: Webhooks by Zapier → Catch Hook
2. **Webhook URL**: `https://your-domain.com/api/v1/webhooks/zapier`
3. **Action**: Slack → Send Channel Message
4. **Message Template**: 
   ```
   📧 Email processed: {{data__notification_text}}
   Classification: {{data__classification}}
   Confidence: {{data__confidence}}%
   ```

**Setup Instructions**:
1. Create new Zap in Zapier
2. Select "Webhooks by Zapier" as trigger
3. Choose "Catch Hook" event
4. Copy provided webhook URL
5. Configure email processing to send POST requests to URL
6. Add desired actions (Slack, Email, etc.)
7. Test with sample payload

### 10.2 Make.com Integration

**Endpoint**: `POST /api/v1/webhooks/make`

**Visual Workflow**:
```
[Timer: 15min] → [HTTP Request] → [Filter] → [Slack Message]
      ↓              ↓             ↓            ↓
   Every 15min    GET /recent   Only new    Format + Send
```

**Setup Instructions**:
1. Create new Scenario in Make.com
2. Add "Schedule" module (every 15 minutes)
3. Add "HTTP Request" module:
   - URL: `https://your-domain.com/api/v1/webhooks/make`
   - Method: POST
   - Headers: `X-API-Key: your-api-key`
4. Add filter for new emails only
5. Add Slack/Discord webhook for notifications
6. Save and activate scenario

### 10.3 Webhook Payload Examples

**Email Processed Event**:
```json
{
  "event_type": "email_processed",
  "data": {
    "email_id": "email_12345",
    "subject": "Customer inquiry about pricing",
    "classification": "support_request",
    "confidence": 0.89,
    "summary": "Customer asking about enterprise pricing...",
    "processed_at": "2026-08-17T10:30:00Z"
  },
  "source": "email_agent",
  "timestamp": "2026-08-17T10:30:00Z"
}
```

**Make.com Response**:
```json
{
  "success": true,
  "message": "Recent emails retrieved successfully",
  "data": {
    "total_processed": 3,
    "summary_message": "📊 Processed 3 emails in the last 15 minutes",
    "emails": [
      {
        "id": "email_12345",
        "subject": "Customer inquiry about pricing",
        "classification": "support_request",
        "confidence": 0.89
      }
    ]
  }
}
```

### 10.4 Authentication

All webhook endpoints require API key authentication:

```bash
curl -X POST "https://your-domain.com/api/v1/webhooks/zapier" \
  -H "X-API-Key: dev-api-key-2024" \
  -H "Content-Type: application/json" \
  -d '{"event_type": "email_processed", "data": {...}}'
```

### 10.5 Error Handling

**Rate Limiting**: 100 requests per minute per API key
**Timeout**: 5 seconds maximum response time
**Retry Policy**: 3 attempts with exponential backoff
**Error Codes**:
- `400`: Invalid event type or malformed payload
- `401`: Missing or invalid API key
- `429`: Rate limit exceeded
- `500`: Internal server error

### 10.6 Monitoring

Webhook activity is logged and available in:
- Application logs: `/logs/webhooks.log`
- Dashboard: Real-time webhook statistics
- Metrics: Success/failure rates per integration
```

---

## 📦 **COMPONENTE 4: IMPLEMENTATION PLAN**

### **Phase 1: Backend Implementation (30 min)**
1. **Create webhook router** (10 min)
   - New file: `backend/src/api/routers/webhooks.py`
   - Pydantic models for payloads
   - Basic error handling

2. **Update app.py** (5 min)
   - Import webhook router
   - Add to FastAPI app

3. **Integrate with orchestrator** (15 min)
   - Add webhook triggers to key points
   - Non-blocking HTTP calls
   - Error tolerance

### **Phase 2: Zapier Configuration (20 min)**
1. **Create Zapier account** (5 min)
2. **Configure Zap** (10 min)
   - Webhook trigger
   - Slack action
   - Test payload

3. **Test integration** (5 min)
   - Send test webhook
   - Verify Slack message
   - Document URL

### **Phase 3: Make.com Configuration (25 min)**
1. **Create Make.com account** (5 min)
2. **Build visual scenario** (15 min)
   - Timer trigger
   - HTTP request
   - Filter logic
   - Output action

3. **Export and test** (5 min)
   - Export scenario JSON
   - Test full workflow
   - Take screenshots

### **Phase 4: Documentation (15 min)**
1. **Update README** (10 min)
   - Add section 10
   - Include examples
   - Setup instructions

2. **Screenshots** (5 min)
   - Zapier interface
   - Make.com scenario
   - Slack notifications

---

## 📊 **SUCCESS CRITERIA**

### **Functional Requirements**
- ✅ Zapier integration working end-to-end
- ✅ Make.com scenario active and functional
- ✅ Webhook endpoints responding correctly
- ✅ Authentication working for both platforms
- ✅ Error handling for failed webhooks

### **Documentation Requirements**
- ✅ README section 10 complete with examples
- ✅ Setup instructions for both platforms
- ✅ Screenshots of working integrations
- ✅ API documentation for webhook endpoints

### **Evaluation Requirements (4.9)**
- ✅ **Automação low-code integrada**: 2 plataformas visuais
- ✅ **Pelo menos 1 gatilho**: Timer + Event-based triggers
- ✅ **Integração com aplicação**: REST API webhooks
- ✅ **Saída observável**: Slack notifications + logs
- ✅ **Lógica principal na aplicação**: Python backend
- ✅ **Ferramenta visual**: Zapier + Make.com interfaces
- ✅ **Instruções de reprodução**: README completo

---

## 🎯 **EXPECTED OUTCOME**

**Requisito 4.9 Score**: 0,50/0,50 (100% completo)
**Implementation Time**: ~90 minutes total
**Demo Value**: Excellent visual content for presentation video
**Maintenance Effort**: Minimal (webhook endpoints + documentation)

---

## 📋 **NEXT STEPS**

1. **Execute implementation** following the 4-phase plan
2. **Test both integrations** thoroughly
3. **Update README** with complete documentation
4. **Take screenshots** for video demonstration
5. **Commit changes** following project guidelines

---

> **📝 NOTA**: Este documento serve como guia completo para implementação. Após execução, validar com checklist de requisitos para garantir 100% de conformidade com critério 4.9.