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
    _editor_box      (tk.Text)              : panel Request (izquierdo).
    _response_box    (tk.Text)              : panel Response (derecho).
    _editor_lbl      (tk.Label)             : etiqueta del panel Request.
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
from .utils import apply_syntax_highlighting


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
                text="⬛  Interceptar: OFF",
                border_color=ACCENT_GREEN,
                text_color=ACCENT_GREEN,
            )
            # CU-04: Si apagamos el interceptor, liberamos la petición actual
            if getattr(self, "_pending", None):
                self._pending.forward()
                self._pending = None
                self._hide_intercept_buttons()
                self._editor_lbl.configure(text="📋 Petición seleccionada")
                self._set_editor_text("")
                self._set_response_text("")
        else:
            self.proxy.intercept.enable()
            self._intercept_btn.configure(
                text="🔴  Interceptar: ON",
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
            modified_bytes = self._recalculate_content_length(editor_text)
            
        self._pending.forward(modified_bytes)
        self._pending = None
        self._hide_intercept_buttons()
        self._editor_lbl.configure(text="📋 Petición seleccionada")
        self._set_editor_text("")
        self._set_response_text("")

    def _recalculate_content_length(self, request_text: str) -> bytes:
        """
        Recalcula dinámicamente el valor de la cabecera Content-Length basándose
        en el tamaño real (en bytes) del body modificado en el editor, asegurando
        que el servidor objetivo reciba exactamente la cantidad de datos que
        espera y no se quede bloqueado.
        """
        if "\n\n" in request_text and "\r\n\r\n" not in request_text:
            request_text = request_text.replace("\n", "\r\n")

        parts = request_text.split("\r\n\r\n", 1)
        headers_str = parts[0]
        body_str = parts[1] if len(parts) > 1 else ""

        # Si hay Transfer-Encoding: chunked, el proxy/servidor asume formato
        # dinámico, por lo que NO debemos tocar/inyectar un Content-Length estático.
        if "transfer-encoding: chunked" in headers_str.lower():
            return request_text.encode("utf-8", errors="replace")

        # Si hay body (indistintamente del método), calcular bytes y actualizar cabecera
        if body_str:
            body_bytes = body_str.encode("utf-8", errors="replace")
            new_length = len(body_bytes)

            # Buscar y reemplazar el Content-Length independientemente de mayúsculas
            lines = headers_str.split("\r\n")
            replaced = False
            for i, line in enumerate(lines):
                if line.lower().startswith("content-length:"):
                    lines[i] = f"Content-Length: {new_length}"
                    replaced = True
                    break

            if not replaced:
                # Si no existía, la añadimos al final de las cabeceras
                lines.append(f"Content-Length: {new_length}")

            headers_str = "\r\n".join(lines)
            final_text = headers_str + "\r\n\r\n" + body_str
            return final_text.encode("utf-8", errors="replace")

        return request_text.encode("utf-8", errors="replace")

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
        self._set_response_text("")
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
            self._actions_menu.pack_forget()
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
            record.display_request or record.raw_request.decode("utf-8", errors="replace"),
            editable=False,
        )
        self._set_response_text(
            record.display_response or record.response_raw.decode("utf-8", errors="replace"),
        )
        self._editor_lbl.configure(text=self._format_request_title(
            req_id=req_id,
            method=record.method,
            host=record.host,
            path=record.path,
            prefix="📋",
        ))

        # Mostrar menú “Acciones” si al menos un callback está registrado
        if self._repeater_callback is not None or self._intruder_callback is not None:
            self._actions_var.set("⚡  Acciones")
            self._actions_menu.pack(side="left", padx=8, pady=9)

    # ── Menú Acciones (CU-05 + Intruder) ─────────────────────────────────────

    def _on_action_selected(self, choice: str) -> None:
        """
        Dispatcher del menú Acciones.

        Clona el texto del editor y lo envía al módulo correspondiente
        (Repeater o Intruder) según la opción elegida, cambiando el
        foco de pestaña automáticamente.
        """
        raw_text = self._editor_box.get("1.0", "end-1c").strip()
        if not raw_text:
            return

        if "Repeater" in choice and self._repeater_callback is not None:
            self._repeater_callback(raw_text)
        elif "Intruder" in choice and self._intruder_callback is not None:
            self._intruder_callback(raw_text)

        # Reiniciar el menú al título neutral tras la acción
        self._actions_var.set("⚡  Acciones")

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

    def _set_editor_text(self, text: str, editable: bool = False) -> None:
        """
        Reemplaza el contenido del panel Request.

        Args:
            text (str): Texto a insertar. Si es vacío, limpia el widget.
            editable (bool): Si True, deja el panel editable para intercept.
        """
        self._editor_box.configure(state="normal")
        self._editor_box.delete("1.0", "end")
        if text:
            self._editor_box.insert("1.0", text)
            apply_syntax_highlighting(self._editor_box)
        if not editable:
            self._editor_box.configure(state="disabled")

    def _set_response_text(self, text: str) -> None:
        """Reemplaza el contenido del panel Response (siempre solo lectura)."""
        self._response_box.configure(state="normal")
        self._response_box.delete("1.0", "end")
        if text:
            self._response_box.insert("1.0", text)
            apply_syntax_highlighting(self._response_box)
        self._response_box.configure(state="disabled")
