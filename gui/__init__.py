"""
gui/__init__.py
---------------
Paquete de la interfaz gráfica de Mini-Burp Suite.

Módulos:
    app.py          → App (ventana principal con CTkTabview)
    proxy_tab.py    → ProxyTab (pestaña Proxy: tabla, editor, intercept)
    repeater_tab.py → RepeaterTab (pestaña Repeater: Request/Response + Send)
    colors.py       → PALETTE (colores compartidos del tema dark)
"""

from .app          import App
from .proxy_tab    import ProxyTab
from .repeater_tab import RepeaterTab

__all__ = ["App", "ProxyTab", "RepeaterTab"]
