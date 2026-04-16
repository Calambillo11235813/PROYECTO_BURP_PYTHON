"""
proxy/proxy_server.py
---------------------
Shim de compatibilidad hacia atrás.

Importa ProxyServer desde server.py para que el código existente que haga:
    from proxy.proxy_server import ProxyServer
siga funcionando sin cambios tras la refactorización.
"""

from .server import ProxyServer  # noqa: F401

__all__ = ["ProxyServer"]
