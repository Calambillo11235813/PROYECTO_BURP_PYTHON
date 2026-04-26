"""
logic/ai_engine.py
------------------
Motor de Inteligencia Artificial local para NetLens (Módulo E - CU-13).

Responsabilidades (y SOLO estas):
    - Comunicarse con el servidor Ollama local vía HTTP.
    - Construir prompts estructurados para análisis de seguridad.
    - Retornar respuestas de texto plano al módulo llamante.

Este módulo NO abre ventanas, NO gestiona hilos y NO conoce nada
de CustomTkinter. Es puramente lógica de negocio testeable.

Dependencias externas:
    - requests >= 2.31.0  (ya incluido en requirements.txt)
    - Ollama corriendo en http://localhost:11434

Autores: Diogo Nicolas Rodriguez Gomez, Javier Soliz Rueda
Materia: Ingeniería de Software 2
"""

from __future__ import annotations

import json

import requests

# ── Configuración del servidor Ollama ─────────────────────────────────────────
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_API_URL  = f"{OLLAMA_BASE_URL}/api/generate"
DEFAULT_MODEL   = "llama3"   # se puede sobreescribir al instanciar

# Tiempo máximo de espera para la respuesta del modelo (segundos).
# Los LLMs locales pueden tardar en generar; 300 s (5 minutos) es un valor holgado.
REQUEST_TIMEOUT = 300

# ── Prompt de sistema ─────────────────────────────────────────────────────────
_SYSTEM_PROMPT = (
    "Eres un experto en seguridad ofensiva y evasión de WAF (Web Application Firewall). "
    "Tu tarea es analizar la petición HTTP y la respuesta recibida, identificar por qué "
    "el WAF bloqueó la petición, y proporcionar EXACTAMENTE 3 técnicas de evasión "
    "concretas y accionables. "
    "Responde SIEMPRE en español. "
    "Devuelve ÚNICAMENTE un array JSON válido, sin texto antes ni después, y sin bloques de markdown. "
    'El formato exacto que debes usar es: [{"tecnica": "Nombre de la técnica", "payload": "El código HTTP a inyectar", "explicacion": "Por qué funciona"}]'
)


class AIEngineError(Exception):
    """Excepción base para errores del motor de IA."""


class OllamaConnectionError(AIEngineError):
    """Ollama no está disponible en la dirección configurada."""


class OllamaResponseError(AIEngineError):
    """Ollama respondió con un código de error (ej. 500 por falta de RAM)."""


class AIEngine:
    """
    Cliente del servidor Ollama para análisis de seguridad asistido por IA.

    Cada instancia puede apuntar a un modelo distinto. El estado de la
    instancia es mínimo (solo la URL y el modelo), por lo que es seguro
    reutilizar la misma instancia desde múltiples hilos siempre y cuando
    cada llamada a ``suggest_waf_bypass`` se realice desde un único hilo
    (lo que garantiza ``RepeaterTab`` con su hilo daemon dedicado).

    Args:
        model (str): Nombre del modelo Ollama a usar. Por defecto 'llama3'.
        base_url (str): URL base del servidor Ollama.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        base_url: str = OLLAMA_BASE_URL,
    ) -> None:
        self.model    = model
        self._base_url = base_url
        self._api_url = f"{base_url}/api/generate"
        self._tags_url = f"{base_url}/api/tags"

    # ── API pública ────────────────────────────────────────────────────────────

    def suggest_waf_bypass(
        self,
        request_text: str,
        response_text: str,
        model_override: str | None = None,
    ) -> str:
        """
        Solicita al modelo local 3 técnicas de evasión de WAF (CU-13).

        Construye un prompt que incluye la petición HTTP y la respuesta
        bloqueada, luego los envía al modelo Ollama configurado y retorna
        la respuesta como texto plano.

        Args:
            request_text  (str): Texto completo de la petición HTTP enviada.
            response_text (str): Texto completo de la respuesta recibida
                                 (normalmente un 403 Forbidden o similar).

        Returns:
            str: Texto con las 3 sugerencias de bypass generadas por la IA.

        Raises:
            OllamaConnectionError: Si Ollama no está corriendo o no es
                                   alcanzable en la URL configurada.
            OllamaResponseError:   Si Ollama responde con un status HTTP ≥ 400
                                   (ej. 500 por falta de memoria RAM).
        """
        prompt = self._build_prompt(request_text, response_text)
        target_model = model_override if model_override else self.model
        
        payload = {
            "model" : target_model,
            "prompt": prompt,
            "system": _SYSTEM_PROMPT,
            "stream": False,   # respuesta completa en un solo JSON
            "format": "json",  # Fuerza nativamente a Ollama a responder en formato JSON
        }

        try:
            response = requests.post(
                self._api_url,
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )
        except requests.exceptions.ConnectionError as exc:
            raise OllamaConnectionError(
                f"No se pudo conectar a Ollama en '{self._api_url}'.\n"
                f"Asegúrate de que Ollama está corriendo: ollama serve\n"
                f"Detalle técnico: {exc}"
            ) from exc
        except requests.exceptions.Timeout as exc:
            raise OllamaConnectionError(
                f"Ollama no respondió en {REQUEST_TIMEOUT} segundos.\n"
                f"El modelo puede estar cargando o la máquina no tiene "
                f"suficientes recursos. Intenta de nuevo."
            ) from exc

        # Errores HTTP del servidor Ollama (ej. 500 por OOM, 404 modelo no encontrado)
        if response.status_code >= 400:
            raise OllamaResponseError(
                f"Ollama respondió con HTTP {response.status_code}.\n"
                f"Posibles causas:\n"
                f"  • HTTP 500: La máquina no tiene suficiente RAM para cargar "
                f"'{target_model}'.\n"
                f"  • HTTP 404: El modelo '{target_model}' no está instalado. "
                f"Ejecuta: ollama pull {target_model}\n"
                f"Respuesta del servidor: {response.text[:300]}"
            )

        # Extraer el texto generado del JSON de respuesta
        return self._extract_response_text(response.text)

    def get_installed_models(self) -> list[str]:
        """
        Obtiene la lista de modelos instalados en el servidor Ollama local.

        Hace una petición GET a /api/tags y parsea el JSON resultante.

        Returns:
            list[str]: Lista con los nombres de los modelos disponibles.
                       Retorna una lista vacía si Ollama no está disponible.
        """
        try:
            response = requests.get(self._tags_url, timeout=3)
            if response.status_code != 200:
                return []
            
            data = response.json()
            models = data.get("models", [])
            return [model.get("name") for model in models if "name" in model]
        except (requests.exceptions.RequestException, ValueError):
            return []

    def is_available(self) -> bool:
        """
        Comprueba si el servidor Ollama está activo (HEAD a la raíz).

        Útil para validar la conexión antes de mostrar el botón de IA en la GUI.

        Returns:
            bool: True si Ollama responde, False en caso contrario.
        """
        try:
            r = requests.head(
                OLLAMA_BASE_URL,
                timeout=3,
            )
            return r.status_code < 500
        except requests.exceptions.RequestException:
            return False

    # ── Helpers privados ───────────────────────────────────────────────────────

    @staticmethod
    def _build_prompt(request_text: str, response_text: str) -> str:
        """
        Construye el prompt estructurado para la solicitud de bypass WAF.

        El prompt delimita claramente la petición y la respuesta usando
        bloques de código para que el modelo pueda identificarlas sin ambigüedad.

        Args:
            request_text  (str): Petición HTTP en texto plano.
            response_text (str): Respuesta HTTP en texto plano.

        Returns:
            str: Prompt completo listo para enviar al modelo.
        """
        # Truncar entradas muy largas para evitar que excedan el contexto del modelo.
        # La mayoría de modelos locales soportan ~4 096 tokens; 3 000 chars es seguro.
        _MAX_CHARS = 3_000
        req_snippet  = request_text[:_MAX_CHARS]
        resp_snippet = response_text[:_MAX_CHARS]

        return (
            "Actúa como un experto en pentesting. Analiza este request HTTP bloqueado y sugiere 3 técnicas de evasión de WAF.\n\n"
            f"--- REQUEST BLOQUEADO ---\n{req_snippet}\n\n"
            f"--- RESPONSE WAF ---\n{resp_snippet}\n\n"
            "REGLAS ESTRICTAS:\n"
            "1. NO repitas técnicas. Cada evasión debe ser única.\n"
            "2. Enfócate en: Manipulación de Headers, Encoding de URL, o cambio de Verbos HTTP.\n"
            "3. Tu respuesta DEBE SER ÚNICAMENTE un array JSON válido. NO añadas texto introductorio, ni saludos, ni explicaciones fuera del JSON.\n"
            "4. Usa EXACTAMENTE esta estructura JSON:\n"
            "[\n"
            '  {"tecnica": "Nombre de técnica 1", "payload": "El código HTTP exacto a inyectar", "explicacion": "Por qué funcionará"},\n'
            '  {"tecnica": "Nombre de técnica 2", "payload": "El código HTTP exacto a inyectar", "explicacion": "Por qué funcionará"},\n'
            '  {"tecnica": "Nombre de técnica 3", "payload": "El código HTTP exacto a inyectar", "explicacion": "Por qué funcionará"}\n'
            "]"
        )

    @staticmethod
    def _extract_response_text(raw_json: str) -> str:
        """
        Extrae el campo 'response' del JSON devuelto por Ollama.

        Si el JSON está malformado o el campo no existe, retorna el texto
        crudo como fallback para no perder información.

        Args:
            raw_json (str): Cuerpo de la respuesta HTTP de Ollama.

        Returns:
            str: Texto generado por el modelo.
        """
        try:
            data = json.loads(raw_json)
            return data.get("response", raw_json).strip()
        except json.JSONDecodeError:
            # Fallback: devolver el texto crudo si el JSON no es válido
            return raw_json.strip()
