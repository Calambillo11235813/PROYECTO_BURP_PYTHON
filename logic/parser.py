"""
logic/parser.py
---------------
Principio de Responsabilidad Única: este módulo SOLO parsea bytes HTTP.
No abre sockets, no gestiona hilos, no imprime en consola.

Expone:
    ParsedRequest  → dataclass con los campos extraídos de una petición.
    parse_request  → función principal que convierte bytes → ParsedRequest.

Criterios de normalización (para la tabla de la GUI):
    HOST  : siempre el hostname puro (sin puerto). El puerto va en su
            propio campo 'port'. La capa de presentación decide si
            mostrar 'host' o 'host:port'.
    PATH  : ruta del recurso ('/api/v1/login').
            Para CONNECT (túnel HTTPS) se usa la constante CONNECT_PATH.

Autores: Diogo Nicolas Rodriguez Gomez, Javier Soliz Rueda
Materia: Ingeniería de Software 2
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Path descriptivo para peticiones CONNECT (túnel cifrado sin ruta de recurso)
CONNECT_PATH = "[HTTPS Tunnel]"


# ─────────────────────────────────────────────
#  Dataclass de resultado
# ─────────────────────────────────────────────
@dataclass
class ParsedRequest:
    """
    Resultado del parseo de una petición HTTP cruda.

    Attributes:
        method  (str)  : Verbo HTTP (GET, POST, CONNECT, …).
        host    (str)  : Nombre de host destino.
        port    (int)  : Puerto destino (80 por defecto, 443 para HTTPS).
        path    (str)  : Path de la URL (ej. "/api/users").
        headers (dict) : Cabeceras HTTP como diccionario clave→valor.
        body    (bytes): Cuerpo de la petición (puede ser vacío).
    """
    method  : str
    host    : str
    port    : int
    path    : str
    headers : dict  = field(default_factory=dict)
    body    : bytes = b""


# ─────────────────────────────────────────────
#  Función principal de parseo
# ─────────────────────────────────────────────
def parse_request(raw: bytes) -> ParsedRequest | None:
    """
    Descompone una petición HTTP cruda en sus partes componentes.

    Soporta tres formatos de Request-Line:
        - URL absoluta : GET http://example.com/path HTTP/1.1
        - URL relativa : POST /api/login HTTP/1.1  (host en cabecera Host:)
        - CONNECT      : CONNECT github.com:443 HTTP/1.1  (tunnel HTTPS)

    Args:
        raw (bytes): Bytes crudos recibidos del socket del navegador.

    Returns:
        ParsedRequest | None: Campos parseados, o None si la petición
                              está vacía o malformada.
    """
    if not raw:
        return None

    try:
        # ── 1. Separar cabeceras del body ──────────────────────────────
        if b"\r\n\r\n" in raw:
            header_section, body = raw.split(b"\r\n\r\n", 1)
        else:
            header_section, body = raw, b""

        lines = header_section.decode("utf-8", errors="replace").split("\r\n")
        if not lines or not lines[0]:
            return None

        # ── 2. Parsear la Request-Line ─────────────────────────────────
        parts = lines[0].split(" ")
        if len(parts) < 2:
            return None

        method = parts[0]
        url    = parts[1]

        # ── 3. Extraer host, puerto y path ─────────────────────────────
        host, port, path = _extract_host_port_path(method, url, lines[1:])

        # ── 4. Parsear cabeceras como diccionario ──────────────────────
        headers: dict[str, str] = {}
        for line in lines[1:]:
            if ": " in line:
                key, value = line.split(": ", 1)
                headers[key.strip()] = value.strip()

        return ParsedRequest(
            method=method,
            host=host,
            port=port,
            path=path,
            headers=headers,
            body=body,
        )

    except Exception:
        return None


# ─────────────────────────────────────────────
#  Helpers privados de parseo
# ─────────────────────────────────────────────
def _extract_host_port_path(
    method: str,
    url: str,
    header_lines: list[str],
) -> tuple[str, int, str]:
    """
    Determina (host, port, path) según el tipo de petición.

    Args:
        method       (str)      : Verbo HTTP.
        url          (str)      : Segunda parte de la Request-Line.
        header_lines (list[str]): Líneas de cabecera sin la Request-Line.

    Returns:
        tuple[str, int, str]: (host, puerto, path)
    """
    if method.upper() == "CONNECT":
        # CONNECT host:443 HTTP/1.1 — no hay ruta de recurso, es un túnal TCP
        parts = url.split(":")
        host  = parts[0]
        port  = int(parts[1]) if len(parts) > 1 else 443
        # PATH descriptivo: indica que es un túnal cifrado, no una ruta real
        return host, port, CONNECT_PATH

    if url.startswith("http://"):
        return _parse_absolute_url(url)

    # URL relativa → host en cabecera Host:
    return _host_from_headers(url, header_lines)


def _parse_absolute_url(url: str) -> tuple[str, int, str]:
    """
    Parsea una URL absoluta tipo 'http://host[:port]/path'.

    Args:
        url (str): URL incluyendo el scheme 'http://'.

    Returns:
        tuple[str, int, str]: (host_puro, puerto, path)
    """
    stripped  = url[7:]   # quitar "http://"
    if "/" in stripped:
        host_part, rest = stripped.split("/", 1)
        path = "/" + rest
    else:
        host_part = stripped
        path      = "/"

    if ":" in host_part:
        host, port_str = host_part.split(":", 1)
        return host.strip(), int(port_str), path or "/"

    return host_part.strip(), 80, path or "/"


def _host_from_headers(
    path: str,
    header_lines: list[str],
) -> tuple[str, int, str]:
    """
    Extrae host y puerto desde la cabecera 'Host:' cuando la URL es relativa.

    La cabecera Host puede tener el formato:
        Host: example.com          → host='example.com', port=80
        Host: example.com:8080     → host='example.com', port=8080
        Host: secure.com:443       → host='secure.com',  port=443

    Args:
        path         (str)      : Path ya conocido de la Request-Line.
        header_lines (list[str]): Líneas de cabeceras sin la Request-Line.

    Returns:
        tuple[str, int, str]: (host_puro, puerto, path)
    """
    for line in header_lines:
        if line.lower().startswith("host:"):
            host_value = line.split(":", 1)[1].strip()
            # Separar host del puerto si viene incluido ("host:port")
            if ":" in host_value:
                host, port_str = host_value.rsplit(":", 1)
                try:
                    return host.strip(), int(port_str), path or "/"
                except ValueError:
                    # Si el port_str no es numérico (poco común), ignorar
                    return host_value.strip(), 80, path or "/"
            return host_value.strip(), 80, path or "/"

    return "", 80, path or "/"


def display_host(host: str, port: int) -> str:
    """
    Genera la cadena de host que se muestra en la tabla de la GUI.

    Criterio de presentación:
        - Puerto 80  (HTTP)  : mostrar solo el host (el puerto es implícito).
        - Puerto 443 (HTTPS) : mostrar 'host:443' para dejar claro que es HTTPS.
        - Cualquier otro     : mostrar 'host:puerto' (puerto no estándar).

    Esta función se llama en el hilo del proxy (ConnectionHandler) antes
    de almacenar el registro, para que la GUI solo muestre strings ya limpios.

    Args:
        host (str): Hostname puro (sin puerto).
        port (int): Número de puerto.

    Returns:
        str: Cadena de presentación, ej. 'www.google.com' o 'api.x.com:443'.
    """
    if port == 80:
        return host
    return f"{host}:{port}"
