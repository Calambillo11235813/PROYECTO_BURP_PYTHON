"""
logic/ai_copilot.py
--------------------
CU-14: Generacion dinamica de payloads para el Intruder mediante IA (Gemini).

Responsabilidades:
    - Analizar la plantilla HTTP del Intruder para identificar el contexto
      del marcador de inyeccion (parametro URL, campo JSON, cabecera, etc.).
    - Generar exactamente 15 payloads optimizados para ese contexto usando
      la API de Google Gemini.
    - Devolver la lista limpia de strings, lista para aniadirse a self._payloads.

Separacion de responsabilidades:
    Este modulo NO conoce la GUI. Recibe y devuelve datos primitivos (str / list).

Autores: Diogo Nicolas Rodriguez Gomez, Javier Soliz Rueda
Materia: Ingenieria de Software 2
"""

from __future__ import annotations

try:
    import google.generativeai as genai
    _GENAI_AVAILABLE = True
except ImportError:
    genai = None  # type: ignore[assignment]
    _GENAI_AVAILABLE = False

from logic.config_manager import ConfigManager


# ── Constantes ─────────────────────────────────────────────────────────────────

_MODEL_NAME    = "gemini-2.5-flash"
_PAYLOAD_COUNT = 15
_MAX_TEMPLATE  = 4_000  # caracteres del template enviados al prompt


# ── Excepciones propias ────────────────────────────────────────────────────────

class AICopilotError(Exception):
    """Base para errores del copiloto de IA."""


class AICopilotConfigError(AICopilotError):
    """Falta la API key o la libreria google-generativeai no esta instalada."""


class AICopilotNetworkError(AICopilotError):
    """Error de conexion con la API de Gemini."""


# ── Clase principal ────────────────────────────────────────────────────────────

class GeminiCopilot:
    """
    Copiloto de IA para el Intruder.

    Genera payloads de fuzzing contextualizados analizando la plantilla
    HTTP que el usuario ha configurado en la pestana 'Posiciones'.

    Usage::

        copilot = GeminiCopilot()
        payloads = copilot.generate_intruder_payloads(template)
        # payloads -> ["admin' --", "1 OR 1=1", ...]
    """

    def __init__(self) -> None:
        if not _GENAI_AVAILABLE:
            raise AICopilotConfigError(
                "La libreria 'google-generativeai' no esta instalada.\n"
                "Ejecuta: pip install google-generativeai"
            )

        self._api_key: str = ConfigManager.instance().get_api_key()

        if not self._api_key:
            raise AICopilotConfigError(
                "API Key no configurada.\n"
                "Ve a Ajustes (icono en la barra superior) e introduce "
                "tu clave de Google Gemini para usar el Copiloto de IA."
            )

        genai.configure(api_key=self._api_key)

    # ── API publica ────────────────────────────────────────────────────────────

    def generate_intruder_payloads(self, template: str) -> list[str]:
        """
        Analiza el template HTTP con marcadores § y genera payloads de ataque.

        Args:
            template:
                Peticion HTTP base con marcadores §...§ que indican los puntos
                de inyeccion (ej. "GET /search?q=§FUZZ§ HTTP/1.1\\nHost: x.com").

        Returns:
            Lista de exactamente hasta ``_PAYLOAD_COUNT`` strings con los payloads
            generados por Gemini, listos para anadir a ``self._payloads``.

        Raises:
            AICopilotConfigError: Si falta la API key o la libreria.
            AICopilotNetworkError: Si ocurre cualquier error de red o de la API.
        """
        prompt = self._build_prompt(template)

        try:
            model    = genai.GenerativeModel(model_name=_MODEL_NAME)
            response = model.generate_content(prompt)
            raw_text = response.text or ""
        except AICopilotError:
            raise
        except Exception as exc:
            raise AICopilotNetworkError(
                f"Error al conectar con Gemini API: {exc}"
            ) from exc

        return self._parse_payloads(raw_text)

    # ── Helpers privados ───────────────────────────────────────────────────────

    @staticmethod
    def _build_prompt(template: str) -> str:
        """
        Construye el prompt de instruccion para Gemini.

        El prompt analiza el contexto del marcador § (parametro URL, body JSON,
        cabecera HTTP, etc.) e instruye al modelo a generar payloads especificos
        en texto plano sin markdown.
        """
        snippet = template.strip()[:_MAX_TEMPLATE]

        return (
            f"Eres un experto en pentesting web. Analiza la siguiente plantilla "
            f"de peticion HTTP que contiene marcadores § indicando los puntos de "
            f"inyeccion:\n\n"
            f"--- PLANTILLA HTTP ---\n{snippet}\n"
            f"---------------------\n\n"
            f"Identifica el CONTEXTO de cada marcador § (parametro URL, campo JSON, "
            f"cabecera HTTP, cookie, etc.) y genera exactamente {_PAYLOAD_COUNT} "
            f"payloads de ataque optimizados para ese contexto.\n\n"
            f"Los payloads deben cubrir tecnicas variadas como:\n"
            f"- SQL Injection (clasica, blind, time-based)\n"
            f"- XSS (reflexivo, DOM, poliglota)\n"
            f"- Path Traversal / LFI\n"
            f"- Command Injection\n"
            f"- Bypass de autenticacion\n"
            f"- Fuzzing general (cadenas especiales, limites, null bytes)\n\n"
            f"REGLAS ESTRICTAS DE FORMATO:\n"
            f"1. Responde UNICAMENTE con los {_PAYLOAD_COUNT} payloads.\n"
            f"2. Un payload por linea, SIN numeracion ni viñetas.\n"
            f"3. SIN bloques de codigo markdown (``` o similar).\n"
            f"4. SIN texto introductorio, saludos ni explicaciones.\n"
            f"5. SIN lineas en blanco entre los payloads.\n"
            f"6. Solo texto plano, listo para ser copiado directamente.\n"
        )

    @staticmethod
    def _parse_payloads(raw: str) -> list[str]:
        """
        Limpia la respuesta de Gemini y devuelve una lista de payloads.

        - Elimina bloques markdown (```).
        - Descarta lineas vacias y lineas con solo guiones o numeracion.
        - Limita a ``_PAYLOAD_COUNT`` entradas.

        Args:
            raw: Texto crudo devuelto por Gemini.

        Returns:
            Lista de strings, cada uno un payload listo para usar.
        """
        payloads: list[str] = []

        for line in raw.splitlines():
            clean = line.strip()

            # Descartar lineas vacias o de markdown
            if not clean or clean.startswith("```"):
                continue

            # Descartar encabezados/separadores (----, ====)
            if all(c in "-=*#" for c in clean):
                continue

            # Descartar numeracion inicial (ej. "1. payload" -> "payload")
            if len(clean) > 2 and clean[0].isdigit() and clean[1] in ".):":
                clean = clean[2:].strip()

            # Descartar viñetas (-, *, •)
            if clean and clean[0] in "-*\u2022" and len(clean) > 1:
                clean = clean[1:].strip()

            if clean:
                payloads.append(clean)

            if len(payloads) >= _PAYLOAD_COUNT:
                break

        return payloads
