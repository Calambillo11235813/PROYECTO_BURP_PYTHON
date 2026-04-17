"""
repeater.py
-----------
Módulo B: Repeater — Lógica de reenvío manual de peticiones HTTP.

Responsabilidades (y SOLO estas):
    - Parsear una petición escrita en texto plano (string) al formato
      que necesita la librería `requests`.
    - Ejecutar el envío HTTP contra el servidor destino.
    - Retornar un objeto `RepeaterResponse` con el resultado.

Este módulo NO tiene dependencias con la GUI. Su única dependencia
externa es `requests`. Esto permite testearlo de forma aislada.

Casos de Uso cubiertos:
    CU-05: Clonación de Petición (recibe el raw y lo prepara para envío).
    CU-06: Reenvío Manipulado (el usuario edita el raw antes de llamar send()).

Autores: Diogo Nicolas Rodriguez Gomez, Javier Soliz Rueda
Materia: Ingeniería de Software 2
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

import requests
import urllib3

# Silenciar advertencias de SSL en requests (el certificado puede ser
# auto-firmado o no verificable en entornos de pentesting)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── Constantes ────────────────────────────────────────────────────────────────
DEFAULT_TIMEOUT = 15  # segundos de espera máxima por petición


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class RepeaterResponse:
    """
    Resultado de un envío ejecutado por el Repeater.

    Attributes:
        status_code  (int)        : Código HTTP de la respuesta (ej. 200, 404).
        http_version (str)        : Versión HTTP negociada (ej. "HTTP/1.1").
        headers      (dict)       : Cabeceras de la respuesta como dict.
        body         (str)        : Cuerpo de la respuesta decodificado (UTF-8).
        duration_ms  (float)      : Tiempo de ida y vuelta en milisegundos.
        error        (str | None) : Mensaje de error si la petición falló.

    Uso rápido:
        response.as_raw_text()  → texto completo listo para mostrar en UI.
    """

    status_code : int
    http_version: str
    headers     : dict[str, str]
    body        : str
    duration_ms : float
    error       : Optional[str] = field(default=None)

    @property
    def success(self) -> bool:
        """True si la petición se ejecutó sin errores de red."""
        return self.error is None

    def as_raw_text(self) -> str:
        """
        Serializa la respuesta completa en formato legible para el visor.

        Returns:
            Cadena con status line + headers + cuerpo separados por CRLF.
        """
        if not self.success:
            return f"[ERROR]\n{self.error}"

        lines: list[str] = [
            f"{self.http_version} {self.status_code}",
        ]
        for key, value in self.headers.items():
            lines.append(f"{key}: {value}")
        lines.append("")  # línea en blanco que separa headers del cuerpo
        lines.append(self.body)
        return "\n".join(lines)


# ── Clase principal ────────────────────────────────────────────────────────────

class Repeater:
    """
    Motor de reenvío manual de peticiones HTTP (Módulo B).

    Convierte un bloque de texto en formato HTTP crudo a una petición
    real usando la librería `requests`, ejecuta el envío y devuelve
    un `RepeaterResponse` con todos los detalles de la respuesta.

    El texto de la petición sigue el formato estándar HTTP:
        MÉTODO PATH HTTP/1.x
        Header-Nombre: Header-Valor
        ...
        [línea en blanco]
        [cuerpo opcional]

    Ejemplo de uso:
        r = Repeater()
        raw = "GET /index.html HTTP/1.1\\nHost: example.com\\n\\n"
        resp = r.send(raw, base_url="http://example.com")
        print(resp.as_raw_text())
    """

    def send(self, raw_request: str, timeout: int = DEFAULT_TIMEOUT) -> RepeaterResponse:
        """
        Ejecuta el envío de la petición descrita en `raw_request`.

        Parsea el texto crudo para extraer método, URL, cabeceras y cuerpo,
        luego realiza la petición con `requests` y retorna el resultado.

        Args:
            raw_request (str): Petición HTTP completa en texto plano,
                               incluyendo request-line, headers y body.
            timeout     (int): Tiempo máximo de espera en segundos.

        Returns:
            RepeaterResponse: Objeto con la respuesta completa o con
                              el campo `error` relleno si hubo fallo de red.
        """
        try:
            method, url, headers, body = self._parse_raw(raw_request)
        except ValueError as exc:
            return self._error_response(str(exc))

        start = time.perf_counter()
        try:
            resp = requests.request(
                method  = method,
                url     = url,
                headers = headers,
                data    = body.encode("utf-8") if body else None,
                timeout = timeout,
                verify  = False,   # pentesting: ignorar errores de SSL
                allow_redirects = False,  # el usuario decide si seguir redirects
            )
        except requests.exceptions.ConnectionError as exc:
            return self._error_response(f"Error de conexión: {exc}")
        except requests.exceptions.Timeout:
            return self._error_response(f"Timeout tras {timeout}s esperando respuesta.")
        except requests.exceptions.RequestException as exc:
            return self._error_response(f"Error en la petición: {exc}")

        duration_ms = (time.perf_counter() - start) * 1000

        # Detectar versión HTTP de la respuesta
        http_version = "HTTP/1.1"
        if hasattr(resp.raw, "version"):
            http_version = "HTTP/2" if resp.raw.version == 20 else "HTTP/1.1"

        return RepeaterResponse(
            status_code  = resp.status_code,
            http_version = http_version,
            headers      = dict(resp.headers),
            body         = resp.text,
            duration_ms  = duration_ms,
        )

    # ── Métodos internos ───────────────────────────────────────────────────────

    def _parse_raw(self, raw: str) -> tuple[str, str, dict[str, str], str]:
        """
        Descompone un bloque de texto HTTP crudo en sus partes fundamentales.

        Args:
            raw (str): Texto completo de la petición HTTP.

        Returns:
            Tupla (method, url, headers_dict, body).

        Raises:
            ValueError: Si el texto no tiene una request-line válida
                        o le falta la cabecera Host.
        """
        # Normalizar saltos de línea
        raw = raw.replace("\r\n", "\n").strip()

        # Separar cabeceras del cuerpo usando la línea en blanco
        if "\n\n" in raw:
            header_section, body = raw.split("\n\n", maxsplit=1)
        else:
            header_section, body = raw, ""

        lines = header_section.splitlines()
        if not lines:
            raise ValueError("La petición está vacía.")

        # Primera línea: METHOD PATH HTTP/VERSION
        request_line = lines[0].strip()
        parts = request_line.split()
        if len(parts) < 2:
            raise ValueError(
                f"Request-line inválida: '{request_line}'. "
                "Formato esperado: MÉTODO PATH HTTP/1.1"
            )
        method = parts[0].upper()
        path   = parts[1]

        # Parsear cabeceras (líneas 1..N del header_section)
        headers: dict[str, str] = {}
        for line in lines[1:]:
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            headers[key.strip()] = value.strip()

        # Construir la URL completa usando la cabecera Host
        host = headers.get("Host", "")
        if not host:
            raise ValueError(
                "Falta la cabecera 'Host'. "
                "El Repeater la necesita para construir la URL destino."
            )

        scheme = "https" if ":443" in host else "http"
        # Limpiar el puerto del host para evitar duplicarlo en la URL
        clean_host = host.replace(":443", "").replace(":80", "")

        # Si path ya contiene una URL absoluta (http://...) úsala directamente
        if path.startswith("http://") or path.startswith("https://"):
            url = path
        else:
            url = f"{scheme}://{clean_host}{path}"

        return method, url, headers, body

    @staticmethod
    def _error_response(message: str) -> RepeaterResponse:
        """Crea un RepeaterResponse representando un error de red o parseo."""
        return RepeaterResponse(
            status_code  = 0,
            http_version = "—",
            headers      = {},
            body         = "",
            duration_ms  = 0.0,
            error        = message,
        )
