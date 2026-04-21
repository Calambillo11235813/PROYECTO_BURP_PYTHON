"""
core/__init__.py
----------------
Paquete 'core': componentes de infraestructura transversal.

Módulos:
    certs_manager.py → CertsManager: CA root + generación de certs por dominio.
"""

from .certs_manager import CertsManager

__all__ = ["CertsManager"]
