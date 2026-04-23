"""
gui/utils.py
------------
Utilidades compartidas para la interfaz gráfica.

Autores: Diogo Nicolas Rodriguez Gomez, Javier Soliz Rueda
Materia: Ingeniería de Software 2
"""

import re
import tkinter as tk

_TAG_HTTP_METHOD = "http_method"
_TAG_HTTP_HEADER_KEY = "http_header_key"
_TAG_JSON_KEY = "json_key"
_TAG_JSON_STRING = "json_string"

_MAX_JSON_HIGHLIGHT_CHARS = 20000

def apply_syntax_highlighting(textbox: tk.Text) -> None:
    """
    Aplica resaltado básico HTTP/JSON en un widget Text de Tkinter o CTkTextbox.

    Esta función extrae los patrones clave de una petición o respuesta HTTP y les 
    aplica colores específicos para mejorar la legibilidad.
    Resalta:
      - El método HTTP en la request line (GET, POST, etc.) en azul.
      - Nombres de cabeceras HTTP (Host, User-Agent, etc.) en naranja.
      - Claves y strings de cuerpos JSON, con un límite de tamaño para evitar
        congelar la interfaz en payloads masivos.

    Args:
        textbox (tk.Text): El widget de texto donde se aplicará el resaltado. 
                           El contenido ya debe estar cargado en el widget.
    """
    content = textbox.get("1.0", "end-1c")

    # Configuración de tags (idempotente: puede llamarse muchas veces).
    textbox.tag_config(_TAG_HTTP_METHOD, foreground="#4FC3F7")
    textbox.tag_config(_TAG_HTTP_HEADER_KEY, foreground="#F5A524")
    textbox.tag_config(_TAG_JSON_KEY, foreground="#C792EA")
    textbox.tag_config(_TAG_JSON_STRING, foreground="#7FDBCA")

    # Limpiar resaltado previo.
    for tag in (_TAG_HTTP_METHOD, _TAG_HTTP_HEADER_KEY, _TAG_JSON_KEY, _TAG_JSON_STRING):
        textbox.tag_remove(tag, "1.0", "end")

    if not content:
        return

    # 1) Método HTTP en primera línea.
    method_match = re.search(
        r"^(GET|POST|PUT|DELETE|PATCH|OPTIONS|HEAD|CONNECT|TRACE)\b",
        content,
    )
    if method_match:
        start, end = method_match.span(1)
        textbox.tag_add(_TAG_HTTP_METHOD, f"1.0+{start}c", f"1.0+{end}c")

    # 2) Claves de headers (solo bloque de cabeceras, antes del body).
    headers_end = re.search(r"\r?\n\r?\n", content)
    if headers_end:
        header_block_end = headers_end.start()
    else:
        header_block_end = len(content)

    first_line_end = content.find("\n")
    headers_start = first_line_end + 1 if first_line_end != -1 else len(content)
    headers_text = content[headers_start:header_block_end]

    for match in re.finditer(r"(?m)^([!#$%&'*+\-.^_`|~0-9A-Za-z]+)(?=\s*:)", headers_text):
        key_start = headers_start + match.start(1)
        key_end = headers_start + match.end(1)
        textbox.tag_add(_TAG_HTTP_HEADER_KEY, f"1.0+{key_start}c", f"1.0+{key_end}c")

    # 3) JSON body (limitado para evitar congelar UI en payloads grandes).
    if not headers_end:
        return

    body_start = headers_end.end()
    body_text = content[body_start:]
    if not body_text:
        return

    if not body_text.lstrip().startswith(("{", "[")):
        return

    json_scan = body_text[:_MAX_JSON_HIGHLIGHT_CHARS]

    for match in re.finditer(r'"(?:[^"\\]|\\.)*"', json_scan):
        s = body_start + match.start()
        e = body_start + match.end()
        textbox.tag_add(_TAG_JSON_STRING, f"1.0+{s}c", f"1.0+{e}c")

    for match in re.finditer(r'("(?:[^"\\]|\\.)*")\s*:', json_scan):
        s = body_start + match.start(1)
        e = body_start + match.end(1)
        textbox.tag_add(_TAG_JSON_KEY, f"1.0+{s}c", f"1.0+{e}c")

    textbox.tag_raise(_TAG_JSON_KEY)
