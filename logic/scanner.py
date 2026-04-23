"""
logic/scanner.py
----------------
Módulo D: Reporting & Analysis (CU-11: Detección Pasiva)

Implementa el análisis pasivo del historial de peticiones para detectar
configuraciones inseguras, fugas de información y errores del servidor
sin realizar nuevas peticiones a la red.

Autores: Diogo Nicolas Rodriguez Gomez, Javier Soliz Rueda
Materia: Ingeniería de Software 2
"""

import re
from dataclasses import dataclass
from proxy.history import RequestRecord


@dataclass
class PassiveFinding:
    """
    Representa una vulnerabilidad o configuración insegura encontrada
    pasivamente en una petición del historial.

    Args:
        request_id  (int): ID de la petición analizada.
        severity    (str): Nivel de riesgo (High, Medium, Low, Info).
        title       (str): Nombre corto del hallazgo.
        description (str): Detalles del problema y su implicación.
    """
    request_id: int
    severity: str
    title: str
    description: str


class PassiveScanner:
    """
    Analizador pasivo de tráfico HTTP.

    Su responsabilidad es recorrer un conjunto de objetos RequestRecord e
    identificar vulnerabilidades comparando cabeceras y códigos de estado
    contra reglas predefinidas.
    """

    def __init__(self) -> None:
        """
        Inicializa el escáner y define las reglas base.
        """
        # Cabeceras de seguridad requeridas y su título de hallazgo.
        self._required_headers: dict[str, str] = {
            "strict-transport-security": "Falta Strict-Transport-Security (HSTS)",
            "x-frame-options": "Falta X-Frame-Options (Clickjacking)",
            "x-content-type-options": "Falta X-Content-Type-Options (nosniff)",
            "content-security-policy": "Falta Content-Security-Policy (CSP)",
        }

        # Patrón para detectar versiones (ej. Apache/2.4.41, PHP/7.4)
        self._version_pattern = re.compile(r"(/|\s)\d+\.\d+")

        # Patrones para buscar vulnerabilidades en el cuerpo de la respuesta
        self._critical_patterns: list[tuple[re.Pattern, str]] = [
            (re.compile(r"-----BEGIN (RSA )?PRIVATE KEY-----"), "Fuga Crítica: Llave Privada Expuesta"),
        ]

        self._high_patterns: list[tuple[re.Pattern, str]] = [
            (re.compile(r"SQL syntax.*MySQL|mysql_fetch_array|ORA-\d{4,5}|PostgreSQL query failed", re.IGNORECASE), "Fuga de Información: Error de Base de Datos"),
        ]

    def scan_history(self, history_records: list[RequestRecord]) -> list[PassiveFinding]:
        """
        Analiza iterativamente una lista de registros del historial en busca de hallazgos.

        Args:
            history_records (list[RequestRecord]): Lista de peticiones capturadas.

        Retorna:
            list[PassiveFinding]: Lista de todos los hallazgos encontrados.
        """
        findings: list[PassiveFinding] = []

        for record in history_records:
            # Ignorar peticiones sin respuesta válida (ej. túneles CONNECT o errores)
            if not record.response_status or record.status_code == 0:
                continue

            findings.extend(self._check_missing_security_headers(record))
            findings.extend(self._check_information_leakage(record))
            findings.extend(self._check_server_errors(record))
            findings.extend(self._check_body_leaks(record))

        return findings

    def _check_missing_security_headers(self, record: RequestRecord) -> list[PassiveFinding]:
        """
        Verifica la ausencia de cabeceras de seguridad estándar en la respuesta.

        Args:
            record (RequestRecord): El registro a analizar.

        Retorna:
            list[PassiveFinding]: Hallazgos por falta de cabeceras.
        """
        findings: list[PassiveFinding] = []

        try:
            # Normalizar a minúsculas para una comparación case-insensitive segura
            headers_lower = {k.lower(): v for k, v in record.response_headers.items()}
        except (AttributeError, TypeError):
            return findings

        for header_key, title in self._required_headers.items():
            if header_key not in headers_lower:
                desc = (
                    f"La cabecera de seguridad '{header_key}' no está presente "
                    f"en la respuesta. Esto puede exponer a la aplicación a ataques "
                    f"del lado del cliente."
                )
                findings.append(
                    PassiveFinding(
                        request_id=record.id,
                        severity="Low",
                        title=title,
                        description=desc,
                    )
                )

        return findings

    def _check_information_leakage(self, record: RequestRecord) -> list[PassiveFinding]:
        """
        Busca patrones de fuga de información (versiones) en cabeceras como Server.

        Args:
            record (RequestRecord): El registro a analizar.

        Retorna:
            list[PassiveFinding]: Hallazgos por fugas de información.
        """
        findings: list[PassiveFinding] = []
        target_headers = ["server", "x-powered-by"]

        try:
            headers_lower = {k.lower(): v for k, v in record.response_headers.items()}
        except (AttributeError, TypeError):
            return findings

        for header in target_headers:
            if header in headers_lower:
                value = str(headers_lower[header])
                if self._version_pattern.search(value):
                    desc = (
                        f"La cabecera '{header}' revela la tecnología exacta "
                        f"o su versión: '{value}'. Esto facilita el reconocimiento "
                        f"para potenciales atacantes."
                    )
                    findings.append(
                        PassiveFinding(
                            request_id=record.id,
                            severity="Medium",
                            title=f"Fuga de Información en {header.title()}",
                            description=desc,
                        )
                    )

        return findings

    def _check_server_errors(self, record: RequestRecord) -> list[PassiveFinding]:
        """
        Detecta si el servidor devolvió un error de la serie 500.

        Args:
            record (RequestRecord): El registro a analizar.

        Retorna:
            list[PassiveFinding]: Hallazgo de error si corresponde.
        """
        findings: list[PassiveFinding] = []

        if record.status_code >= 500:
            desc = (
                f"El servidor devolvió un código de estado {record.status_code}. "
                f"Los errores 500 pueden ser indicadores de inyecciones (ej. SQLi "
                f"ciego) o fallos de lógica no manejados."
            )
            findings.append(
                PassiveFinding(
                    request_id=record.id,
                    severity="Info",
                    title="Error del Servidor (Serie 500)",
                    description=desc,
                )
            )

        return findings

    def _check_body_leaks(self, record: RequestRecord) -> list[PassiveFinding]:
        """
        Busca patrones sensibles (ej. llaves privadas o errores de DB)
        en el cuerpo de la respuesta.
        Aborta temprano si el Content-Type es binario/multimedia.

        Args:
            record (RequestRecord): El registro a analizar.

        Retorna:
            list[PassiveFinding]: Hallazgos críticos o altos.
        """
        findings: list[PassiveFinding] = []

        if not record.response_body:
            return findings

        # Comprobar Content-Type para evitar escanear binarios
        try:
            headers_lower = {k.lower(): v for k, v in record.response_headers.items()}
            content_type = str(headers_lower.get("content-type", "")).lower()
            
            # Si es un archivo binario explícito, abortar
            if any(t in content_type for t in ["image/", "video/", "font/", "application/octet-stream"]):
                return findings
        except (AttributeError, TypeError):
            pass # Si falla el parseo de headers, intentamos de todas formas

        try:
            body_text = record.response_body.decode("utf-8", errors="ignore")
        except Exception:
            return findings # Si no se puede decodificar, no es texto
            
        # Revisar patrones críticos (ej. llaves privadas)
        for pattern, title in self._critical_patterns:
            if pattern.search(body_text):
                findings.append(
                    PassiveFinding(
                        request_id=record.id,
                        severity="Critical",
                        title=title,
                        description="Se detectó la exposición de una llave privada en el cuerpo de la respuesta. Esto representa un riesgo máximo de seguridad.",
                    )
                )

        # Revisar patrones altos (ej. errores de BD)
        for pattern, title in self._high_patterns:
            if pattern.search(body_text):
                findings.append(
                    PassiveFinding(
                        request_id=record.id,
                        severity="High",
                        title=title,
                        description="Se encontró un error de base de datos en el cuerpo de la respuesta. Esto puede facilitar inyecciones SQL u otras debilidades de backend.",
                    )
                )

        return findings
