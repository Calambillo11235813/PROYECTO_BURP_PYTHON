"""
tests/test_gemini_engine.py
---------------------------
Pruebas unitarias para el motor de Inteligencia Artificial en la nube (GeminiEngine).
"""

import unittest
from unittest.mock import patch, MagicMock
import json
import os

# Simulamos que la librería está importada correctamente
import logic.gemini_engine
from logic.gemini_engine import GeminiEngine, GeminiConfigError

class TestGeminiEngine(unittest.TestCase):

    def setUp(self):
        # Configuramos entorno
        os.environ["GEMINI_API_KEY"] = "fake-test-key"
        self.engine = GeminiEngine(model="test_gemini_model")
        self.dummy_req = "GET / HTTP/1.1\r\nHost: test.com\r\n\r\n"
        self.dummy_resp = "HTTP/1.1 403 Forbidden\r\n\r\nBlock!"

    def test_is_available(self):
        """Verifica que is_available devuelve True si hay API key y librería."""
        self.assertTrue(self.engine.is_available())

    @patch("logic.gemini_engine.genai.GenerativeModel")
    def test_suggest_waf_bypass(self, mock_gen_model_class):
        """Verifica que el payload de Gemini utilice el schema JSON estructurado."""
        
        # 1. Configurar mocks
        mock_model_instance = MagicMock()
        mock_gen_model_class.return_value = mock_model_instance
        
        mock_response = MagicMock()
        fake_llm_output = '[{"tecnica": "Gemini Bypass", "payload": "X", "explicacion": "Y"}]'
        mock_response.text = fake_llm_output
        mock_model_instance.generate_content.return_value = mock_response

        # 2. Ejecutar
        result = self.engine.suggest_waf_bypass(self.dummy_req, self.dummy_resp)

        # 3. Aserciones
        self.assertTrue(mock_gen_model_class.called)
        
        # Verificar inicialización de modelo con system prompt
        call_kwargs = mock_gen_model_class.call_args.kwargs
        self.assertEqual(call_kwargs["model_name"], "test_gemini_model")
        self.assertIn("system_instruction", call_kwargs)
        
        # Verificar generación de contenido
        self.assertTrue(mock_model_instance.generate_content.called)
        generate_kwargs = mock_model_instance.generate_content.call_args.kwargs
        
        # Verificar que se usó generation_config con application/json
        config = generate_kwargs.get("generation_config")
        self.assertIsNotNone(config)
        self.assertEqual(config.response_mime_type, "application/json")
        
        # Verificar resultado procesado
        self.assertEqual(result, fake_llm_output)

    def test_no_api_key_raises_error(self):
        """Verifica que lanza GeminiConfigError si no hay API key."""
        os.environ.pop("GEMINI_API_KEY", None)
        engine_no_key = GeminiEngine()
        
        with self.assertRaises(GeminiConfigError):
            engine_no_key.suggest_waf_bypass("req", "resp")

if __name__ == '__main__':
    unittest.main()
