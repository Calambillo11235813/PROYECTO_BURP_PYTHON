"""
logic package
-------------
Capa de procesamiento y manipulación de datos del proyecto Mini-Burp Suite.

Módulos:
    parser     → Extrae campos de peticiones HTTP crudas (bytes → ParsedRequest)
    ai_engine  → Motor de IA local vía Ollama (bypass WAF - CU-13)
"""
from .parser    import ParsedRequest, parse_request
from .ai_engine import AIEngine, AIEngineError, OllamaConnectionError, OllamaResponseError

__all__ = [
    "ParsedRequest",
    "parse_request",
    "AIEngine",
    "AIEngineError",
    "OllamaConnectionError",
    "OllamaResponseError",
]
