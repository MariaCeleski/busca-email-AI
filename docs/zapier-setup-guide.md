# 🔗 Guia de Configuração Zapier - AI Email Agent System

## Objetivo
Configurar integração Zapier para receber notificações automáticas quando emails são processados pelo sistema.

## Fluxo da Integração
**Webhook (Sistema) → Zapier → Slack/Discord/Email**

---

## 📋 Pré-requisitos

1. **Conta Zapier** (gratuita ou paga)
2. **Conta Slack** ou **Discord** para receber notificações
3. **Sistema AI Email Agent** rodando localmente
4. **ngrok** ou **similar** para expor localhost (opcional para testes)

---

## 🛠️ Configuração Passo-a-Passo

### Passo 1: Configurar Webhook no Zapier

1. **Acesse**: https://zapier.com/
2. **Crie um novo Zap**:
   - Clique em "Create Zap"
   - Nome sugerido: "AI Email Agent Notifications"

3. **Configure o Trigger**:
   - **App**: Webhooks by Zapier
   - **Event**: Catch Hook
   - **Clique em "Continue"**

4. **Copie a Webhook URL**:
   - Zapier fornecerá uma URL como:
   - `https://hooks.zapier.com/hooks/catch/XXXXX/YYYYY/`
   - **⚠️ Guarde esta URL - você vai precisar dela!**

### Passo 2: Configurar Action (Slack)

1. **Escolha App**: Slack
2. **Event**: Send Channel Message
3. **Account**: Conecte sua conta Slack
4. **Configure**:
   - **Channel**: #general ou canal desejado
   - **Message**: Usar dados do webhook (ver exemplos abaixo)

### Passo 3: Configurar Filtros (Opcional)

Para evitar spam, configure filtros:
- **Only continue if**: `event_type` contains `email_processed`
- **Or**: `agent_name` contains `classifier`

---

## 📝 Exemplos de Payloads

### Email Processado Completo
```json
{
  "event_type": "email_processed",
  "data": {
    "email_id": "email_123456789",
    "timestamp": "2024-08-18T15:30:00.000Z",
    "email": {
      "provider_message_id": "gmail_abc123",
      "sender": "cliente@exemplo.com",
      "subject": "Urgente: Problema com faturamento",
      "provider": "gmail"
    },
    "classification": {
      "category": "Urgent",
      "priority": "High",
      "confidence": 0.95,
      "requires_response": true
    },
    "summary": {
      "summary": "Cliente relata problema com cobrança duplicada...",
      "key_points": ["Cobrança duplicada", "Valor incorreto"]
    },
    "draft_reply": {
      "suggested_subject": "Re: Urgente: Problema com faturamento",
      "reply_body": "Prezado cliente, recebemos sua solicitação..."
    },
    "stage": "completed"
  },
  "source": "orchestrator",
  "timestamp": "2024-08-18T15:30:00.000Z"
}
```

### Agente Completado
```json
{
  "event_type": "agent_completed",
  "data": {
    "email_id": "email_123456789",
    "agent_name": "classifier",
    "timestamp": "2024-08-18T15:29:45.000Z",
    "classification": {
      "category": "Urgent",
      "priority": "High",
      "confidence": 0.95
    }
  },
  "source": "orchestrator"
}
```

### Erro Ocorrido
```json
{
  "event_type": "error_occurred",
  "data": {
    "email_id": "email_123456789",
    "error_type": "Classification failed after 3 retries: Timeout",
    "component": "orchestrator",
    "severity": "high",
    "timestamp": "2024-08-18T15:29:30.000Z"
  },
  "source": "orchestrator"
}
```

---

## 💬 Templates de Mensagens Slack

### Para Email Processado
```
📧 **Novo Email Processado**

**From:** {{data__email__sender}}
**Subject:** {{data__email__subject}}
**Classification:** {{data__classification__category}} ({{data__classification__confidence}})
**Stage:** {{data__stage}}

**Summary:** {{data__summary__summary}}

**Draft Reply:** {{data__draft_reply__suggested_subject}}
```

### Para Agente Completado
```
🤖 **Agent Completed**

**Agent:** {{data__agent_name}}
**Email:** {{data__email_id}}
**Result:** {{data__classification__category}} ({{data__classification__confidence}})
```

### Para Erro
```
🚨 **System Error**

**Component:** {{data__component}}
**Error:** {{data__error_type}}
**Severity:** {{data__severity}}
**Email:** {{data__email_id}}
```

---

## 🧪 Testes

### 1. Teste Manual via curl
```bash
curl -X POST "https://hooks.zapier.com/hooks/catch/XXXXX/YYYYY/" \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "email_processed",
    "data": {
      "email_id": "test_123",
      "classification": "urgent_request",
      "confidence": 0.95,
      "summary": "Teste de integração Zapier"
    },
    "source": "test"
  }'
```

### 2. Teste via Sistema
1. Configure a webhook URL no sistema
2. Processe um email real
3. Verifique notificação no Slack

---

## ⚙️ Configurações Avançadas

### Rate Limiting
- Zapier Free: 100 tasks/month
- Zapier Paid: 750+ tasks/month

### Error Handling
Configure no Zapier:
- **Retry on failure**: 3 tentativas
- **Delay between retries**: 1 minuto

### Filtros Recomendados
```
# Apenas emails processados com sucesso
data__stage = "completed"

# Apenas classificações de alta confiança
data__classification__confidence > 0.8

# Apenas categorias importantes
data__classification__category IN ["Urgent", "Personal"]
```

---

## 🔧 Troubleshooting

### Problema: Webhook não recebe dados
- ✅ Verificar URL copiada corretamente
- ✅ Sistema local acessível externamente (ngrok)
- ✅ Configuração ENABLE_WEBHOOKS=true no .env

### Problema: Slack não recebe mensagens
- ✅ Canal Slack existe e bot tem permissão
- ✅ Template de mensagem válido
- ✅ Campos do payload disponíveis

### Problema: Muitas notificações
- ✅ Adicionar filtros por event_type
- ✅ Filtrar por confidence > 0.8
- ✅ Limitar a categorias importantes

---

## 📸 Screenshots a Capturar

Para documentação final:

1. **Zapier Dashboard** - Lista de Zaps
2. **Zap Configuration** - Trigger setup
3. **Slack Integration** - Message template
4. **Test Success** - Zapier test result
5. **Slack Message** - Notificação recebida
6. **Zap History** - Execuções recentes

---

## 🎯 Resultado Esperado

Após configuração completa:
- ✅ Webhook URL configurada no sistema
- ✅ Zap ativo e funcionando
- ✅ Notificações Slack automáticas
- ✅ Testes manuais bem-sucedidos
- ✅ Screenshots documentados

**Status**: Pronto para configuração manual