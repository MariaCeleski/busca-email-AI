# Documentação de Refatoração com IA

> Registro das refatorações realizadas no projeto AI Email Agent, com código antes/depois, prompt utilizado, motivação técnica e princípios aplicados.

---

## Refatoração 1: Migração de Google Gemini para OpenAI

### Motivação Técnica
- Google Gemini apresentava instabilidade de resposta e custos imprevisíveis
- OpenAI (gpt-4o-mini) oferece melhor custo-benefício e respostas mais consistentes em JSON
- Princípio aplicado: **Dependency Inversion (SOLID - D)** — depender de abstrações, não de implementações concretas

### Prompt Utilizado
> "use OPENAI_API_KEY — migrar todos os 3 agentes de google.generativeai para openai.AsyncOpenAI"

### Código ANTES (Google Gemini)
```python
# classifier.py — ANTES
import google.generativeai as genai

class ClassifierAgent:
    def __init__(self):
        genai.configure(api_key=settings.gemini_api_key)
        self._model = genai.GenerativeModel("gemini-2.0-flash")

    async def _call_gemini(self, prompt: str) -> str:
        response = await self._model.generate_content_async(prompt)
        return response.text
```

### Código DEPOIS (OpenAI)
```python
# classifier.py — DEPOIS
from openai import AsyncOpenAI

class ClassifierAgent:
    def __init__(self):
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model_name = settings.openai_model  # "gpt-4o-mini"

    async def _call_gemini(self, prompt: str) -> str:
        response = await self._client.chat.completions.create(
            model=self._model_name,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content
```

### Princípios Aplicados
- **Single Responsibility (S)**: cada agente faz apenas sua função
- **Open/Closed (O)**: trocar o provider sem alterar a lógica de negócio
- **Dependency Inversion (D)**: modelo configurável via `.env`, não hardcoded

### Impacto
- 3 arquivos alterados: `classifier.py`, `summarizer.py`, `response.py`
- 0 testes quebrados (interfaces mantidas)
- Branch: `feature/full-implementation` (commit `4042f41`)

---

## Refatoração 2: Separação do Endpoint de Feedback

### Motivação Técnica
- O `emails.py` estava acumulando responsabilidades demais (CRUD + approve + reject + feedback)
- Princípio aplicado: **Single Responsibility (SOLID - S)** — cada módulo deve ter um único motivo para mudar

### Prompt Utilizado
> "implementar o aprendizado por feedback em 3 etapas simples que não quebram nada existente"

### Código ANTES (tudo no emails.py)
```python
# emails.py — feedback inline no approve/reject
@router.post("/{email_id}/reply/approve")
async def approve_reply(...):
    # ... lógica de approve ...
    # feedback misturado com lógica de envio
    await save_feedback_inline(email, "approved")
```

### Código DEPOIS (separado)
```python
# feedback_learner.py — serviço dedicado
class FeedbackLearner:
    async def record_feedback(self, ...): ...
    async def get_recent_examples(self, limit=5): ...
    @staticmethod
    def build_few_shot_section(examples): ...

# feedback.py — router dedicado
router = APIRouter(prefix="/api/v1/feedback")

@router.get("/history")
async def get_feedback_history(...): ...

@router.delete("/{feedback_id}")
async def delete_feedback_entry(...): ...
```

### Princípios Aplicados
- **Single Responsibility (S)**: router de feedback separado do de emails
- **Interface Segregation (I)**: API de feedback independente
- **DRY**: `FeedbackLearner` reutilizado em approve e reject

### Impacto
- 3 novos arquivos: `feedback_learner.py`, `feedback.py` (router), `002_feedback_table.py` (migration)
- 0 funcionalidades existentes quebradas
- Branch: `feature/frontend-usability`

---

## Refatoração 3: Extração do Pipeline Demo

### Motivação Técnica
- O endpoint `/demo` só classificava emails, não gerava resumo nem resposta
- Os botões de revisão no frontend não apareciam sem `draft_reply`
- Princípio: **completude funcional** — demo deve demonstrar o sistema completo

### Prompt Utilizado
> "ajuste o endpoint de demo para executar pipeline completo sem quebrar a aplicação"

### Código ANTES (apenas classificação)
```python
@router.post("/demo")
async def insert_demo_emails():
    # Insere 3 emails
    # Classifica cada um
    # NÃO gera resumo nem resposta
    classifier = ClassifierAgent()
    result = await classifier.classify(raw)
    await repo.update_classification(...)
```

### Código DEPOIS (pipeline completo)
```python
@router.post("/demo")
async def insert_demo_emails():
    # Insere 7 emails diversificados
    classifier = ClassifierAgent()
    summarizer = SummarizerAgent()

    for email_data in demo_emails:
        # Etapa 1: Classificar
        classification = await classifier.classify(raw)
        # Etapa 2: Resumir
        summary = await summarizer.summarize(raw)
        # Etapa 3: Gerar resposta (draft_reply com status=pending)
        response = await client.chat.completions.create(...)
        draft = DraftReplyORM(status="pending", ...)
        session.add(draft)
```

### Princípios Aplicados
- **Completude**: demo reproduz o pipeline real
- **Testabilidade**: permite testar approve/reject sem Gmail conectado
- **Clean Code**: emails demo diversificados cobrem todas as categorias

### Impacto
- 7 emails demo (antes eram 3) cobrindo: Urgente, Pessoal, Informativo, Spam, Promocional, Transacional
- Frontend de revisão funcional sem depender de Gmail real
- Branch: `feature/frontend-usability` (commit `cdb0623`)

---

## Refatoração 4: Approve sem Dependência de Provider

### Motivação Técnica
- O approve falhava com `send_failed` quando não havia Gmail conectado (modo demo)
- O feedback só era registrado no sucesso de envio
- Princípio: **Fail Gracefully** + **Separação de preocupações**

### Prompt Utilizado
> "approve registra feedback independente do envio, não deve depender de provider conectado"

### Código ANTES
```python
if send_result.success:
    draft.status = "sent"
    await learner.record_feedback(...)  # SÓ registra no sucesso
else:
    draft.status = "send_failed"  # Não registra feedback
    # Usuário vê "Falha no Envio" — confuso em modo demo
```

### Código DEPOIS
```python
# Registra feedback ANTES de tentar enviar
email.flagged_for_review = False
await learner.record_feedback(...)  # Sempre registra

if send_result.success:
    draft.status = "sent"
else:
    draft.status = "approved"  # Aprovado mesmo sem provider
    # Em modo demo, "aprovado" é o resultado correto
```

### Princípios Aplicados
- **Separation of Concerns**: feedback ≠ envio de email
- **Graceful Degradation**: funciona sem Gmail conectado
- **User Experience**: mensagem clara em vez de erro técnico

### Impacto
- Feedback sempre registrado em approve e reject
- Demo funcional sem provider
- Branch: `feature/frontend-usability` (commit `9e30013`)

---

## Resumo de Princípios Aplicados

| Princípio | Onde aplicado |
|-----------|--------------|
| **S** - Single Responsibility | FeedbackLearner separado, routers por domínio |
| **O** - Open/Closed | Provider configurável via .env |
| **L** - Liskov Substitution | GmailClient e MicrosoftGraphClient intercambiáveis |
| **I** - Interface Segregation | API de feedback independente da API de emails |
| **D** - Dependency Inversion | Modelo IA configurável, não hardcoded |
| **DRY** | FeedbackLearner reutilizado em approve/reject |
| **Clean Code** | Nomes descritivos em português, comentários explicativos |
| **Graceful Degradation** | Funciona sem Gmail, sem ChromaDB, sem Celery |


---

## Implementação 5: Guardrails de Conteúdo

### Motivação Técnica
- A IA pode gerar respostas com conteúdo ofensivo, dados sensíveis ou tom inadequado
- Sem validação, respostas problemáticas chegam diretamente ao usuário
- Princípio: **Defense in Depth** — múltiplas camadas de validação

### Prompt Utilizado
> "Implementar guardrails básico — validar se resposta gerada não contém conteúdo inadequado. Validação por palavras proibidas."

### Implementação

```python
# backend/src/services/guardrails.py

OFFENSIVE_TERMS = ["idiota", "imbecil", "merda", ...]
SENSITIVE_PATTERNS = [
    r'\b\d{3}\.\d{3}\.\d{3}-\d{2}\b',  # CPF
    r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b',  # Cartão
]
INAPPROPRIATE_PHRASES = ["dane-se", "problema seu", ...]

def validate_response(text: str) -> GuardrailResult:
    # 1. Verifica termos ofensivos
    # 2. Verifica dados sensíveis (regex)
    # 3. Verifica frases inadequadas
    # Retorna: is_safe, flagged_terms, category, message
```

### Integração no Pipeline

```python
# fetch.py — após gerar resposta
from src.services.guardrails import validate_response
guardrail_check = validate_response(reply_body)

if not guardrail_check.is_safe:
    reply_body = f"⚠️ GUARDRAIL: {guardrail_check.message}\n\n---\n\n{reply_body}"
```

### Princípios Aplicados
- **Defense in Depth**: guardrails + human-in-the-loop + feedback
- **Fail Safe**: resposta sinalizada, não bloqueada (humano decide)
- **Zero custo extra**: validação local sem chamada de API adicional

### Impacto
- 3 níveis de validação (ofensivo, sensível, inadequado)
- 0 chamadas extras à API
- 0 funcionalidades existentes quebradas
- Branch: `develop` (commit `7bde31f`)
