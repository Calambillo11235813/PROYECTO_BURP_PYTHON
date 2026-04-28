"""core/paths.py
----------------
Helpers de rutas para ejecución desde código fuente y desde binario PyInstaller.

Convenciones:
- Datos persistentes de usuario: ~/.netlens/ (Windows/Linux/macOS)
- Recursos empaquetados (onefile): sys._MEIPASS
"""

from __future__ import annotations

import sys
from pathlib import Path


_APP_DIRNAME = ".netlens"


def is_frozen() -> bool:
    """True si está corriendo como binario de PyInstaller."""
    return bool(getattr(sys, "frozen", False))


def user_data_dir() -> Path:
    """Directorio persistente por usuario (config, certs, etc.)."""
    return Path.home() / _APP_DIRNAME


def project_root() -> Path:
    """Raíz del proyecto cuando se ejecuta desde código fuente."""
    return Path(__file__).resolve().parent.parent


def resource_base_dir() -> Path:
    """Base para recursos incluidos como --add-data.

    En PyInstaller onefile, los datos se extraen a sys._MEIPASS.
    En desarrollo, usamos la raíz del proyecto.
    """
    if is_frozen() and hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS"))
    return project_root()


def resource_path(*parts: str) -> Path:
    """Devuelve la ruta absoluta a un recurso empaquetado o del repo."""
    return resource_base_dir().joinpath(*parts)
