"""
logic/intruder_engine.py
------------------------
Motor de permutación de payloads para el Módulo C: Intruder (CU-08 a CU-10).

Responsabilidades (y SOLO estas):
    - Parsear los marcadores § en una plantilla de petición HTTP.
    - Generar, mediante funciones ``yield``, las peticiones modificadas
      según el tipo de ataque solicitado.
    - NO realiza peticiones de red ni toca la GUI.

Marcador de inyección: §nombre§
    El texto encerrado entre dos § identifica un punto de inyección.
    Ejemplo:
        GET /search?q=§FUZZ§ HTTP/1.1
        Host: §HOST§

Tipos de ataque implementados
──────────────────────────────
    Sniper        → 1 lista,  un marcador a la vez.
    Battering Ram → 1 lista,  todos los marcadores simultáneamente.
    Pitchfork     → N listas, iteración paralela (zip).
    Cluster Bomb  → N listas, producto cartesiano (itertools.product).

Autores: Diogo Nicolas Rodriguez Gomez, Javier Soliz Rueda
Materia: Ingeniería de Software 2
"""

from __future__ import annotations

import itertools
import re
from typing import Generator, Sequence

# ── Tipo público ───────────────────────────────────────────────────────────────

#: Un generador que produce pares (índice_global, petición_modificada).
RequestGen = Generator[tuple[int, str], None, None]

# ── Constantes internas ────────────────────────────────────────────────────────

#: Expresión regular que captura cualquier bloque §…§.
_MARKER_RE = re.compile(r"§[^§]*§")

# Nombres de tipo de ataque aceptados (sin distinción de mayúsculas).
_VALID_ATTACK_TYPES = frozenset(
    {"sniper", "battering ram", "pitchfork", "cluster bomb"}
)


# ── Helpers privados ───────────────────────────────────────────────────────────

def _find_markers(template: str) -> list[str]:
    """
    Devuelve la lista ordenada de marcadores §…§ encontrados en la plantilla.

    Args:
        template: Petición HTTP con marcadores § embebidos.

    Returns:
        Lista de strings con los marcadores tal como aparecen en el texto,
        incluyendo los caracteres §.  Puede contener duplicados si el mismo
        marcador aparece varias veces.

    Example:
        >>> _find_markers("GET /q=§FUZZ§ HTTP/1.1\\nHost: §HOST§")
        ['§FUZZ§', '§HOST§']
    """
    return _MARKER_RE.findall(template)


def _replace_marker_at(
    template: str,
    markers: list[str],
    target_index: int,
    payload: str,
    placeholder: str = "",
) -> str:
    """
    Reemplaza la ocurrencia número *target_index* del marcador correspondiente
    por *payload*, y el resto de marcadores por *placeholder*.

    Se usa en **Sniper**, donde solo un marcador recibe el payload mientras
    los demás se limpian.

    Args:
        template:      Plantilla original.
        markers:       Lista de marcadores tal como los devuelve _find_markers().
        target_index:  Índice (0-based) del marcador que recibirá el payload.
        payload:       Valor a insertar en el marcador objetivo.
        placeholder:   Valor a usar en los demás marcadores (default: cadena vacía).

    Returns:
        Petición HTTP con las sustituciones aplicadas.
    """
    result = template
    # Iteramos en orden inverso para que los índices de cadena no se desplacen.
    occurrence_positions: list[tuple[int, int, str]] = []

    pos = 0
    for marker in markers:
        idx = result.find(marker, pos)
        if idx == -1:
            # El marcador ya fue consumido en una sustitución anterior.
            continue
        occurrence_positions.append((idx, idx + len(marker), marker))
        pos = idx + len(marker)

    # Reemplazar de derecha a izquierda para preservar índices.
    for i, (start, end, _) in enumerate(reversed(occurrence_positions)):
        real_index = len(occurrence_positions) - 1 - i
        value = payload if real_index == target_index else placeholder
        result = result[:start] + value + result[end:]

    return result


def _replace_all_markers(template: str, payload: str) -> str:
    """
    Sustituye **todos** los marcadores § simultáneamente por el mismo *payload*.

    Se usa en **Battering Ram**.

    Args:
        template: Plantilla original con marcadores.
        payload:  Valor único a insertar en todas las posiciones.

    Returns:
        Petición HTTP con todos los marcadores reemplazados.

    Mathematical note:
        Si hay *m* marcadores y *n* payloads, el total de peticiones
        generadas es simplemente *n* (complejidad lineal O(n)).
    """
    return _MARKER_RE.sub(payload, template)


def _replace_markers_by_index(
    template: str,
    markers: list[str],
    payloads: Sequence[str],
) -> str:
    """
    Sustituye cada marcador por el payload en la misma posición de *payloads*.

    Se usa en **Pitchfork** y **Cluster Bomb**.

    Args:
        template: Plantilla original.
        markers:  Lista de marcadores tal como los devuelve _find_markers().
        payloads: Secuencia de valores, uno por marcador (len debe coincidir).

    Returns:
        Petición HTTP con cada marcador i reemplazado por payloads[i].

    Raises:
        ValueError: Si len(payloads) != len(markers).
    """
    if len(payloads) != len(markers):
        raise ValueError(
            f"Se esperaban {len(markers)} payloads pero se recibieron "
            f"{len(payloads)}."
        )
    result = template
    # Reemplazar de derecha a izquierda para no desplazar índices.
    pos = 0
    positions: list[tuple[int, int]] = []

    for marker in markers:
        idx = result.find(marker, pos)
        if idx == -1:
            continue
        positions.append((idx, idx + len(marker)))
        pos = idx + len(marker)

    for i, (start, end) in enumerate(reversed(positions)):
        real_i = len(positions) - 1 - i
        result = result[:start] + payloads[real_i] + result[end:]

    return result


# ── Clase principal ────────────────────────────────────────────────────────────

class IntruderEngine:
    """
    Motor puro de generación de peticiones para el Intruder.

    No realiza I/O de red ni interacciones con la GUI.  Su única
    responsabilidad es recibir una plantilla y diccionarios de payloads
    y **generar** (``yield``) cada petición modificada.

    Usage::

        engine = IntruderEngine()

        payloads = {"0": ["admin", "root", "guest"]}
        template = "GET /login?user=§FUZZ§ HTTP/1.1\\nHost: example.com"

        for idx, request in engine.generate_requests(
            template, payloads, attack_type="sniper"
        ):
            print(idx, request[:40])
    """

    # ── API pública ────────────────────────────────────────────────────────────

    @staticmethod
    def get_marker_count(template: str) -> int:
        """
        Devuelve la cantidad de marcadores § encontrados en la plantilla.

        Args:
            template: Texto de la petición HTTP.

        Returns:
            Número entero ≥ 0 de marcadores detectados.
        """
        return len(_find_markers(template))

    @staticmethod
    def validate_template(template: str) -> bool:
        """
        Verifica que la plantilla contenga al menos un marcador §…§.

        Args:
            template: Texto de la petición HTTP.

        Returns:
            ``True`` si hay al menos un marcador, ``False`` en caso contrario.
        """
        return bool(_MARKER_RE.search(template))

    def generate_requests(
        self,
        template: str,
        payloads_dict: dict[str, list[str]],
        attack_type: str = "sniper",
    ) -> RequestGen:
        """
        Generador principal.  Delega en el método específico según *attack_type*.

        Args:
            template:
                Petición HTTP base con marcadores §…§ embebidos.
            payloads_dict:
                Diccionario cuyas claves son identificadores de set
                (``"0"``, ``"1"``…) y cuyos valores son las listas de payloads.
                - Sniper y Battering Ram usan solo la clave ``"0"``.
                - Pitchfork y Cluster Bomb usan ``"0"``, ``"1"``, ``"2"``…
                  (uno por marcador).
            attack_type:
                Uno de ``"sniper"``, ``"battering ram"``,
                ``"pitchfork"`` o ``"cluster bomb"``
                (sin distinción de mayúsculas).

        Yields:
            Tuplas ``(global_index, modified_request)`` donde *global_index*
            empieza en 1 e incrementa con cada petición generada.

        Raises:
            ValueError:
                Si *attack_type* no es uno de los valores admitidos.
            ValueError:
                Si *template* no contiene ningún marcador §.
            ValueError:
                Si *payloads_dict* está vacío o la clave ``"0"`` falta para
                los modos que la requieren.
        """
        normalized = attack_type.strip().lower()
        if normalized not in _VALID_ATTACK_TYPES:
            raise ValueError(
                f"Tipo de ataque no válido: '{attack_type}'. "
                f"Valores permitidos: {sorted(_VALID_ATTACK_TYPES)}"
            )

        if not self.validate_template(template):
            raise ValueError(
                "La plantilla no contiene ningún marcador §. "
                "Añade al menos uno con la forma §NOMBRE§."
            )

        dispatch = {
            "sniper":        self._sniper,
            "battering ram": self._battering_ram,
            "pitchfork":     self._pitchfork,
            "cluster bomb":  self._cluster_bomb,
        }
        yield from dispatch[normalized](template, payloads_dict)

    # ── Algoritmos de ataque ───────────────────────────────────────────────────

    @staticmethod
    def _sniper(
        template: str,
        payloads_dict: dict[str, list[str]],
    ) -> RequestGen:
        """
        **Sniper** — Un marcador atacado a la vez, el resto se limpia.

        Algoritmo:
            Sea M = {m₀, m₁, …, m_{k-1}} el conjunto de marcadores y
            P = {p₀, p₁, …, p_{n-1}} la lista de payloads.

            Para cada mᵢ ∈ M:
                Para cada pⱼ ∈ P:
                    Sustituir mᵢ → pⱼ, y mₓ → "" para x ≠ i.
                    yield (índice_global, petición_resultante)

            Total de peticiones = k × n   (marcadores × payloads).

        Args:
            template:      Plantilla con marcadores.
            payloads_dict: Requiere la clave ``"0"`` con la lista de payloads.

        Yields:
            ``(idx, request)`` para cada combinación (marcador, payload).
        """
        payloads = payloads_dict.get("0", [])
        if not payloads:
            return

        markers = _find_markers(template)
        idx = 1

        for marker_index in range(len(markers)):
            for payload in payloads:
                request = _replace_marker_at(
                    template, markers, marker_index, payload
                )
                yield idx, request
                idx += 1

    @staticmethod
    def _battering_ram(
        template: str,
        payloads_dict: dict[str, list[str]],
    ) -> RequestGen:
        """
        **Battering Ram** — El mismo payload se inserta en todos los marcadores.

        Algoritmo:
            Sea M = {m₀, …, m_{k-1}} los marcadores y P la lista de payloads.

            Para cada pⱼ ∈ P:
                Sustituir todos mᵢ → pⱼ  (∀ i ∈ [0, k-1]).
                yield (j+1, petición_resultante)

            Total de peticiones = n   (solo depende del número de payloads).

        Args:
            template:      Plantilla con marcadores.
            payloads_dict: Requiere la clave ``"0"`` con la lista de payloads.

        Yields:
            ``(idx, request)`` con el mismo payload en todos los marcadores.
        """
        payloads = payloads_dict.get("0", [])
        if not payloads:
            return

        for idx, payload in enumerate(payloads, start=1):
            yield idx, _replace_all_markers(template, payload)

    @staticmethod
    def _pitchfork(
        template: str,
        payloads_dict: dict[str, list[str]],
    ) -> RequestGen:
        """
        **Pitchfork** — Iteración paralela (zip) entre N listas de payloads.

        Algoritmo:
            Sea M = {m₀, …, m_{k-1}} los marcadores y
            Lᵢ la lista de payloads para el marcador mᵢ.

            Para j en range(min(|L₀|, |L₁|, …, |L_{k-1}|)):
                Sustituir mᵢ → Lᵢ[j]  para todo i.
                yield (j+1, petición_resultante)

            Total de peticiones = min(|L₀|, |L₁|, …)   (la lista más corta
            determina el fin del ataque — comportamiento de ``zip``).

        Args:
            template:
                Plantilla con exactamente k marcadores.
            payloads_dict:
                Claves ``"0"``, ``"1"``, …, ``"k-1"`` con una lista cada una.
                Si hay más claves que marcadores, las extras se ignoran.
                Si hay menos claves que marcadores, los marcadores sobrantes
                reciben cadena vacía.

        Yields:
            ``(idx, request)`` con cada marcador i usando su j-ésimo payload.
        """
        markers = _find_markers(template)
        k = len(markers)

        # Construir las listas en orden de marcador.
        lists = [
            payloads_dict.get(str(i), [])
            for i in range(k)
        ]

        for idx, combo in enumerate(zip(*lists), start=1):
            request = _replace_markers_by_index(template, markers, list(combo))
            yield idx, request

    @staticmethod
    def _cluster_bomb(
        template: str,
        payloads_dict: dict[str, list[str]],
    ) -> RequestGen:
        """
        **Cluster Bomb** — Producto cartesiano de N listas de payloads.

        Algoritmo:
            Sea M = {m₀, …, m_{k-1}} los marcadores y
            Lᵢ la lista de payloads para mᵢ.

            Para cada (p₀, p₁, …, p_{k-1}) ∈ L₀ × L₁ × … × L_{k-1}:
                Sustituir mᵢ → pᵢ  para todo i.
                yield (idx, petición_resultante)

            Total de peticiones = |L₀| × |L₁| × … × |L_{k-1}|
            (crece exponencialmente — usar con cautela).

        Args:
            template:
                Plantilla con exactamente k marcadores.
            payloads_dict:
                Claves ``"0"``, ``"1"``, …, ``"k-1"`` con una lista cada una.

        Yields:
            ``(idx, request)`` para cada combinación del producto cartesiano.

        Warning:
            El producto cartesiano de listas grandes puede generar millones
            de peticiones.  El generador es lazy (``yield``) para no consumir
            memoria, pero el tiempo de ejecución puede ser muy largo.
        """
        markers = _find_markers(template)
        k = len(markers)

        lists = [
            payloads_dict.get(str(i), [""])
            for i in range(k)
        ]

        for idx, combo in enumerate(itertools.product(*lists), start=1):
            request = _replace_markers_by_index(template, markers, list(combo))
            yield idx, request
