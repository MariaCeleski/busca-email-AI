#!/usr/bin/env python3
"""
Script de teste para demonstração Zapier + Slack no vídeo
Executa diferentes cenários de webhook para validar integração
"""

import requests
import time
import json
from datetime import datetime

# Configuração
ZAPIER_WEBHOOK_URL = "https://hooks.zapier.com/hooks/catch/28584917/4t5ocoi/"
DELAY_BETWEEN_TESTS = 3  # segundos

def send_webhook(payload, description):
    """Envia payload para webhook e retorna resultado"""
    print(f"\n🚀 {description}")
    print(f"📤 Payload: {json.dumps(payload, indent=2)}")
    
    try:
        response = requests.post(
            ZAPIER_WEBHOOK_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        if response.status_code == 200:
            print(f"✅ SUCCESS - Status: {response.status_code}")
            print(f"📨 Response: {response.text}")
        else:
            print(f"❌ ERROR - Status: {response.status_code}")
            print(f"📨 Response: {response.text}")
            
        return response.status_code == 200
        
    except Exception as e:
        print(f"❌ EXCEPTION: {str(e)}")
        return False

def test_demo_scenarios():
    """Executa cenários de teste para o vídeo"""
    
    print("🎬 TESTE ZAPIER + SLACK - DEMO VÍDEO")
    print("=" * 50)
    
    # Teste 1: Ping simples
    payload_ping = {
        "event_type": "demo_ping",
        "timestamp": datetime.utcnow().isoformat(),
        "message": "🎬 Teste de conectividade para vídeo demo",
        "system": {
            "model_used": "gpt-4o-mini",
            "environment": "production"
        }
    }
    
    success1 = send_webhook(payload_ping, "Teste 1: Ping de Conectividade")
    time.sleep(DELAY_BETWEEN_TESTS)
    
    # Teste 2: Email processado completo
    payload_email = {
        "event_type": "email_processed",
        "timestamp": datetime.utcnow().isoformat(),
        "email": {
            "provider_message_id": "demo_msg_001",
            "sender": "professor@faculdade.edu.br",
            "subject": "🎓 Avaliação do Projeto - AI Email Agent",
            "provider": "gmail",
            "body_preview": "Gostaria de avaliar o projeto desenvolvido com IA..."
        },
        "classification": {
            "category": "Academic",
            "priority": "High",
            "confidence": 0.96,
            "requires_response": True
        },
        "summary": {
            "summary": "Professor solicita avaliação de projeto acadêmico com sistema de IA para processamento de emails",
            "key_points": [
                "Avaliação de projeto acadêmico",
                "Sistema IA funcional", 
                "Demonstração necessária"
            ]
        },
        "draft_reply": {
            "suggested_subject": "Re: Avaliação do Projeto - AI Email Agent",
            "reply_body": "Prezado Professor, ficamos honrados em apresentar nosso projeto..."
        },
        "stage": "completed",
        "processing_time": 2.3,
        "system": {
            "model_used": "gpt-4o-mini",
            "environment": "production"
        }
    }
    
    success2 = send_webhook(payload_email, "Teste 2: Email Processado Completo")
    time.sleep(DELAY_BETWEEN_TESTS)
    
    # Teste 3: Agente completado
    payload_agent = {
        "event_type": "agent_completed",
        "timestamp": datetime.utcnow().isoformat(),
        "email_id": "demo_msg_002",
        "agent_name": "classifier",
        "classification": {
            "category": "Urgent",
            "priority": "Critical", 
            "confidence": 0.98,
            "reasoning": "Email contém palavras-chave de urgência e prazo crítico"
        },
        "processing_time": 1.1,
        "system": {
            "model_used": "gpt-4o-mini",
            "retry_count": 0
        }
    }
    
    success3 = send_webhook(payload_agent, "Teste 3: Agente Classifier Completado")
    time.sleep(DELAY_BETWEEN_TESTS)
    
    # Teste 4: Erro simulado
    payload_error = {
        "event_type": "error_occurred",
        "timestamp": datetime.utcnow().isoformat(),
        "email_id": "demo_msg_003",
        "error": {
            "component": "summarizer",
            "error_type": "Timeout after 3 retries",
            "severity": "medium",
            "retry_count": 3,
            "last_attempt": datetime.utcnow().isoformat()
        },
        "email": {
            "sender": "test@exemplo.com",
            "subject": "Email com Problema de Processamento"
        },
        "system": {
            "model_used": "gpt-4o-mini",
            "environment": "production"
        }
    }
    
    success4 = send_webhook(payload_error, "Teste 4: Erro de Processamento")
    time.sleep(DELAY_BETWEEN_TESTS)
    
    # Teste 5: Email urgente empresarial
    payload_business = {
        "event_type": "email_processed", 
        "timestamp": datetime.utcnow().isoformat(),
        "email": {
            "sender": "cliente.vip@empresa.com.br",
            "subject": "🚨 URGENTE: Sistema de Faturamento Fora do Ar",
            "provider": "outlook"
        },
        "classification": {
            "category": "Urgent",
            "priority": "Critical",
            "confidence": 0.99,
            "requires_immediate_action": True
        },
        "summary": {
            "summary": "Cliente VIP reporta que sistema de faturamento está indisponível, impactando operações críticas",
            "impact_level": "High",
            "estimated_users_affected": 500
        },
        "draft_reply": {
            "suggested_subject": "Re: URGENTE - Equipe técnica mobilizada",
            "reply_body": "Prezado cliente, nossa equipe técnica foi imediatamente acionada...",
            "priority_flag": True
        },
        "system": {
            "model_used": "gpt-4o-mini",
            "processing_time": 1.8,
            "escalation_triggered": True
        }
    }
    
    success5 = send_webhook(payload_business, "Teste 5: Email Empresarial Crítico")
    
    # Resumo dos testes
    print("\n" + "=" * 50)
    print("📊 RESUMO DOS TESTES")
    print("=" * 50)
    
    results = [success1, success2, success3, success4, success5]
    descriptions = [
        "Teste 1: Ping Conectividade", 
        "Teste 2: Email Processado",
        "Teste 3: Agente Completado", 
        "Teste 4: Erro Simulado",
        "Teste 5: Email Crítico"
    ]
    
    for i, (result, desc) in enumerate(zip(results, descriptions)):
        status = "✅ PASSOU" if result else "❌ FALHOU"
        print(f"{desc}: {status}")
    
    success_rate = sum(results) / len(results) * 100
    print(f"\n🎯 Taxa de Sucesso: {success_rate:.1f}% ({sum(results)}/{len(results)})")
    
    if success_rate >= 80:
        print("🎉 SISTEMA PRONTO PARA DEMONSTRAÇÃO NO VÍDEO!")
    else:
        print("⚠️  VERIFICAR CONFIGURAÇÃO ANTES DA GRAVAÇÃO")
    
    return success_rate >= 80

if __name__ == "__main__":
    test_demo_scenarios()