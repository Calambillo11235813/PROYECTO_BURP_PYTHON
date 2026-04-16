"""
proxy package
-------------
Proxy HTTP interceptor para Ingeniería de Software 2.

Módulos internos:
    server.py  → ProxyServer (socket TCP, bucle de accept)
    handler.py → ConnectionHandler, InterceptController, PendingRequest
    history.py → History, RequestRecord  (CU-03)
    parser.py  → Shim; el parser real está en logic/parser.py
"""

from .server  import ProxyServer
from .handler import ConnectionHandler, InterceptController, PendingRequest
from .history import History, RequestRecord

__all__ = [
    "ProxyServer",
    "ConnectionHandler",
    "InterceptController",
    "PendingRequest",
    "History",
    "RequestRecord",
]
