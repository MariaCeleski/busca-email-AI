# 🎬 Demo Zapier + Slack para Vídeo - AI Email Agent System

## 🎯 **Objetivo da Demonstração**
Mostrar como o sistema AI Email Agent automaticamente notifica equipes via Slack através do Zapier quando emails são processados, demonstrando integração real de **Low-Code/No-Code**.

---

## 📋 **Preparação Antes da Gravação**

### **1. Verificar Configurações**
```bash
# No backend/.env - confirmar configurações
ENABLE_WEBHOOKS=true
ZAPIER_WEBHOOK_URL=https://hooks.zapier.com/hooks/catch/28584917/4t5ocoi/
```

### **2. Testar Webhook Manualmente**
```bash
curl -X POST "https://hooks.zapier.com/hooks/catch/28584917/4t5ocoi/" \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "demo_test",
    "timestamp": "2024-08-19T21:30:00Z",
    "email": {
      "subject": "Teste de Integração Zapier",
      "sender": "demo@exemplo.com"
    },
    "system": {
      "model_used": "gpt-4o-mini",
      "environment": "development"
    }
  }'
```

### **3. Abrir Abas Necessárias**
- **Aba 1**: Slack (canal onde chegam as notificações)
- **Aba 2**: Dashboard AI Email Agent (`http://localhost:3001`)
- **Aba 3**: Terminal com curl para testes manuais
- **Aba 4**: Zapier Dashboard (histórico de execuções)

---

## 🎬 **Roteiro de Demonstração (5-7 minutos)**

### **CENA 1: Explicação da Integração (1 minuto)**
**FALAR:**
> "Agora vou demonstrar uma das funcionalidades mais importantes para empresas: a integração com plataformas **Low-Code** como Zapier. Isso permite que qualquer pessoa, sem conhecimento de programação, configure automações quando o sistema processa emails."

**MOSTRAR:**
- Diagrama simples: `AI System → Webhook → Zapier → Slack`
- Mencionar que está configurado para notificar automaticamente

### **CENA 2: Configuração Zapier (30 segundos)**
**FALAR:**
> "Já tenho configurado um Zap que conecta nosso sistema ao Slack. Quando o sistema termina de processar um email, envia automaticamente uma notificação."

**MOSTRAR:**
- Zapier dashboard com o Zap ativo
- URL do webhook já configurada
- Mostrar que está conectado ao Slack

### **CENA 3: Demonstração ao Vivo (3 minutos)**

#### **3.1 Teste Manual (1 minuto)**
**FALAR:**
> "Primeiro, vou simular manualmente o envio de uma notificação para mostrar que a integração funciona."

**EXECUTAR:**
```bash
curl -X POST "https://hooks.zapier.com/hooks/catch/28584917/4t5ocoi/" \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "demo_test",
    "timestamp": "2024-08-19T21:30:00Z",
    "email": {
      "subject": "🎬 Teste para Vídeo Demo",
      "sender": "apresentacao@faculdade.edu"
    },
    "classification": {
      "category": "Academic",
      "priority": "High",
      "confidence": 0.95
    },
    "system": {
      "model_used": "gpt-4o-mini",
      "environment": "production"
    }
  }'
```

**MOSTRAR:**
- Terminal executando o comando
- Response: `200 OK`
- **IMEDIATAMENTE** mostrar Slack recebendo a notificação
- Destacar os dados que aparecem na mensagem

#### **3.2 Processamento Real (2 minutos)**
**FALAR:**
> "Agora vou processar um email real através do sistema para mostrar como a automação funciona na prática."

**EXECUTAR:**
1. **No Dashboard**: Clicar em "Buscar E-mails" ou "Demo"
2. **Aguardar**: Sistema processar (classificar → resumir → resposta)
3. **Mostrar**: Em tempo real, conforme cada agente termina:
   - Notificação no Slack: "🤖 Classifier Agent completed"
   - Notificação no Slack: "📝 Summarizer Agent completed" 
   - Notificação no Slack: "📧 Email Processing Complete"

**DESTACAR:**
- Cada etapa gera uma notificação automática
- Dados estruturados chegam no Slack
- **Zero código** necessário para configurar
- Equipe é notificada imediatamente

### **CENA 4: Análise dos Resultados (1 minuto)**
**FALAR:**
> "Como podem ver, a integração funciona perfeitamente. Vejam no Zapier o histórico de execuções bem-sucedidas."

**MOSTRAR:**
- **Zapier History**: Lista de execuções recentes (todas success)
- **Slack Thread**: Múltiplas mensagens recebidas
- **Dashboard**: Emails processados com sucesso

### **CENA 5: Benefícios Empresariais (30 segundos)**
**FALAR:**
> "Essa integração permite que empresas conectem nosso sistema a **centenas** de outras ferramentas: CRM, Planilhas Google, Microsoft Teams, Discord, Email, SMS - tudo sem programação."

**MOSTRAR:**
- Zapier app directory (mencionar 5000+ apps)
- Possibilidades: "Slack, Microsoft Teams, Google Sheets, Salesforce, etc."

---

## 📱 **Mensagens que Aparecerão no Slack**

### **Teste Manual**
```
🎬 **Demo Test Received**

📧 **Email**: 🎬 Teste para Vídeo Demo
👤 **From**: apresentacao@faculdade.edu  
🏷️ **Category**: Academic (95% confidence)
⚡ **Priority**: High
🤖 **Model**: gpt-4o-mini
```

### **Agente Completado**
```
🤖 **AI Agent Completed**

🔧 **Agent**: classifier
📧 **Email ID**: email_123456789
🎯 **Result**: Urgent (95% confidence)
⏰ **Time**: 2024-08-19 21:35:42
```

### **Email Processado Completo**
```
✅ **Email Processing Complete**

📧 **Subject**: Urgente: Problema com faturamento
👤 **Sender**: cliente@empresa.com
🏷️ **Classification**: Urgent/High (95%)
📝 **Summary**: Cliente relata cobrança duplicada...
💬 **Draft Reply**: Prezado cliente, recebemos sua solicitação...
🕐 **Processed**: 2024-08-19 21:35:45
```

---

## 🎥 **Dicas para Gravação**

### **Timing**
- **Teste Manual**: 30 segundos para executar + aguardar Slack
- **Processamento Real**: 45-60 segundos (aguardar pipeline completo)
- **Mostrar Zapier History**: 15 segundos
- **Total**: ~3-4 minutos de demo prática

### **Transições Suaves**
1. **Alt+Tab** rápido entre: Terminal → Slack → Dashboard → Zapier
2. **Mostrar cursor** clicando nos elementos importantes
3. **Pausar 2-3 segundos** depois que notificação chega no Slack
4. **Narrar** o que está acontecendo em tempo real

### **Pontos Críticos**
- ✅ **Slack deve estar visível** quando notificação chegar
- ✅ **Zapier History** deve mostrar execuções success (verde)
- ✅ **Dashboard** deve mostrar emails sendo processados
- ✅ **Terminal** deve mostrar `200 OK` response

---

## 🔧 **Comandos de Teste Rápido**

### **Verificar se Webhook Está Funcionando**
```bash
curl -X POST "https://hooks.zapier.com/hooks/catch/28584917/4t5ocoi/" \
  -H "Content-Type: application/json" \
  -d '{"test": true, "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"}'
```

### **Simular Email Urgente**
```bash
curl -X POST "https://hooks.zapier.com/hooks/catch/28584917/4t5ocoi/" \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "email_processed",
    "email": {
      "subject": "🚨 URGENTE: Sistema Fora do Ar",
      "sender": "ops@empresa.com"
    },
    "classification": {"category": "Urgent", "priority": "Critical", "confidence": 0.99},
    "summary": {"summary": "Sistema principal apresenta instabilidade crítica"},
    "draft_reply": {"subject": "Re: Sistema sendo verificado", "body": "Equipe técnica já foi acionada..."}
  }'
```

### **Simular Erro**
```bash
curl -X POST "https://hooks.zapier.com/hooks/catch/28584917/4t5ocoi/" \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "error_occurred",
    "error": {
      "component": "classifier",
      "message": "Timeout after 3 retries",
      "severity": "high"
    },
    "email": {"subject": "Email Problemático", "sender": "test@demo.com"}
  }'
```

---

## 📊 **Métricas de Sucesso**

**Durante a gravação, destacar:**
- ✅ **Latência baixa**: Notificação chega em < 3 segundos
- ✅ **100% delivery**: Todas as notificações chegam
- ✅ **Dados estruturados**: JSON completo no Slack
- ✅ **Zero erros**: Zapier History mostra success
- ✅ **Escalabilidade**: Suporta múltiplos channels/apps

---

## 🎯 **Resultado Esperado**

Ao final da demonstração, ficará claro:

1. **✅ Integração Real**: Sistema realmente se conecta com ferramentas externas
2. **✅ Zero Código**: Qualquer pessoa pode configurar automações
3. **✅ Tempo Real**: Notificações chegam instantaneamente  
4. **✅ Dados Ricos**: Informações completas sobre classificação, resumo, etc.
5. **✅ Escalável**: Pode ser expandido para centenas de outras ferramentas
6. **✅ Empresarial**: Atende requisito 4.9 de Low-Code/No-Code do SCTEC

**Impacto:** Demonstração clara de como IA + Automação Low-Code criam valor empresarial real.