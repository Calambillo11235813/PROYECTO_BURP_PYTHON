"""
gui/__init__.py
---------------
Paquete de la interfaz gráfica de Mini-Burp Suite.

Módulos:
    app.py       → App (ventana principal con CTkTabview)
    proxy_tab.py → ProxyTab (pestaña Proxy con tabla, editor e intercept)
    colors.py    → PALETTE (colores compartidos del tema dark)
"""

from .app       import App
from .proxy_tab import ProxyTab

__all__ = ["App", "ProxyTab"]
