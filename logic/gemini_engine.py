"""
Módulo E: Motor de IA (Gemini)
==============================
Encargado de la comunicación con la API en la nube de Google Gemini para 
el análisis de bloqueos WAF y sugerencia de payloads.
"""

from __future__ import annotations

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import google.generativeai as genai
except ImportError:
    genai = None

# ── Configuración de Modelos ──────────────────────────────────────────────────
AVAILABLE_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro"
]
DEFAULT_MODEL = "gemini-2.5-flash"

# ── Prompt de sistema ─────────────────────────────────────────────────────────
_SYSTEM_PROMPT = (
    "Eres un experto en seguridad ofensiva y evasión de WAF (Web Application Firewall). "
    "Tu tarea es analizar la petición HTTP y la respuesta recibida, identificar por qué "
    "el WAF bloqueó la petición, y proporcionar EXACTAMENTE 3 técnicas de evasión "
    "concretas y accionables. "
    "Responde SIEMPRE en español. "
)

class GeminiEngineError(Exception):
    """Excepción base para errores del motor Gemini."""
    pass

class GeminiConfigError(GeminiEngineError):
    """Excepción lanzada cuando falta la API Key o la librería no está instalada."""
    pass

class GeminiConnectionError(GeminiEngineError):
    """Excepción para errores de conexión o de la API de Google."""
    pass

class GeminiResponseError(GeminiEngineError):
    """Excepción para respuestas inválidas de la API de Google."""
    pass

class GeminiEngine:
    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self.model = model
        self._api_key = os.environ.get("GEMINI_API_KEY", "")
        if self._api_key and genai:
            genai.configure(api_key=self._api_key)

    def is_available(self) -> bool:
        """Verifica si la API de Gemini está lista para usarse."""
        return bool(self._api_key and genai)

    def get_installed_models(self) -> list[str]:
        """
        Retorna la lista de modelos de Gemini soportados.
        """
        if not self.is_available():
            return []
        return AVAILABLE_MODELS

    def suggest_waf_bypass(
        self,
        request_text: str,
        response_text: str,
        model_override: str | None = None,
    ) -> str:
        """
        Envía la petición bloqueada a Gemini y retorna un JSON string 
        con técnicas de evasión WAF.
        """
        if not self.is_available():
            raise GeminiConfigError(
                "La API de Gemini no está configurada.\n"
                "Asegúrate de definir la variable de entorno GEMINI_API_KEY y de instalar 'google-generativeai'."
            )

        target_model_name = model_override if model_override else self.model
        prompt = self._build_prompt(request_text, response_text)

        try:
            # Inicializamos el modelo instanciándolo con el system_instruction
            model = genai.GenerativeModel(
                model_name=target_model_name,
                system_instruction=_SYSTEM_PROMPT
            )

            # Forzamos JSON schema estructurado
            response = model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                )
            )

            if not response.text:
                raise GeminiResponseError("Gemini devolvió una respuesta vacía.")

            return response.text

        except Exception as exc:
            # Capturamos excepciones genéricas de red o de API de google
            if isinstance(exc, GeminiEngineError):
                raise
            raise GeminiConnectionError(f"Error al conectar con Gemini API: {exc}") from exc

    def _build_prompt(self, request_text: str, response_text: str) -> str:
        _MAX_CHARS = 10_000 # Gemini soporta contextos muy grandes
        req_snippet  = request_text[:_MAX_CHARS]
        resp_snippet = response_text[:_MAX_CHARS]

        return (
            "Actúa como un experto en pentesting. Analiza este request HTTP bloqueado y sugiere 3 técnicas AVANZADAS de evasión de WAF.\n\n"
            f"--- REQUEST BLOQUEADO ---\n{req_snippet}\n\n"
            f"--- RESPONSE WAF ---\n{resp_snippet}\n\n"
            "REGLAS ESTRICTAS:\n"
            "1. NO repitas técnicas. Cada evasión debe ser única.\n"
            "2. Explora técnicas avanzadas como: Manipulación de Headers (ej. X-Forwarded-For, X-Real-IP), Encoding de URL (doble encoding, Unicode), Cambio de Verbos HTTP (Verb Tampering), y manipulación de parámetros.\n"
            "3. Tu respuesta DEBE SER ÚNICAMENTE un array JSON válido. NO añadas texto introductorio, ni saludos, ni explicaciones fuera del JSON.\n"
            "4. Usa EXACTAMENTE esta estructura JSON:\n"
            "[\n"
            '  {"tecnica": "Nombre de técnica 1", "payload": "SOLO LA LÍNEA A CAMBIAR", "explicacion": "Por qué funcionará"},\n'
            '  {"tecnica": "Nombre de técnica 2", "payload": "SOLO LA LÍNEA A CAMBIAR", "explicacion": "Por qué funcionará"},\n'
            '  {"tecnica": "Nombre de técnica 3", "payload": "SOLO LA LÍNEA A CAMBIAR", "explicacion": "Por qué funcionará"}\n'
            "]\n"
            "5. NUNCA devuelvas la petición completa en el payload. Devuelve ÚNICAMENTE el fragmento, cabecera o verbo que el usuario debe inyectar o modificar."
        )
