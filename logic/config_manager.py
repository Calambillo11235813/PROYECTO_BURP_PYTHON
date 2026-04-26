"""
logic/config_manager.py
------------------------
Gestor de configuracion persistente de NetLens.

Guarda y lee un archivo JSON en el directorio de perfil del usuario:
    Windows : C:\\Users\\<user>\\.netlens\\config.json
    Linux / macOS : ~/.netlens/config.json

Patron Singleton: una sola instancia compartida por toda la aplicacion.
Esto garantiza que todos los modulos lean y escriban el mismo estado.

Autores: Diogo Nicolas Rodriguez Gomez, Javier Soliz Rueda
Materia: Ingenieria de Software 2
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


# ── Ruta del archivo de configuracion ─────────────────────────────────────────

_CONFIG_DIR  = Path.home() / ".netlens"
_CONFIG_FILE = _CONFIG_DIR / "config.json"

# Clave que se almacena en el JSON
_KEY_API_KEY = "gemini_api_key"


# ── Clase principal ────────────────────────────────────────────────────────────

class ConfigManager:
    """
    Gestor de configuracion persistente (Singleton).

    Lee y escribe ``~/.netlens/config.json``.  La primera vez que se llama
    a ``instance()`` crea el directorio y el archivo si no existen.

    Usage::

        cfg = ConfigManager.instance()
        key = cfg.get_api_key()
        cfg.save_api_key("AIza...")
    """

    _instance: ConfigManager | None = None

    # ── Singleton ──────────────────────────────────────────────────────────────

    def __new__(cls) -> "ConfigManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._data: dict[str, Any] = {}
            cls._instance._loaded = False
        return cls._instance

    @classmethod
    def instance(cls) -> "ConfigManager":
        """Devuelve la instancia unica de ConfigManager."""
        return cls()

    # ── Ciclo de vida ──────────────────────────────────────────────────────────

    def _ensure_loaded(self) -> None:
        """Carga el JSON del disco si todavia no se ha hecho en esta sesion."""
        if self._loaded:
            return
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if _CONFIG_FILE.exists():
            try:
                with _CONFIG_FILE.open(encoding="utf-8") as fh:
                    self._data = json.load(fh)
            except (json.JSONDecodeError, OSError):
                self._data = {}
        else:
            self._data = {}
        self._loaded = True

    def _save(self) -> None:
        """Persiste el estado actual de ``_data`` en disco."""
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with _CONFIG_FILE.open("w", encoding="utf-8") as fh:
            json.dump(self._data, fh, indent=2)

    # ── API publica ────────────────────────────────────────────────────────────

    def get_api_key(self) -> str:
        """
        Devuelve la API Key de Gemini almacenada.

        Returns:
            La clave como string, o cadena vacia si no esta configurada.
        """
        self._ensure_loaded()
        return str(self._data.get(_KEY_API_KEY, "")).strip()

    def save_api_key(self, key: str) -> None:
        """
        Guarda la API Key de Gemini en el archivo de configuracion.

        Args:
            key: Clave de la API de Google Gemini (puede estar vacia
                 para borrarla).
        """
        self._ensure_loaded()
        self._data[_KEY_API_KEY] = key.strip()
        self._save()

    def get(self, key: str, default: Any = None) -> Any:
        """
        Devuelve el valor de una clave generica del JSON.

        Args:
            key:     Nombre de la clave.
            default: Valor si la clave no existe.

        Returns:
            El valor almacenado o ``default``.
        """
        self._ensure_loaded()
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """
        Guarda un valor generico en el JSON de configuracion.

        Args:
            key:   Nombre de la clave.
            value: Valor a almacenar (debe ser serializable por json).
        """
        self._ensure_loaded()
        self._data[key] = value
        self._save()

    @property
    def config_path(self) -> str:
        """Ruta absoluta del archivo config.json (util para mostrar en la UI)."""
        return str(_CONFIG_FILE)
