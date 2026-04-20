"""
intruder.py
-----------
Módulo C: Intruder — Motor de fuzzing automatizado.

Responsabilidades (y SOLO estas):
    - Cargar diccionarios de payloads desde archivos .txt (CU-09).
    - Validar que la plantilla de petición contenga puntos de inyección
      marcados con §payload§ (CU-08).
    - Ejecutar el ataque: sustituir el marcador por cada payload,
      enviar la petición HTTP y registrar el resultado (CU-10).
    - Permitir detener el ataque de forma thread-safe.

Este módulo NO tiene dependencias con la GUI. Su única dependencia
externa es `requests`. Esto permite testearlo de forma aislada.

Marcador de inyección: §payload§
    El texto entre los dos símbolos § es reemplazado por cada payload
    en cada iteración del ataque. Si el template contiene el marcador
    literal §FUZZ§, ese fragmento es el punto de inyección.

Casos de Uso cubiertos:
    CU-08: Definición de Puntos de Inyección.
    CU-09: Gestión de Payloads (cargar diccionarios .txt).
    CU-10: Ejecución de Ataque (envío masivo con registro de variaciones).

Autores: Diogo Nicolas Rodriguez Gomez, Javier Soliz Rueda
Materia: Ingeniería de Software 2
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import requests
import urllib3

# Silenciar advertencias de SSL en entornos de pentesting
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ── Constantes ────────────────────────────────────────────────────────────────

# Marcador que delimita el punto de inyección en la plantilla de petición.
# El usuario debe escribir §texto§ para indicar qué parte se sustituirá.
INJECTION_MARKER = "§"

# Expresión regular que captura todo lo que hay entre dos § (punto de inyección)
_MARKER_PATTERN = re.compile(r"§[^§]*§")

DEFAULT_TIMEOUT  = 10   # segundos por petición
DEFAULT_THREADS  = 5    # hilos concurrentes máximos
MAX_THREADS      = 20   # límite absoluto de hilos


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class IntruderResult:
    """
    Resultado de un envío individual durante el ataque Intruder.

    Attributes:
        index       (int)        : Número de orden del intento (1-based).
        payload     (str)        : Payload usado en esta iteración.
        status_code (int)        : Código HTTP de la respuesta (0 si hubo error).
        length      (int)        : Longitud del cuerpo de la respuesta en bytes.
        duration_ms (float)      : Tiempo de ida y vuelta en milisegundos.
        error       (str | None) : Mensaje de error si la petición falló.
    """
    index       : int
    payload     : str
    status_code : int
    length      : int
    duration_ms : float
    error       : Optional[str] = field(default=None)

    @property
    def success(self) -> bool:
        """True si la petición se completó sin errores de red."""
        return self.error is None


# ── Clase principal ────────────────────────────────────────────────────────────

class Intruder:
    """
    Motor de fuzzing automatizado (Módulo C).

    Flujo de uso típico:
        intruder = Intruder()
        payloads = intruder.load_payloads("payloads/sqli.txt")
        intruder.set_template(raw_request_with_markers)
        intruder.run(
            payloads  = payloads,
            on_result = mi_callback,   # llamado por cada resultado
            threads   = 5,
            timeout   = 10,
        )

    El template debe contener al menos un marcador §texto§.
    Ejemplo:
        GET /search?q=§test§ HTTP/1.1
        Host: example.com

    El texto entre § se sustituye por cada payload en cada iteración.
    """

    def __init__(self) -> None:
        self._template    : str         = ""
        self._stop_flag   : bool        = False
        self._lock        : threading.Lock = threading.Lock()
        self._active_threads: list[threading.Thread] = []

    # ── API pública ────────────────────────────────────────────────────────────

    def load_payloads(self, path: str) -> list[str]:
        """
        Carga un diccionario de payloads desde un archivo .txt (CU-09).

        Cada línea no vacía del archivo es un payload independiente.
        Las líneas que empiezan con '#' se tratan como comentarios y se ignoran.

        Args:
            path (str): Ruta al archivo de payloads (.txt).

        Returns:
            list[str]: Lista de payloads cargados.

        Raises:
            FileNotFoundError: Si el archivo no existe en la ruta indicada.
            ValueError: Si el archivo está vacío o solo contiene comentarios.
        """
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Archivo de payloads no encontrado: {path}")

        payloads: list[str] = []
        with p.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    payloads.append(stripped)

        if not payloads:
            raise ValueError(
                f"El archivo '{path}' no contiene payloads válidos. "
                "Asegúrate de que tenga al menos una línea no vacía y sin '#'."
            )

        return payloads

    def set_template(self, raw_request: str) -> None:
        """
        Establece la plantilla de la petición HTTP con marcadores de inyección (CU-08).

        Valida que el template contenga al menos un marcador §…§.

        Args:
            raw_request (str): Petición HTTP completa con marcadores §payload§.

        Raises:
            ValueError: Si el template no contiene ningún marcador §…§.
        """
        if not _MARKER_PATTERN.search(raw_request):
            raise ValueError(
                "El template no contiene ningún punto de inyección.\n"
                "Añade el marcador §texto§ alrededor de la parte que quieres atacar.\n"
                "Ejemplo:  GET /search?q=§test§ HTTP/1.1"
            )
        self._template = raw_request

    def validate_template(self, raw_request: str) -> bool:
        """
        Comprueba (sin lanzar excepción) si un template tiene marcadores válidos.

        Args:
            raw_request (str): Texto de la petición a validar.

        Returns:
            bool: True si contiene al menos un marcador §…§, False en caso contrario.
        """
        return bool(_MARKER_PATTERN.search(raw_request))

    def stop(self) -> None:
        """
        Señala al motor de ataque que debe detenerse (thread-safe).

        Los hilos en vuelo terminarán su petición actual pero no
        iniciarán ninguna nueva iteración.
        """
        with self._lock:
            self._stop_flag = True

    def is_running(self) -> bool:
        """Retorna True si hay hilos de ataque activos actualmente."""
        return any(t.is_alive() for t in self._active_threads)

    def run(
        self,
        payloads  : list[str],
        on_result : Callable[[IntruderResult], None],
        threads   : int = DEFAULT_THREADS,
        timeout   : int = DEFAULT_TIMEOUT,
    ) -> None:
        """
        Ejecuta el ataque de fuzzing (CU-10).

        Itera sobre la lista de payloads, sustituye el marcador §…§ en el
        template por cada payload y envía la petición HTTP. Cada resultado
        se reporta inmediatamente mediante el callback `on_result`, que es
        llamado desde el hilo de trabajo (NO desde el hilo principal de la GUI).

        El método es BLOQUEANTE: retorna cuando todos los payloads han sido
        procesados o cuando se ha llamado a stop(). La GUI debe llamarlo
        desde un hilo daemon.

        Args:
            payloads  (list[str]): Lista de strings a inyectar.
            on_result (Callable) : Función llamada con cada IntruderResult.
                                   Nota: se llama desde hilos de trabajo.
            threads   (int)      : Número máximo de hilos concurrentes (1-20).
            timeout   (int)      : Segundos de espera máxima por petición.
        """
        # Resetear flag de stop para una nueva ejecución
        with self._lock:
            self._stop_flag = False

        threads = max(1, min(threads, MAX_THREADS))

        # Semáforo para limitar la concurrencia
        semaphore = threading.Semaphore(threads)
        self._active_threads = []

        for idx, payload in enumerate(payloads, start=1):
            # Verificar cancelación antes de lanzar cada hilo
            with self._lock:
                if self._stop_flag:
                    break

            semaphore.acquire()

            t = threading.Thread(
                target=self._attack_worker,
                args=(idx, payload, on_result, semaphore, timeout),
                daemon=True,
                name=f"IntruderWorker-{idx}",
            )
            self._active_threads.append(t)
            t.start()

        # Esperar a que todos los hilos lanzados terminen
        for t in self._active_threads:
            t.join()

    # ── Métodos internos ───────────────────────────────────────────────────────

    def _attack_worker(
        self,
        idx       : int,
        payload   : str,
        on_result : Callable[[IntruderResult], None],
        semaphore : threading.Semaphore,
        timeout   : int,
    ) -> None:
        """
        Hilo de trabajo: sustituye el payload, envía la petición y reporta.

        Args:
            idx       (int)      : Índice del intento (1-based).
            payload   (str)      : Payload a inyectar.
            on_result (Callable) : Callback para reportar el resultado.
            semaphore            : Semáforo compartido para limitar concurrencia.
            timeout   (int)      : Timeout en segundos para la petición HTTP.
        """
        try:
            result = self._send_one(idx, payload, timeout)
        finally:
            semaphore.release()

        on_result(result)

    def _send_one(self, idx: int, payload: str, timeout: int) -> IntruderResult:
        """
        Construye y envía una única petición con el payload sustituido.

        Args:
            idx     (int): Índice del intento.
            payload (str): Payload a inyectar en el template.
            timeout (int): Timeout en segundos.

        Returns:
            IntruderResult: Resultado del envío.
        """
        # Sustituir el marcador §…§ por el payload
        raw = _MARKER_PATTERN.sub(payload, self._template)

        try:
            method, url, headers, body = self._parse_template(raw)
        except ValueError as exc:
            return IntruderResult(
                index=idx, payload=payload,
                status_code=0, length=0, duration_ms=0.0,
                error=str(exc),
            )

        start = time.perf_counter()
        try:
            resp = requests.request(
                method          = method,
                url             = url,
                headers         = headers,
                data            = body.encode("utf-8") if body else None,
                timeout         = timeout,
                verify          = False,
                allow_redirects = False,
            )
            duration_ms = (time.perf_counter() - start) * 1000
            return IntruderResult(
                index       = idx,
                payload     = payload,
                status_code = resp.status_code,
                length      = len(resp.content),
                duration_ms = duration_ms,
            )

        except requests.exceptions.ConnectionError as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            return IntruderResult(
                index=idx, payload=payload,
                status_code=0, length=0, duration_ms=duration_ms,
                error=f"Error de conexión: {exc}",
            )
        except requests.exceptions.Timeout:
            duration_ms = (time.perf_counter() - start) * 1000
            return IntruderResult(
                index=idx, payload=payload,
                status_code=0, length=0, duration_ms=duration_ms,
                error=f"Timeout tras {timeout}s.",
            )
        except requests.exceptions.RequestException as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            return IntruderResult(
                index=idx, payload=payload,
                status_code=0, length=0, duration_ms=duration_ms,
                error=f"Error en la petición: {exc}",
            )

    @staticmethod
    def _parse_template(raw: str) -> tuple[str, str, dict[str, str], str]:
        """
        Descompone el texto HTTP crudo (ya con payload sustituido) en sus partes.

        Sigue el mismo patrón que Repeater._parse_raw() para consistencia.

        Args:
            raw (str): Petición HTTP en texto plano, con payload ya inyectado.

        Returns:
            Tupla (method, url, headers_dict, body).

        Raises:
            ValueError: Si la request-line es inválida o falta la cabecera Host.
        """
        raw = raw.replace("\r\n", "\n").strip()

        if "\n\n" in raw:
            header_section, body = raw.split("\n\n", maxsplit=1)
        else:
            header_section, body = raw, ""

        lines = header_section.splitlines()
        if not lines:
            raise ValueError("El template está vacío tras sustituir el payload.")

        parts = lines[0].strip().split()
        if len(parts) < 2:
            raise ValueError(
                f"Request-line inválida: '{lines[0]}'. "
                "Formato esperado: MÉTODO PATH HTTP/1.1"
            )

        method = parts[0].upper()
        path   = parts[1]

        headers: dict[str, str] = {}
        for line in lines[1:]:
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            headers[key.strip()] = value.strip()

        host = headers.get("Host", "")
        if not host:
            raise ValueError(
                "Falta la cabecera 'Host' en el template. "
                "El Intruder la necesita para construir la URL destino."
            )

        scheme = "https" if ":443" in host else "http"
        clean_host = host.replace(":443", "").replace(":80", "")

        if path.startswith("http://") or path.startswith("https://"):
            url = path
        else:
            url = f"{scheme}://{clean_host}{path}"

        return method, url, headers, body
