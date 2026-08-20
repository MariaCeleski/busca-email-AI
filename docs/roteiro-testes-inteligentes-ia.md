# Roteiro de Implementação — Testes Inteligentes com IA

> Roteiro descritivo de como cada tópico do "Prompt de Testes Inteligentes com IA" (registrado em `docs/historico-prompts.md`, Prompt 35) pode ser aplicado ao projeto **AI Email Agent**, respeitando a stack existente (Python, FastAPI, LangGraph, React) sem introduzir ferramentas incompatíveis.
>
> Este documento é apenas um **plano** — nenhuma implementação foi feita ainda. Cada seção indica o que já existe, o que falta, e uma sugestão de próximo passo.

---

## 1. Arquitetura e Observabilidade de Agentes

**O que o prompt pede:** estruturar agentes escaláveis, logs, auditoria, rastreamento, métricas, observabilidade inteligente.

**O que já existe no projeto:**
- `AccessLoggingMiddleware` — loga todas as requisições HTTP
- Cada agente (`classifier.py`, `summarizer.py`, `response.py`) usa `logging.getLogger(__name__)` com `logger.warning`/`logger.error` em pontos de falha
- `EmailWorkflowState` rastreia `current_stage`, `error` e `retry_counts` por execução

**O que falta:**
- Logs estruturados (JSON) com campos padronizados (email_id, agent_name, duration_ms, status) em vez de strings livres
- Métricas agregadas (ex: taxa de erro por agente, tempo médio de resposta)

**Próximo passo sugerido:** criar um logger estruturado simples em `backend/src/services/` que padroniza os campos de log já emitidos pelos agentes, sem adicionar ferramenta externa (ex: sem Datadog/Prometheus).

---

## 2. IA para QA (Code Review e Testes de Aceitação)

**O que o prompt pede:** revisão de código inteligente, testes de aceitação com IA, testes orientados a risco.

**O que já existe no projeto:**
- 511 testes automatizados (unit + integration + property-based) em `backend/tests/`
- Testes cobrem os fluxos críticos: approve/reject, classificação, feedback, autenticação

**O que falta:**
- Testes de aceitação explícitos (Given/When/Then) documentados separadamente dos testes unitários
- Priorização formal por risco (matriz probabilidade × impacto) para decidir quais fluxos merecem mais cobertura

**Próximo passo sugerido:** criar `backend/tests/acceptance/` com cenários de aceitação em linguagem natural + código, focados nos fluxos de maior risco (envio de resposta, guardrails, autenticação).

---

## 3. Testes Automatizados Inteligentes

**O que o prompt pede:** geração de suítes de teste com IA, priorização por risco, testes E2E, ferramentas no-code.

**O que já existe:**
- Testes unitários e de integração gerados com apoio de IA (Kiro) durante o desenvolvimento
- `backend/tests/integration/test_pipeline_e2e.py` — teste E2E do pipeline completo

**O que falta:**
- Testes E2E do frontend (ex: Playwright/Cypress) — atualmente só há testes de backend
- Ferramentas no-code de automação — fora do escopo da stack atual (não há necessidade real de introduzir)

**Próximo passo sugerido:** se o objetivo é reforçar E2E, avaliar adicionar Playwright no frontend para cobrir o fluxo login → dashboard → aprovar resposta. Isso é uma decisão de escopo que precisa de confirmação, pois adiciona uma nova dependência de teste.

---

## 4. DevOps Inteligente e Detecção de Falhas

**O que o prompt pede:** explicação automática de logs via IA, detecção de anomalias em tempo real, previsão de falhas.

**O que já existe:**
- `CircuitBreaker` (mencionado em `analise-requisitos-agentes.md`) — abre após 5 falhas consecutivas, cooldown de 60s
- Retry com backoff nos agentes (`_execute_agent_with_retry`)

**O que falta:**
- "Explicação automática de logs via IA" — isso exigiria uma chamada extra à OpenAI para interpretar logs de erro, o que é uma funcionalidade nova não implementada
- Detecção de anomalias em tempo real e análise preditiva — fora do escopo atual, exigiria histórico de métricas e um modelo de série temporal

**Próximo passo sugerido:** este item é o mais distante da stack atual. Se quiser avançar, o menor incremento viável seria: ao um agente falhar 3x seguidas, gerar um resumo do erro via OpenAI (reaproveitando o cliente já configurado) e expor no dashboard. Isso precisa de confirmação explícita antes de implementar, pois é uma funcionalidade nova.

---

## 5. Low-Code para QA e SRE

**O que o prompt pede:** ferramentas visuais/no-code para QA, testes visuais e regressão automatizada, assistentes para SRE/DevOps.

**Avaliação:** este tópico se refere a ferramentas de mercado (ex: Testim, Mabl, Percy) que são produtos SaaS independentes, não bibliotecas a serem integradas ao código. Não há ação de código aplicável dentro do repositório atual.

**Próximo passo sugerido:** nenhum — este item é conceitual/educacional, não uma tarefa de implementação.

---

## 6. Low-Code com IA (AutoGPT e Flowise)

**O que o prompt pede:** automação de fluxos com triggers, agentes visuais com AutoGPT e Flowise, integração com APIs/webhooks.

**Avaliação:** AutoGPT e Flowise são plataformas externas de orquestração de agentes, distintas do LangGraph já usado no projeto. Adicionar qualquer uma delas significaria introduzir uma segunda camada de orquestração de agentes, o que:
- Não foi solicitado nos requisitos originais do projeto (`requisitos.md` pede especificamente LangGraph)
- Adicionaria uma dependência externa significativa (serviço separado, banco de dados próprio no caso do Flowise)

**Próximo passo sugerido:** **não recomendado** para este projeto — divergiria do requisito de usar LangGraph como framework de orquestração. Se o interesse é apenas educacional/exploratório, sugiro tratar como um projeto experimental separado, fora do `busca-email-AI`.

---

## Resumo de Prioridades

| # | Tópico | Viabilidade no projeto atual | Ação recomendada |
|---|--------|------------------------------|-------------------|
| 1 | Observabilidade e logs | ✅ Alta | Padronizar logs estruturados nos agentes |
| 2 | QA / testes de aceitação | ✅ Alta | Criar testes de aceitação por risco |
| 3 | Testes automatizados / E2E | 🟡 Média | Avaliar Playwright no frontend (requer confirmação) |
| 4 | Detecção de falhas com IA | 🟡 Média | Resumo de erro via OpenAI após falhas repetidas (requer confirmação) |
| 5 | Low-code QA/SRE | ⚪ Não aplicável | Nenhuma ação — ferramentas de mercado, fora do escopo |
| 6 | AutoGPT / Flowise | ❌ Não recomendado | Divergiria do requisito de usar LangGraph |

---

## Como proceder

Este roteiro é só o mapeamento. Para qualquer um dos itens marcados como "requer confirmação" ou para os itens 1 e 2 (viabilidade alta), preciso que você escolha qual implementar primeiro — nenhuma alteração de código será feita até você indicar qual item seguir.
