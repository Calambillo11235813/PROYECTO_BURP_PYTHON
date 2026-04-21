"""
gui/__init__.py
---------------
Paquete de la interfaz gráfica de Mini-Burp Suite.

Módulos:
    app.py           → App (ventana principal con CTkTabview)
    proxy_tab.py     → ProxyTab (construcción UI de la pestaña Proxy)
    proxy_events.py  → ProxyEventsMixin (event handlers: select, forward, drop…)
    repeater_tab.py  → RepeaterTab (pestaña Repeater: Request/Response + Send)
    colors.py        → PALETTE (tokens de color del tema dark)
"""

from .app           import App
from .proxy_tab     import ProxyTab
from .proxy_events  import ProxyEventsMixin
from .repeater_tab  import RepeaterTab

__all__ = ["App", "ProxyTab", "ProxyEventsMixin", "RepeaterTab"]
