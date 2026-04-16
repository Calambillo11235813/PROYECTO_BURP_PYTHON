"""
history.py
----------
CU-03: Visualización de Historial (Logs)

Implementa el historial persistente de peticiones interceptadas por el proxy.

Responsabilidades:
    - Almacenar cada petición/respuesta en un objeto RequestRecord
    - Proveer filtros por método HTTP, host y código de respuesta
    - Exportar el historial a .txt y .csv

Autores: Diogo Nicolas Rodriguez Gomez, Javier Soliz Rueda
Materia: Ingeniería de Software 2
"""

import csv
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


# ─────────────────────────────────────────────
#  Dataclass: RequestRecord
# ─────────────────────────────────────────────
@dataclass
class RequestRecord:
    """
    Representa una petición HTTP/HTTPS interceptada junto con su respuesta.

    Args:
        id            (int)      : Número secuencial de la petición.
        timestamp     (datetime) : Momento exacto de la intercepción.
        method        (str)      : Verbo HTTP (GET, POST, CONNECT, ...).
        host          (str)      : Host destino.
        port          (int)      : Puerto destino.
        path          (str)      : Path de la URL.
        headers       (dict)     : Cabeceras HTTP como diccionario.
        body          (bytes)    : Cuerpo de la petición (puede ser vacío).
        raw_request   (bytes)    : Bytes crudos completos de la petición.
        response_status (str)    : Primera línea de la respuesta (ej: "HTTP/1.1 200 OK").
        response_raw  (bytes)    : Bytes completos de la respuesta.
        duration_ms   (float)    : Tiempo de round-trip en milisegundos.
        client_ip     (str)      : IP del cliente que originó la petición.
    """
    id              : int
    timestamp       : datetime
    method          : str
    host            : str
    port            : int
    path            : str
    headers         : dict      = field(default_factory=dict)
    body            : bytes     = b""
    raw_request     : bytes     = b""
    response_status : str       = ""
    response_raw    : bytes     = b""
    duration_ms     : float     = 0.0
    client_ip       : str       = ""

    # ── Propiedades de conveniencia ──────────────────────────
    @property
    def url(self) -> str:
        """URL completa reconstruida (sin scheme para CONNECT)."""
        if self.method.upper() == "CONNECT":
            return f"{self.host}:{self.port}"
        scheme = "https" if self.port == 443 else "http"
        port_str = f":{self.port}" if self.port not in (80, 443) else ""
        return f"{scheme}://{self.host}{port_str}{self.path}"

    @property
    def status_code(self) -> int:
        """
        Extrae el código de estado numérico de response_status.

        Retorna:
            int: Código HTTP (ej. 200, 404) ó 0 si no aplica (CONNECT/error).
        """
        try:
            # "HTTP/1.1 200 OK" → 200
            return int(self.response_status.split()[1])
        except (IndexError, ValueError):
            return 0

    @property
    def timestamp_str(self) -> str:
        """Timestamp formateado para mostrar en consola o exportar."""
        return self.timestamp.strftime("%Y-%m-%d %H:%M:%S")

    def to_dict(self) -> dict:
        """
        Serializa el registro a un diccionario plano (apto para CSV).

        Retorna:
            dict: Campos escalares del registro (excluye bytes crudos).
        """
        return {
            "id"              : self.id,
            "timestamp"       : self.timestamp_str,
            "method"          : self.method,
            "host"            : self.host,
            "port"            : self.port,
            "path"            : self.path,
            "url"             : self.url,
            "status_code"     : self.status_code,
            "response_status" : self.response_status,
            "duration_ms"     : round(self.duration_ms, 2),
            "body_size_bytes" : len(self.body),
            "client_ip"       : self.client_ip,
        }

    def __str__(self) -> str:
        return (
            f"[#{self.id:04d}] {self.timestamp_str} | "
            f"{self.method:<7} {self.url:<50} | "
            f"{self.response_status or 'TUNNEL':<20} | "
            f"{self.duration_ms:.1f}ms"
        )


# ─────────────────────────────────────────────
#  Clase principal: History
# ─────────────────────────────────────────────
class History:
    """
    Historial persistente (en memoria) de todas las peticiones interceptadas.

    Thread-safe: usa un RLock para que múltiples hilos del ProxyServer
    puedan agregar registros de forma segura al mismo tiempo.

    Métodos principales:
        add(record)           → agrega un RequestRecord al historial
        filter(...)           → retorna una lista filtrada de registros
        export_txt(path)      → exporta el historial a un archivo .txt
        export_csv(path)      → exporta el historial a un archivo .csv
        print_table()         → imprime una tabla resumen en consola
        clear()               → vacía el historial
    """

    def __init__(self):
        self._records: list[RequestRecord] = []
        # RLock (reentrant): el mismo hilo puede adquirirlo varias veces
        self._lock = threading.RLock()

    # ── Agregar registro (thread-safe) ───────────────────────
    def add(self, record: RequestRecord) -> None:
        """
        Agrega un RequestRecord al historial de forma thread-safe.

        Args:
            record (RequestRecord): Petición interceptada a almacenar.
        """
        with self._lock:
            self._records.append(record)

    # ── Acceso de lectura ─────────────────────────────────────
    def all(self) -> list[RequestRecord]:
        """
        Retorna una copia de todos los registros almacenados.

        Retorna:
            list[RequestRecord]: Lista completa del historial.
        """
        with self._lock:
            return list(self._records)

    def get_by_id(self, req_id: int) -> RequestRecord | None:
        """
        Busca un registro por su ID secuencial.

        Args:
            req_id (int): ID de la petición a buscar.

        Retorna:
            RequestRecord | None: El registro encontrado o None.
        """
        with self._lock:
            for r in self._records:
                if r.id == req_id:
                    return r
        return None

    # ── Filtros ───────────────────────────────────────────────
    def filter(
        self,
        method      : str | None = None,
        host        : str | None = None,
        status_code : int | None = None,
        min_status  : int | None = None,
        max_status  : int | None = None,
    ) -> list[RequestRecord]:
        """
        Filtra el historial por uno o múltiples criterios en combinación (AND).

        Args:
            method      (str|None) : Verbo HTTP exacto (ej. "GET", "POST").
                                     Case-insensitive.
            host        (str|None) : Substring del host destino
                                     (ej. "google" matchea "www.google.com").
            status_code (int|None) : Código HTTP exacto (ej. 200, 404).
            min_status  (int|None) : Código mínimo del rango (inclusive).
            max_status  (int|None) : Código máximo del rango (inclusive).

        Retorna:
            list[RequestRecord]: Lista de registros que cumplen todos los filtros.

        Ejemplo:
            history.filter(method="POST", min_status=400, max_status=599)
        """
        with self._lock:
            results = list(self._records)

        if method is not None:
            results = [r for r in results if r.method.upper() == method.upper()]

        if host is not None:
            results = [r for r in results if host.lower() in r.host.lower()]

        if status_code is not None:
            results = [r for r in results if r.status_code == status_code]

        if min_status is not None:
            results = [r for r in results if r.status_code >= min_status]

        if max_status is not None:
            results = [r for r in results if r.status_code <= max_status]

        return results

    # ── Exportar a TXT ────────────────────────────────────────
    def export_txt(self, filepath: str | Path, records: list[RequestRecord] | None = None) -> Path:
        """
        Exporta el historial (o un subconjunto filtrado) a un archivo .txt
        con formato tabular legible.

        Args:
            filepath (str|Path)               : Ruta del archivo de salida.
            records  (list[RequestRecord]|None): Registros a exportar.
                                                 Si es None, exporta todo.

        Retorna:
            Path: Ruta absoluta del archivo generado.
        """
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = records if records is not None else self.all()

        with open(path, "w", encoding="utf-8") as f:
            # Encabezado
            f.write("=" * 100 + "\n")
            f.write(" HISTORIAL DE PETICIONES INTERCEPTADAS — Mini-Burp Suite\n")
            f.write(f" Exportado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    f"  |  Total: {len(data)} peticiones\n")
            f.write("=" * 100 + "\n\n")

            # Cabecera de columnas
            header = (
                f"{'#':<6} {'Timestamp':<20} {'Método':<8} "
                f"{'Host':<35} {'Path':<30} {'Status':<25} {'ms':>7}"
            )
            f.write(header + "\n")
            f.write("-" * 100 + "\n")

            for r in data:
                path_display = r.path[:28] + ".." if len(r.path) > 30 else r.path
                host_display = r.host[:33] + ".." if len(r.host) > 35 else r.host
                status_display = r.response_status or "TUNNEL"

                line = (
                    f"{r.id:<6} {r.timestamp_str:<20} {r.method:<8} "
                    f"{host_display:<35} {path_display:<30} "
                    f"{status_display:<25} {r.duration_ms:>7.1f}"
                )
                f.write(line + "\n")

                # Si hay body, mostrarlo debajo (máx 200 chars)
                if r.body:
                    try:
                        body_str = r.body.decode("utf-8", errors="replace")[:200]
                        f.write(f"       Body: {body_str}\n")
                    except Exception:
                        pass

            f.write("\n" + "=" * 100 + "\n")

        return path.resolve()

    # ── Exportar a CSV ────────────────────────────────────────
    def export_csv(self, filepath: str | Path, records: list[RequestRecord] | None = None) -> Path:
        """
        Exporta el historial (o un subconjunto filtrado) a un archivo .csv
        apto para abrir en Excel o procesar con pandas.

        Args:
            filepath (str|Path)               : Ruta del archivo de salida.
            records  (list[RequestRecord]|None): Registros a exportar.
                                                 Si es None, exporta todo.

        Retorna:
            Path: Ruta absoluta del archivo generado.
        """
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = records if records is not None else self.all()

        fieldnames = [
            "id", "timestamp", "method", "host", "port",
            "path", "url", "status_code", "response_status",
            "duration_ms", "body_size_bytes", "client_ip",
        ]

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in data:
                writer.writerow(r.to_dict())

        return path.resolve()

    # ── Imprimir tabla en consola ─────────────────────────────
    def print_table(self, records: list[RequestRecord] | None = None) -> None:
        """
        Imprime una tabla resumen del historial directamente en la consola.

        Args:
            records (list[RequestRecord]|None): Subconjunto a mostrar.
                                                Si es None, muestra todo.
        """
        data = records if records is not None else self.all()

        if not data:
            print("  [Historial vacío]")
            return

        header = (
            f"  {'#':<6} {'Timestamp':<20} {'Método':<8} "
            f"{'Host':<30} {'Status':<25} {'ms':>7}"
        )
        separator = "  " + "-" * 98

        print(separator)
        print(header)
        print(separator)

        for r in data:
            host_display  = r.host[:28] + ".."  if len(r.host)  > 30 else r.host
            status_display = r.response_status or "TUNNEL"
            print(
                f"  {r.id:<6} {r.timestamp_str:<20} {r.method:<8} "
                f"{host_display:<30} {status_display:<25} {r.duration_ms:>7.1f}"
            )

        print(separator)
        print(f"  Total: {len(data)} petición(es)\n")

    # ── Limpiar historial ─────────────────────────────────────
    def clear(self) -> None:
        """Vacía el historial completamente de forma thread-safe."""
        with self._lock:
            self._records.clear()

    # ── Dunder helpers ────────────────────────────────────────
    def __len__(self) -> int:
        with self._lock:
            return len(self._records)

    def __iter__(self):
        return iter(self.all())
