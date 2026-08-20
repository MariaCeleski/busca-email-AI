# =============================================================================
# Guardrails de Conteúdo — validação de respostas geradas pela IA
#
# Objetivo: Verificar se a resposta gerada pelo agente contém termos
# inadequados, ofensivos ou dados sensíveis antes de apresentar ao usuário.
#
# Estratégia: Lista de termos proibidos (sem custo extra de API).
# Se detectar conteúdo problemático, sinaliza para revisão humana.
# =============================================================================
"""Guardrails de conteúdo — valida respostas da IA antes de exibir ao usuário."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List


@dataclass
class GuardrailResult:
    """Resultado da validação de guardrails."""
    is_safe: bool
    flagged_terms: List[str]
    category: str  # "safe", "offensive", "sensitive_data", "inappropriate"
    message: str


# Termos ofensivos ou inadequados (português + inglês)
OFFENSIVE_TERMS = [
    "idiota", "imbecil", "burro", "estúpido", "lixo", "merda",
    "porra", "caralho", "foda-se", "vai se foder", "filho da puta",
    "racist", "sexist", "hate", "kill", "die",
    "nigger", "faggot", "retard",
]

# Padrões de dados sensíveis que não devem aparecer em respostas
SENSITIVE_PATTERNS = [
    r'\b\d{3}\.\d{3}\.\d{3}-\d{2}\b',  # CPF
    r'\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b',  # CNPJ
    r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b',  # Cartão de crédito
    r'\bsenha\s*[:=]\s*\S+',  # Senha exposta
    r'\bpassword\s*[:=]\s*\S+',  # Password exposta
    r'\b[A-Za-z0-9]{20,}\b(?=.*key)',  # Possível API key
]

# Frases que indicam conteúdo inapropriado para resposta profissional
INAPPROPRIATE_PHRASES = [
    "não me importo",
    "problema seu",
    "dane-se",
    "isso não é minha responsabilidade",
    "you're wrong",
    "that's your problem",
]


def validate_response(text: str) -> GuardrailResult:
    """Valida uma resposta gerada pela IA contra as regras de guardrails.

    Args:
        text: Texto da resposta gerada pelo agente.

    Returns:
        GuardrailResult indicando se o conteúdo é seguro ou não.
    """
    if not text or not text.strip():
        return GuardrailResult(
            is_safe=True,
            flagged_terms=[],
            category="safe",
            message="Resposta vazia — segura.",
        )

    text_lower = text.lower()
    flagged = []

    # Verificar termos ofensivos
    for term in OFFENSIVE_TERMS:
        if term.lower() in text_lower:
            flagged.append(f"ofensivo: '{term}'")

    if flagged:
        return GuardrailResult(
            is_safe=False,
            flagged_terms=flagged,
            category="offensive",
            message=f"Resposta contém {len(flagged)} termo(s) ofensivo(s). Requer revisão.",
        )

    # Verificar dados sensíveis
    for pattern in SENSITIVE_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            flagged.append(f"dado sensível: '{match[:10]}...'")

    if flagged:
        return GuardrailResult(
            is_safe=False,
            flagged_terms=flagged,
            category="sensitive_data",
            message=f"Resposta pode conter {len(flagged)} dado(s) sensível(is). Requer revisão.",
        )

    # Verificar frases inapropriadas
    for phrase in INAPPROPRIATE_PHRASES:
        if phrase.lower() in text_lower:
            flagged.append(f"inapropriado: '{phrase}'")

    if flagged:
        return GuardrailResult(
            is_safe=False,
            flagged_terms=flagged,
            category="inappropriate",
            message=f"Resposta contém {len(flagged)} expressão(ões) inadequada(s) para tom profissional.",
        )

    return GuardrailResult(
        is_safe=True,
        flagged_terms=[],
        category="safe",
        message="Resposta aprovada pelos guardrails.",
    )
