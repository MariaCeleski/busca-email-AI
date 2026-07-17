# Regras de Desenvolvimento — AI Email Agent

Documento de referência com as diretrizes para manutenção e evolução do projeto.
Deve ser consultado antes de qualquer alteração no código.

---

## Regra 1: Não Quebrar a Aplicação

Toda alteração deve ser testada antes de ser considerada concluída.
- Verificar compilação TypeScript (`npx tsc --noEmit`)
- Verificar imports Python (`python -c "from src.api.app import create_app"`)
- Confirmar que o backend inicia sem erros
- Confirmar que o frontend renderiza no browser

---

## Regra 2: Não Alterar o que Funciona

Antes de editar qualquer arquivo, identificar o que já está funcionando.
- Não modificar fluxos que o usuário confirmou como corretos
- Alterações devem ser cirúrgicas e isoladas ao problema reportado
- Se um fluxo funciona (ex: aprovação simples), não tocar nele

---

## Regra 3: Revisar Somente o Pedido

Focar exclusivamente no que foi solicitado pelo usuário.
- Não refatorar código adjacente
- Não adicionar features não solicitadas
- Não renomear variáveis ou reorganizar imports sem necessidade

---

## Regra 4: Testar Sempre

Após cada alteração:
- Compilar frontend e backend
- Reiniciar o backend (lru_cache exige restart completo)
- Testar no browser o fluxo afetado
- Verificar que fluxos existentes continuam funcionando

---

## Regra 5: Aceitar Sugestões

Quando houver mais de uma forma de resolver, apresentar opções ao usuário.
- Explicar prós e contras de cada abordagem
- Aguardar confirmação antes de implementar
- Documentar a decisão tomada

---

## Regra 6: Feedback Separado da Revisão

- O botão "✕ Dispensar" na revisão NÃO registra feedback
- Feedback só é registrado em ações explícitas: Aprovar ou Rejeitar
- Dados de feedback ficam na tabela `classification_feedback`
- O agente consulta feedback via few-shot prompting dinâmico

---

## Regra 7: Dados de Demonstração

- O endpoint `/api/v1/emails/demo` executa o pipeline completo
- Pipeline: Classificar → Resumir → Gerar Resposta (draft_reply)
- Emails demo devem cobrir todas as categorias e prioridades
- Spam deve ter confiança baixa (35-65%) para testar revisão manual

---

## Regra 8: Confiança e Revisão Manual

- Threshold de revisão: `flagged_for_review = True` (setado pelo classificador)
- Classificador marca `flagged_for_review` quando confiança < 0.6
- Spam: confiança instruída entre 0.35 e 0.65
- Promocional desconhecido: confiança entre 0.50 e 0.70
- Emails claros (urgente, transacional): confiança 0.85-0.95

---

## Regra 9: Exclusão de Emails

- Emails já revisados (approved/rejected/sent) mostram botão "Excluir da lista"
- Excluir remove permanentemente do banco (processed_emails + draft_replies)
- A exclusão é irreversível — pedir confirmação antes

---

## Regra 10: Configuração Técnica

- Modelo IA: `gpt-4o-mini` (OpenAI)
- PostgreSQL usa `TIMESTAMP WITHOUT TIME ZONE` → usar `datetime.utcnow()`
- `@lru_cache` em `get_settings()` → restart completo ao mudar `.env`
- GmailClient aceita apenas `access_token` e `refresh_token`
- Tokens em `connected_accounts` são encriptados → decriptar antes de usar
- API Key para login no dashboard: `dev-api-key-2024`

---

## Regra 11: Comandos de Execução

```bash
# Backend
cd backend && .venv/bin/python -m uvicorn src.api.app:create_app --factory --host 0.0.0.0 --port 8000

# Frontend
cd frontend && npm run dev

# Docker (PostgreSQL, Redis, ChromaDB)
docker compose up -d

# Celery Worker
cd backend && .venv/bin/celery -A src.tasks.celery_app:celery_app worker --loglevel=info

# Acessar banco de dados
docker exec -it email-agent-postgres psql -U postgres -d email_agent
```

---

## Regra 12: Estrutura de Arquivos Chave

| Arquivo | Responsabilidade |
|---------|-----------------|
| `backend/src/agents/classifier.py` | Classificação + confiança + prioridade |
| `backend/src/agents/summarizer.py` | Resumo + itens de ação |
| `backend/src/agents/response.py` | Geração de resposta (draft_reply) |
| `backend/src/api/routers/emails.py` | Endpoints de email (CRUD, approve, reject, dismiss, delete) |
| `backend/src/api/routers/feedback.py` | Endpoints de feedback (history, delete) |
| `backend/src/api/routers/fetch.py` | Buscar emails reais + endpoint demo |
| `backend/src/services/feedback_learner.py` | Few-shot prompting dinâmico |
| `frontend/src/pages/EmailDetail.tsx` | Detalhe do email + approve/reject/edit |
| `frontend/src/pages/ManualReview.tsx` | Lista de emails para revisão |
| `frontend/src/pages/Feedback.tsx` | Histórico de feedback |
| `frontend/src/services/api.ts` | Client HTTP para o backend |

---

## Regra 13: Versionamento Git e Organização de Branches

O versionamento deve evidenciar desenvolvimento por etapas, com branches temáticas e commits semânticos.

### Estratégia de Branches

| Branch | Propósito |
|--------|-----------|
| `main` | Código estável e funcional (produção) |
| `develop` | Integração de features antes de ir para main |
| `feature/*` | Cada funcionalidade nova em branch separada |
| `bugfix/*` | Correções de bugs em branches isoladas |
| `docs/*` | Alterações apenas em documentação |

### Convenção de Commits (Semantic Commits)

```
tipo(escopo): descrição curta

Exemplos:
feat(frontend): adicionar página de feedback com histórico
feat(backend): criar endpoint DELETE para emails processados
fix(classifier): ajustar confiança para spam (35-65%)
fix(frontend): corrigir edição de resposta não salvando
docs: adicionar regras de desenvolvimento
refactor(api): separar endpoint dismiss do feedback
style(css): melhorar responsividade do dashboard
```

### Tipos válidos

| Tipo | Uso |
|------|-----|
| `feat` | Nova funcionalidade |
| `fix` | Correção de bug |
| `docs` | Documentação |
| `refactor` | Refatoração sem mudar comportamento |
| `style` | CSS, formatação, sem lógica |
| `test` | Testes |
| `chore` | Configuração, dependências |

### Fluxo de Push

1. Criar branch a partir de `develop`: `git checkout -b feature/nome-da-feature develop`
2. Fazer commits pequenos e frequentes (1 commit por alteração lógica)
3. Cada branch deve ter múltiplos commits — reforça evidência de desenvolvimento por etapas
4. Merge na `develop` via Pull Request
5. Merge `develop` → `main` quando estável

### Regras de Push

- Nunca fazer push direto na `main`
- Sempre usar `-u` na primeira push de branch nova
- Commits devem ser atômicos (1 mudança = 1 commit)
- Não commitar `.env` (está no `.gitignore`)
- Mensagens em português ou inglês, mas consistentes dentro da branch
