"""
gui/colors.py
-------------
Paleta de colores centralizada para toda la GUI de Mini-Burp Suite.

Inspirada en el tema oscuro de GitHub (github-dark) para una apariencia
profesional y coherente en todos los componentes.
"""

# ── Paleta principal ───────────────────────────────────────────────────────────
BG_DARK       = "#0d1117"   # fondo principal (muy oscuro)
BG_SECONDARY  = "#161b22"   # fondo de paneles y tarjetas
BG_ROW_ODD    = "#1c2128"   # filas alternas de la tabla
BG_HOVER      = "#2d333b"   # hover de botones secundarios

ACCENT_BLUE   = "#1f6feb"   # acción principal / selección
ACCENT_GREEN  = "#3fb950"   # éxito / intercept OFF
ACCENT_RED    = "#f85149"   # peligro / intercept ON
ACCENT_YELLOW = "#e3b341"   # advertencia / timeout

TEXT_PRIMARY  = "#e6edf3"   # texto principal
TEXT_MUTED    = "#8b949e"   # texto secundario / etiquetas
BORDER        = "#30363d"   # bordes y separadores

# ── Diccionario accesible por clave ───────────────────────────────────────────
PALETTE: dict[str, str] = {
    "bg_dark"       : BG_DARK,
    "bg_secondary"  : BG_SECONDARY,
    "bg_row_odd"    : BG_ROW_ODD,
    "bg_hover"      : BG_HOVER,
    "accent_blue"   : ACCENT_BLUE,
    "accent_green"  : ACCENT_GREEN,
    "accent_red"    : ACCENT_RED,
    "accent_yellow" : ACCENT_YELLOW,
    "text_primary"  : TEXT_PRIMARY,
    "text_muted"    : TEXT_MUTED,
    "border"        : BORDER,
}
