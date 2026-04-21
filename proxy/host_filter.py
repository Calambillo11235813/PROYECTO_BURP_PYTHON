"""
proxy/host_filter.py
--------------------
Filtro de dominios para reducir ruido en la vista del proxy.

Modos soportados:
    - whitelist: solo se muestran hosts que hagan match con la lista.
    - blacklist: se ocultan hosts que hagan match con la lista.

El filtro es thread-safe para uso concurrente desde múltiples hilos del proxy.
"""

from __future__ import annotations

import fnmatch
import threading

FILTER_MODE_WHITELIST = "whitelist"
FILTER_MODE_BLACKLIST = "blacklist"

FILTER_DECISION_SHOW = "show"
FILTER_DECISION_BYPASS = "bypass"
FILTER_DECISION_DROP = "drop"


class HostFilter:
    """Mantiene reglas de filtrado por host con soporte de comodines."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._mode = FILTER_MODE_BLACKLIST
        self._patterns: list[str] = []
        # En blacklist: bypass = reenviar silenciosamente, drop = bloquear.
        self._blacklist_action = FILTER_DECISION_BYPASS

    @property
    def mode(self) -> str:
        with self._lock:
            return self._mode

    def set_mode(self, mode: str) -> None:
        mode = (mode or "").strip().lower()
        if mode not in (FILTER_MODE_WHITELIST, FILTER_MODE_BLACKLIST):
            return
        with self._lock:
            self._mode = mode

    def set_blacklist_action(self, action: str) -> None:
        action = (action or "").strip().lower()
        if action not in (FILTER_DECISION_BYPASS, FILTER_DECISION_DROP):
            return
        with self._lock:
            self._blacklist_action = action

    def add_pattern(self, pattern: str) -> bool:
        normalized = self._normalize_pattern(pattern)
        if not normalized:
            return False
        with self._lock:
            if normalized in self._patterns:
                return False
            self._patterns.append(normalized)
            return True

    def remove_pattern(self, pattern: str) -> bool:
        normalized = self._normalize_pattern(pattern)
        if not normalized:
            return False
        with self._lock:
            try:
                self._patterns.remove(normalized)
                return True
            except ValueError:
                return False

    def clear_patterns(self) -> None:
        with self._lock:
            self._patterns.clear()

    def get_patterns(self) -> list[str]:
        with self._lock:
            return list(self._patterns)

    def decide(self, host: str, port: int) -> str:
        """
        Retorna una decisión para el request:
            show   -> mostrar en UI/historial e interceptar si aplica.
            bypass -> reenviar silenciosamente sin mostrar.
            drop   -> bloquear silenciosamente.
        """
        with self._lock:
            patterns = list(self._patterns)
            mode = self._mode
            blacklist_action = self._blacklist_action

        if not patterns:
            return FILTER_DECISION_SHOW

        matched = self._matches(host=host, port=port, patterns=patterns)

        if mode == FILTER_MODE_WHITELIST:
            return FILTER_DECISION_SHOW if matched else FILTER_DECISION_BYPASS

        # blacklist
        if not matched:
            return FILTER_DECISION_SHOW
        return blacklist_action

    def _matches(self, host: str, port: int, patterns: list[str]) -> bool:
        host_lower = (host or "").strip().lower()
        host_with_port = f"{host_lower}:{port}"

        for pattern in patterns:
            if ":" in pattern:
                if fnmatch.fnmatchcase(host_with_port, pattern):
                    return True
                continue
            if fnmatch.fnmatchcase(host_lower, pattern):
                return True
        return False

    @staticmethod
    def _normalize_pattern(pattern: str) -> str:
        return (pattern or "").strip().lower()
