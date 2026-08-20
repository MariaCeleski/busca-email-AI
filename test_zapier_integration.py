#!/usr/bin/env python3
"""
Script de teste para integração Zapier
Envia payloads de exemplo para testar a configuração
"""

import asyncio
import json
import sys
from datetime import datetime
from typing import Dict, Any

import httpx


class ZapierTester:
    """Classe para testar integração Zapier com diferentes cenários."""
    
    def __init__(self, zapier_webhook_url: str):
        self.webhook_url = zapier_webhook_url
        
    async def send_payload(self, payload: Dict[str, Any]) -> bool:
        """Envia payload para webhook Zapier."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    self.webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                
                print(f"✅ Payload enviado - Status: {response.status_code}")
                if response.status_code != 200:
                    print(f"❌ Response: {response.text}")
                    return False
                    
                return True
                
        except Exception as e:
            print(f"❌ Erro ao enviar payload: {e}")
            return False
    
    def create_email_processed_payload(self) -> Dict[str, Any]:
        """Cria payload para evento email_processed."""
        return {
            "event_type": "email_processed",
            "data": {
                "email_id": "test_email_zapier_001",
                "timestamp": datetime.utcnow().isoformat(),
                "email": {
                    "provider_message_id": "gmail_test_123",
                    "sender": "cliente.teste@exemplo.com",
                    "subject": "🧪 Teste Zapier - Problema Urgente",
                    "provider": "gmail"
                },
                "classification": {
                    "category": "Urgent",
                    "priority": "High",
                    "confidence": 0.95,
                    "requires_response": True,
                    "requires_summary": True
                },
                "summary": {
                    "summary": "Cliente relatou problema com sistema de pagamentos e precisa de resolução urgente.",
                    "key_points": ["Pagamento não processado", "Conta bloqueada", "Precisa resolver hoje"],
                    "confidence": 0.92
                },
                "draft_reply": {
                    "suggested_subject": "Re: 🧪 Teste Zapier - Problema Urgente",
                    "reply_body": "Prezado cliente, recebemos sua solicitação e nossa equipe já está analisando o problema...",
                    "status": "PENDING"
                },
                "stage": "completed"
            },
            "source": "orchestrator",
            "timestamp": datetime.utcnow().isoformat()
        }
    
    def create_agent_completed_payload(self) -> Dict[str, Any]:
        """Cria payload para evento agent_completed."""
        return {
            "event_type": "agent_completed",
            "data": {
                "email_id": "test_email_zapier_002",
                "agent_name": "classifier",
                "timestamp": datetime.utcnow().isoformat(),
                "classification": {
                    "category": "Support",
                    "priority": "Medium",
                    "confidence": 0.87,
                    "requires_response": True
                },
                "execution_time": 2.5
            },
            "source": "orchestrator",
            "timestamp": datetime.utcnow().isoformat()
        }
    
    def create_error_payload(self) -> Dict[str, Any]:
        """Cria payload para evento error_occurred."""
        return {
            "event_type": "error_occurred",
            "data": {
                "email_id": "test_email_zapier_003",
                "error_type": "Classification timeout - LLM not responding",
                "component": "orchestrator",
                "severity": "high",
                "timestamp": datetime.utcnow().isoformat(),
                "email": {
                    "sender": "problema@exemplo.com",
                    "subject": "Email que causou erro no sistema"
                }
            },
            "source": "orchestrator",
            "timestamp": datetime.utcnow().isoformat()
        }
    
    async def run_all_tests(self) -> bool:
        """Executa todos os testes de payload."""
        print("🧪 Iniciando testes de integração Zapier...\n")
        
        tests = [
            ("📧 Email Processado Completo", self.create_email_processed_payload()),
            ("🤖 Agente Completado", self.create_agent_completed_payload()),
            ("🚨 Erro no Sistema", self.create_error_payload())
        ]
        
        results = []
        for test_name, payload in tests:
            print(f"Testando: {test_name}")
            print(f"Payload: {json.dumps(payload, indent=2)[:200]}...")
            
            result = await self.send_payload(payload)
            results.append(result)
            
            print("-" * 50)
            await asyncio.sleep(2)  # Delay entre testes
        
        success_count = sum(results)
        print(f"\n🎯 Resultado: {success_count}/{len(tests)} testes bem-sucedidos")
        
        if success_count == len(tests):
            print("✅ Todos os testes passaram! Integração Zapier funcionando.")
            return True
        else:
            print("❌ Alguns testes falharam. Verifique a configuração do Zapier.")
            return False


async def main():
    """Função principal do script."""
    print("🔗 Testador de Integração Zapier - AI Email Agent System")
    print("=" * 60)
    
    # Solicitar URL do webhook
    webhook_url = input("Digite a URL do webhook Zapier: ").strip()
    
    if not webhook_url:
        print("❌ URL do webhook é obrigatória!")
        sys.exit(1)
    
    if not webhook_url.startswith("https://hooks.zapier.com/"):
        print("⚠️  Aviso: URL não parece ser um webhook Zapier válido")
        confirm = input("Continuar mesmo assim? (y/N): ").strip().lower()
        if confirm not in ['y', 'yes']:
            sys.exit(1)
    
    # Executar testes
    tester = ZapierTester(webhook_url)
    
    try:
        success = await tester.run_all_tests()
        
        if success:
            print("\n🎉 Integração Zapier configurada com sucesso!")
            print("Verifique seu Slack/Discord para as notificações de teste.")
        else:
            print("\n💡 Próximos passos:")
            print("1. Verifique se a URL do webhook está correta")
            print("2. Confirme que o Zap está ativo no Zapier")
            print("3. Teste manualmente com curl se necessário")
            
    except KeyboardInterrupt:
        print("\n\n⏹️  Teste cancelado pelo usuário")
    except Exception as e:
        print(f"\n❌ Erro inesperado: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # Verificar dependências
    try:
        import httpx
    except ImportError:
        print("❌ Dependência httpx não encontrada!")
        print("Instale com: pip install httpx")
        sys.exit(1)
    
    # Executar
    asyncio.run(main())