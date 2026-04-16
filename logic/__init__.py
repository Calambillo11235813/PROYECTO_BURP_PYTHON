"""
logic package
-------------
Capa de procesamiento y manipulación de datos del proyecto Mini-Burp Suite.

Módulos:
    parser  → Extrae campos de peticiones HTTP crudas (bytes → ParsedRequest)
"""
from .parser import ParsedRequest, parse_request

__all__ = ["ParsedRequest", "parse_request"]
