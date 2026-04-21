"""
gui/proxy_events.py
-------------------
Mixin con todos los manejadores de eventos de la pestaña Proxy.

Principio de Responsabilidad Única:
    Este archivo SOLO contiene la lógica de "qué pasa cuando el usuario
    interactúa". La construcción visual de la UI vive en proxy_tab.py.

Patrón de diseño: Mixin — se combina con ProxyTab mediante herencia
múltiple de Python. No hereda de ninguna clase base; accede a `self`
directamente asumiendo los atributos definidos en ProxyTab.

Atributos que este mixin asume que existen en `self`:
    proxy            (ProxyServer)          : instancia del proxy.
    _pending         (PendingRequest|None)  : petición interceptada activa.
    _tree            (ttk.Treeview)         : tabla de historial.
    _editor_box      (ctk.CTkTextbox)       : visor/editor inferior.
    _editor_lbl      (ctk.CTkLabel)         : etiqueta del editor.
    _intercept_btn   (ctk.CTkButton)        : botón Intercept ON/OFF.
    _btn_forward     (ctk.CTkButton)        : botón Forward.
    _btn_drop        (ctk.CTkButton)        : botón Drop.
    _btn_repeater    (ctk.CTkButton)        : botón Send to Repeater.
    _count_lbl       (ctk.CTkLabel)         : contador de peticiones.
    _seen_ids        (set[int])             : IDs ya pintados en la tabla.
    _auto_scroll_var (tk.BooleanVar)        : estado del checkbox de scroll.
    _repeater_callback (Callable|None)      : callback CU-05.

Autores: Diogo Nicolas Rodriguez Gomez, Javier Soliz Rueda
Materia: Ingeniería de Software 2
"""

from __future__ import annotations

import re
import tkinter as tk
from tkinter import filedialog, messagebox
from datetime import datetime

from .colors import ACCENT_GREEN, ACCENT_RED

_TAG_HTTP_METHOD = "http_method"
_TAG_HTTP_HEADER_KEY = "http_header_key"
_TAG_JSON_KEY = "json_key"
_TAG_JSON_STRING = "json_string"

_MAX_JSON_HIGHLIGHT_CHARS = 20000


def apply_syntax_highlighting(textbox: tk.Text) -> None:
    """
    Aplica resaltado básico HTTP/JSON en un widget Text/CTkTextbox.

    Resalta:
      - Método HTTP en la request line.
      - Nombre de cabeceras HTTP.
      - Claves y strings JSON en el body (con límite de tamaño).
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


class ProxyEventsMixin:
    """
    Mixin de manejadores de eventos para ProxyTab.

    Agrupa toda la lógica de interacción del usuario para mantener
    proxy_tab.py enfocado exclusivamente en la construcción de la UI.
    """

    # ── Toggle Intercept ──────────────────────────────────────────────────────

    def _toggle_intercept(self) -> None:
        """Activa o desactiva el modo intercept y actualiza el botón."""
        if self.proxy.intercept.intercept_enabled:
            self.proxy.intercept.disable()
            self._intercept_btn.configure(
                text="⬛  Intercept: OFF",
                border_color=ACCENT_GREEN,
                text_color=ACCENT_GREEN,
            )
        else:
            self.proxy.intercept.enable()
            self._intercept_btn.configure(
                text="🔴  Intercept: ON",
                border_color=ACCENT_RED,
                text_color=ACCENT_RED,
            )

    # ── Forward / Drop (CU-04) ────────────────────────────────────────────────

    def _on_forward(self) -> None:
        """
        CU-04: Lee el texto ACTUAL del editor (que el usuario pudo haber
        modificado) y lo reenvía al hilo del handler que está bloqueado
        esperando una decisión via threading.Event.

        Este es el flujo completo de Forward:
            1. El usuario edita el CTkTextbox.
            2. Se lee el texto con get("1.0", "end-1c").
            3. Se codifica a bytes UTF-8.
            4. Se llama pending.forward(bytes) → Event.set() desbloquea
               el hilo del ConnectionHandler.
            5. El handler envía los bytes modificados al servidor real.
        """
        if not self._pending:
            return

        editor_text = self._editor_box.get("1.0", "end-1c")
        if self._pending.should_forward_original(editor_text):
            modified_bytes = self._pending.raw
        else:
            modified_bytes = editor_text.encode("utf-8", errors="replace")
        self._pending.forward(modified_bytes)
        self._pending = None
        self._hide_intercept_buttons()
        self._editor_lbl.configure(text="📋 Petición seleccionada")

    def _on_drop(self) -> None:
        """
        CU-04: Descarta la petición — el navegador recibe un 403 local.
        Llama pending.drop() que desbloquea el hilo del handler con
        decisión 'drop', el cual cierra la conexión sin reenviar.
        """
        if not self._pending:
            return

        self._pending.drop()
        self._pending = None
        self._hide_intercept_buttons()
        self._editor_lbl.configure(text="📋 Petición seleccionada")

    def _show_intercept_buttons(self) -> None:
        """Muestra los botones Forward y Drop (solo cuando hay intercept activo)."""
        self._btn_forward.pack(side="left", padx=(0, 6))
        self._btn_drop.pack(side="left")

    def _hide_intercept_buttons(self) -> None:
        """Oculta los botones Forward y Drop."""
        self._btn_forward.pack_forget()
        self._btn_drop.pack_forget()

    # ── Historial ─────────────────────────────────────────────────────────────

    def _clear_history(self) -> None:
        """Borra el historial en memoria, limpia la tabla y el editor."""
        self.proxy.history.clear()
        for item in self._tree.get_children():
            self._tree.delete(item)
        self._seen_ids.clear()
        self._row_by_id.clear()
        self._set_editor_text("")
        self._count_lbl.configure(text="0 peticiones")
        self._hide_intercept_buttons()
        self._pending = None

    def _export_csv(self) -> None:
        """Exporta el historial completo a CSV mediante diálogo de archivo."""
        if len(self.proxy.history) == 0:
            messagebox.showinfo("Export", "El historial está vacío.", parent=self)
            return

        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=f"historial_{ts}.csv",
        )
        if path:
            self.proxy.history.export_csv(path)
            messagebox.showinfo(
                "Export", f"✅ Exportado a:\n{path}", parent=self,
            )

    # ── Selección de fila ─────────────────────────────────────────────────────

    def _on_row_select(self, _event: tk.Event | None = None) -> None:
        """
        Listener vinculado al evento <<TreeviewSelect>> del Treeview.

        Cuando el usuario hace clic en una fila de la tabla de historial,
        carga el Raw HTTP Request correspondiente en el CTkTextbox del
        editor inferior. Si hay una petición interceptada activa, no
        sobreescribe el editor para no perder el contexto de intercepción.

        Args:
            _event: Evento de Tkinter generado por la selección
                    (se ignora; la selección se lee de la API del widget).
        """
        if self._pending:
            return  # no sobreescribir petición interceptada activa

        selected = self._tree.selection()
        if not selected:
            self._btn_repeater.pack_forget()
            return

        values = self._tree.item(selected[0], "values")
        if not values:
            return

        req_id = int(values[0])
        record = self.proxy.history.get_by_id(req_id)
        if not record or not record.raw_request:
            return

        # Cargar el raw en el editor
        self._set_editor_text(
            record.display_request or record.raw_request.decode("utf-8", errors="replace")
        )
        self._editor_lbl.configure(text=self._format_request_title(
            req_id=req_id,
            method=record.method,
            host=record.host,
            path=record.path,
            prefix="📋",
        ))

        # Mostrar "Send to Repeater" solo si el callback está registrado
        if self._repeater_callback is not None:
            self._btn_repeater.pack(side="left", padx=8, pady=9)

    # ── Send to Repeater (CU-05) ──────────────────────────────────────────────

    def _on_send_to_repeater(self) -> None:
        """
        CU-05: Clona el texto actual del editor y lo envía al Repeater.

        Lee el contenido del CTkTextbox y llama al callback registrado
        (App.switch_to_repeater), que rellena el panel Request del
        Repeater y cambia el foco a esa pestaña automáticamente.
        """
        if self._repeater_callback is None:
            return

        raw_text = self._editor_box.get("1.0", "end-1c")
        if raw_text.strip():
            self._repeater_callback(raw_text)

    # ── Auto-scroll ───────────────────────────────────────────────────────────

    def _is_scrolled_to_bottom(self) -> bool:
        """
        Detecta si el Treeview está desplazado al final de la lista.

        Usa yview() que retorna (top_fraction, bottom_fraction).
        Si bottom_fraction >= 0.99 el usuario ya ve el último elemento.

        Returns:
            True si la vista está al fondo o la lista está vacía.
        """
        try:
            _, bottom = self._tree.yview()
            return bottom >= 0.99
        except tk.TclError:
            return True

    def _on_auto_scroll_toggle(self) -> None:
        """
        Callback del checkbox de auto-scroll.
        No necesita hacer nada extra: _refresh_table() lee
        _auto_scroll_var.get() en cada ciclo de polling.
        """

    # ── Helper compartido ─────────────────────────────────────────────────────

    def _set_editor_text(self, text: str) -> None:
        """
        Reemplaza el contenido del CTkTextbox del editor.

        Args:
            text (str): Texto a insertar. Si es vacío, limpia el widget.
        """
        self._editor_box.delete("1.0", "end")
        if text:
            self._editor_box.insert("1.0", text)
            apply_syntax_highlighting(self._editor_box)
