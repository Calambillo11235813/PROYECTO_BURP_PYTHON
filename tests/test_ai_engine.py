"""
tests/test_ai_engine.py
-----------------------
Pruebas unitarias para el motor de Inteligencia Artificial (AIEngine).
Verifica que los requests HTTP a Ollama incluyan los flags adecuados, como
el formato estricto JSON introducido para solucionar problemas de parsing y timeouts.
"""

import unittest
from unittest.mock import patch, MagicMock
import json

from logic.ai_engine import AIEngine

class TestAIEngine(unittest.TestCase):

    def setUp(self):
        self.engine = AIEngine(model="test_model")
        self.dummy_req = "GET / HTTP/1.1\r\nHost: test.com\r\n\r\n"
        self.dummy_resp = "HTTP/1.1 403 Forbidden\r\n\r\nBlock!"

    @patch("logic.ai_engine.requests.post")
    def test_suggest_waf_bypass_uses_json_format(self, mock_post):
        """Verifica que el payload enviado a Ollama incluya 'format': 'json'"""
        
        # 1. Configurar mock de respuesta (Ollama exitoso)
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        # Simular respuesta JSON del endpoint /api/generate de Ollama
        fake_llm_output = '[{"tecnica": "A", "payload": "B", "explicacion": "C"}]'
        mock_response.text = json.dumps({"response": fake_llm_output})
        
        mock_post.return_value = mock_response

        # 2. Ejecutar
        result = self.engine.suggest_waf_bypass(self.dummy_req, self.dummy_resp)

        # 3. Aserciones
        self.assertTrue(mock_post.called)
        
        # Extraer los argumentos pasados a requests.post
        call_kwargs = mock_post.call_args.kwargs
        self.assertIn("json", call_kwargs)
        
        payload = call_kwargs["json"]
        
        # Verificar que el payload contiene el flag requerido de JSON
        self.assertEqual(payload["model"], "test_model")
        self.assertIn("format", payload)
        self.assertEqual(payload["format"], "json")
        self.assertFalse(payload["stream"])
        
        # Verificar que el resultado extraído por el método es correcto
        self.assertEqual(result, fake_llm_output)

if __name__ == '__main__':
    unittest.main()
