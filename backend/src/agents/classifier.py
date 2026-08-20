# =============================================================================
# Agente Classificador — classifica e-mails usando o LLM OpenAI (GPT).
#
# Objetivo: Receber um e-mail bruto e produzir uma classificação estruturada
# contendo categoria (Urgente, Informativo, Promocional, Spam, Transacional, Pessoal),
# prioridade (Alta, Média, Baixa) e nível de confiança (0.0 a 1.0).
#
# Entrada: RawEmail (remetente, assunto, corpo, timestamp)
# Saída: ClassificationResult (category, priority, confidence, requires_response,
#         requires_summary, flagged_for_review)
#
# Timeout: 10 segundos. Se exceder, lança ClassificationError.
# E-mail vazio: Se assunto e corpo estiverem vazios, retorna Informativo/Baixa/0.0
#               sem chamar o LLM.
# =============================================================================
"""Agente Classificador — classifica e-mails usando OpenAI GPT."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from openai import AsyncOpenAI

from src.config import get_settings
from src.models.classification import ClassificationResult
from src.models.email import RawEmail
from src.models.enums import EmailCategory, PriorityLevel

logger = logging.getLogger(__name__)


# Erro lançado quando a classificação falha (timeout, resposta inválida, etc.)
class ClassificationError(Exception):
    """Raised when email classification fails (timeout, invalid response, etc.)."""


class ClassifierAgent:
    """Classifica e-mails em categorias e prioridades usando OpenAI GPT."""

    # Categorias que requerem geração de rascunho de resposta
    _RESPONSE_CATEGORIES = {EmailCategory.URGENT, EmailCategory.PERSONAL}
    # Prioridades que qualificam para geração de resposta
    _RESPONSE_PRIORITIES = {PriorityLevel.HIGH, PriorityLevel.MEDIUM}
    # Categorias que qualificam para sumarização
    _SUMMARY_CATEGORIES = {EmailCategory.URGENT, EmailCategory.INFORMATIVE}
    # Limiar de contagem de palavras para sumarização
    _SUMMARY_WORD_THRESHOLD = 200

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 10,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key or settings.openai_api_key
        self._model_name = model or settings.openai_model
        self._timeout = timeout

        # Configura o cliente OpenAI
        self._client = AsyncOpenAI(api_key=self._api_key)

        # Seção de few-shot com feedback do usuário (preenchido externamente)
        self._feedback_section: str = ""

    def set_feedback_examples(self, section: str) -> None:
        """Injeta a seção de exemplos de feedback no prompt de classificação."""
        self._feedback_section = section

    # Método principal: analisa o e-mail e retorna a classificação dentro do timeout de 10s.
    # Lança ClassificationError em caso de timeout ou resposta inválida.
    async def classify(self, email: RawEmail) -> ClassificationResult:
        """Analyze email and return classification within 10s timeout.

        Raises ClassificationError on timeout or invalid response.
        """
        # Trata e-mail vazio (assunto + corpo vazios)
        if not email.subject.strip() and not email.body.strip():
            return ClassificationResult(
                category=EmailCategory.INFORMATIVE,
                priority=PriorityLevel.LOW,
                confidence=0.0,
                requires_response=False,
                requires_summary=False,
                flagged_for_review=True,
            )

        prompt = self.build_classification_prompt(email, feedback_section=self._feedback_section)

        try:
            raw_output = await asyncio.wait_for(
                self._call_gemini(prompt),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            raise ClassificationError(
                f"Classification timed out after {self._timeout}s"
            )
        except ClassificationError:
            raise
        except Exception as exc:
            raise ClassificationError(f"Gemini API call failed: {exc}") from exc

        return self.validate_result(raw_output, email)

    # Constrói o prompt estruturado de classificação para o LLM (em português).
    def build_classification_prompt(self, email: RawEmail, feedback_section: str = "") -> str:
        """Construct the structured classification prompt."""
        return f"""Você é um assistente de classificação de e-mails. Analise o e-mail a seguir e classifique-o.

Retorne APENAS um objeto JSON válido com exatamente estes campos:
- "category": exatamente um entre "Urgent", "Informative", "Promotional", "Spam", "Transactional", "Personal"
- "priority": exatamente um entre "High", "Medium", "Low"
- "confidence": um número decimal entre 0.0 e 1.0 indicando o nível de confiança na classificação

Diretrizes de classificação:
- "Urgent": E-mails urgentes que exigem atenção imediata (prazos, emergências, solicitações críticas)
- "Informative": Notícias, atualizações, relatórios ou mensagens informativas que não precisam de resposta
- "Promotional": E-mails de marketing, ofertas, newsletters de empresas
- "Spam": E-mails indesejados, não solicitados ou suspeitos
- "Transactional": Confirmações de pedidos, recibos, notificações de envio, alertas de conta
- "Personal": Mensagens pessoais de indivíduos que requerem uma resposta pessoal

Diretrizes de prioridade:
- "High": Requer atenção ou ação imediata
- "Medium": Importante, mas não urgente
- "Low": Pode ser tratado depois ou é puramente informativo
Diretrizes de confiança:
- Atribua confiança ALTA (0.85-0.95) para e-mails claros e inequívocos (ex: reunião urgente do chefe, recibo de compra)
- Atribua confiança MÉDIA (0.60-0.80) para e-mails que podem pertencer a mais de uma categoria (ex: newsletter que pode ser informativa ou promocional)
- Atribua confiança BAIXA (0.30-0.55) para e-mails ambíguos, suspeitos ou que exigem julgamento humano (ex: spam disfarçado, promoção que parece golpe, mensagem pessoal vinda de remetente desconhecido)
- E-mails de Spam devem SEMPRE ter confiança entre 0.35 e 0.65, pois a distinção entre spam e promoção legítima é subjetiva
- E-mails Promocionais de remetentes desconhecidos devem ter confiança entre 0.50 e 0.70
{feedback_section}
Detalhes do e-mail:
- De: {email.sender}
- Assunto: {email.subject}
- Corpo: {email.body[:2000]}

Responda APENAS com o objeto JSON, sem texto ou formatação adicional."""

    # Valida e parseia a saída do LLM contra o schema ClassificationResult.
    # Calcula requires_response, requires_summary e flagged_for_review
    # com base nos resultados da classificação e conteúdo do e-mail.
    # Lança ClassificationError se o parsing ou validação falhar.
    def validate_result(self, raw_output: str, email: Optional[RawEmail] = None) -> ClassificationResult:
        """Parse and validate LLM output against ClassificationResult schema.

        Computes requires_response, requires_summary, and flagged_for_review
        based on the classification results and email content.

        Raises ClassificationError if parsing or validation fails.
        """
        try:
            # Remove blocos de código markdown se presentes
            cleaned = raw_output.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                cleaned = "\n".join(lines)

            data = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ClassificationError(
                f"Invalid JSON in LLM response: {exc}"
            ) from exc

        try:
            category = EmailCategory(data["category"])
            priority = PriorityLevel(data["priority"])
            confidence = float(data["confidence"])
        except (KeyError, ValueError) as exc:
            raise ClassificationError(
                f"Missing or invalid field in LLM response: {exc}"
            ) from exc

        # Limita a confiança ao intervalo válido [0.0, 1.0]
        confidence = max(0.0, min(1.0, confidence))

        # Calcula campos derivados baseados na lógica de classificação
        requires_response = (
            category in self._RESPONSE_CATEGORIES
            and priority in self._RESPONSE_PRIORITIES
        )

        # Calcula requires_summary baseado na categoria e contagem de palavras
        word_count = 0
        if email is not None:
            word_count = len(email.body.split())
        requires_summary = (
            category in self._SUMMARY_CATEGORIES
            and word_count > self._SUMMARY_WORD_THRESHOLD
        )

        # Sinaliza para revisão manual se a confiança for menor que 0.6
        flagged_for_review = confidence < 0.6

        return ClassificationResult(
            category=category,
            priority=priority,
            confidence=confidence,
            requires_response=requires_response,
            requires_summary=requires_summary,
            flagged_for_review=flagged_for_review,
        )

    # Chama a API da OpenAI e retorna a resposta em texto bruto.
    async def _call_gemini(self, prompt: str) -> str:
        """Call OpenAI API and return raw text response."""
        response = await self._client.chat.completions.create(
            model=self._model_name,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.choices[0].message.content
        if not text:
            raise ClassificationError("OpenAI returned empty response")
        return text
