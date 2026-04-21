"""
core/certs_manager.py
---------------------
Gestión de certificados SSL para el MITM del proxy (CU-04 HTTPS).

Genera y cachea en disco:
    ca.crt / ca.key  → Autoridad Certificadora raíz (instalada en el navegador
                        UNA sola vez para que confíe en el proxy).
    <dominio>.crt    → Certificados de dominio firmados por la CA, generados
     <dominio>.key      dinámicamente la primera vez que se visita cada host.

Dependencia: pip install cryptography

Thread-safety: un RLock protege la caché y la escritura de archivos
cuando múltiples hilos de conexión visitan dominios distintos en paralelo.

Autores: Diogo Nicolas Rodriguez Gomez, Javier Soliz Rueda
Materia: Ingeniería de Software 2
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

# ── Rutas y constantes ────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).parent.parent
CERTS_DIR     = _PROJECT_ROOT / "certs"
CA_CERT_PATH  = CERTS_DIR / "ca.crt"
CA_KEY_PATH   = CERTS_DIR / "ca.key"

CA_COMMON_NAME   = "Mini-Burp Suite CA"
CA_ORGANIZATION  = "Mini-Burp Suite — SW2 2026"
CA_VALIDITY_DAYS = 3650   # 10 años para la CA raíz
DOMAIN_VALID_DAYS = 365   # 1 año para cada cert de dominio


class CertsManager:
    """
    Gestiona la CA raíz y los certificados de dominio para MITM SSL.

    Al instanciar, carga la CA desde disco si existe; si no, la genera
    automáticamente y avisa al usuario que debe instalarla en el navegador.

    Uso típico:
        mgr = CertsManager()
        cert_path, key_path = mgr.get_domain_cert("www.google.com")
        # → certs/www.google.com.crt  y  certs/www.google.com.key
    """

    def __init__(self) -> None:
        CERTS_DIR.mkdir(parents=True, exist_ok=True)
        self._lock:  threading.RLock = threading.RLock()
        self._cache: dict[str, tuple[Path, Path]] = {}
        self._ca_cert, self._ca_key = self._load_or_create_ca()

    # ── API pública ────────────────────────────────────────────────────────────

    @property
    def ca_cert_path(self) -> Path:
        """Ruta al cert raíz de la CA (el que el usuario debe instalar)."""
        return CA_CERT_PATH

    def get_domain_cert(self, hostname: str) -> tuple[Path, Path]:
        """
        Retorna (cert_path, key_path) para el dominio dado.

        Genera el certificado si no existe en disco; lo sirve desde caché
        en memoria si ya fue generado durante esta ejecución.

        Args:
            hostname (str): Dominio destino, ej. 'www.google.com'.

        Returns:
            tuple[Path, Path]: Rutas al .crt y .key del dominio.
        """
        with self._lock:
            if hostname in self._cache:
                return self._cache[hostname]
            result = self._generate_domain_cert(hostname)
            self._cache[hostname] = result
            return result

    # ── CA: carga o creación ───────────────────────────────────────────────────

    def _load_or_create_ca(
        self,
    ) -> tuple[x509.Certificate, rsa.RSAPrivateKey]:
        """Lee la CA de disco o la genera si no existe."""
        if CA_CERT_PATH.exists() and CA_KEY_PATH.exists():
            return self._load_ca()
        return self._create_ca()

    def _load_ca(
        self,
    ) -> tuple[x509.Certificate, rsa.RSAPrivateKey]:
        """Deserializa ca.crt y ca.key desde PEM."""
        cert = x509.load_pem_x509_certificate(CA_CERT_PATH.read_bytes())
        key  = serialization.load_pem_private_key(
            CA_KEY_PATH.read_bytes(), password=None,
        )
        print(f"[CA] Certificado raíz cargado: {CA_CERT_PATH}")
        return cert, key  # type: ignore[return-value]

    def _create_ca(
        self,
    ) -> tuple[x509.Certificate, rsa.RSAPrivateKey]:
        """
        Genera una CA auto-firmada con extensiones BasicConstraints (CA=True)
        y la guarda en disco. Imprime instrucciones para instalarla.
        """
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = datetime.now(timezone.utc)
        name = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME,        CA_COMMON_NAME),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME,  CA_ORGANIZATION),
        ])

        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + timedelta(days=CA_VALIDITY_DAYS))
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=None),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,  key_cert_sign=True,
                    crl_sign=True,           content_commitment=False,
                    key_encipherment=False,  data_encipherment=False,
                    key_agreement=False,     encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .sign(key, hashes.SHA256())
        )

        CA_CERT_PATH.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        CA_KEY_PATH.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            )
        )

        print("\n" + "═" * 60)
        print("  [CA] ¡Certificado raíz generado!")
        print(f"  Archivo: {CA_CERT_PATH}")
        print("  Instálalo en tu navegador para interceptar HTTPS:")
        print("  Edge/Chrome → Configuración → Certificados → Autoridades")
        print("═" * 60 + "\n")
        return cert, key

    # ── Certificados de dominio ────────────────────────────────────────────────

    def _generate_domain_cert(self, hostname: str) -> tuple[Path, Path]:
        """
        Genera un certificado TLS para `hostname` firmado por nuestra CA.

        Incluye SAN (Subject Alternative Name) para que los navegadores
        modernos (Chrome, Edge) acepten el certificado correctamente.

        Args:
            hostname (str): Dominio de destino, ej. 'api.github.com'.

        Returns:
            tuple[Path, Path]: (cert_path, key_path) del dominio.
        """
        # Sanitizar para usarlo como nombre de archivo (sin * ni :)
        safe_name = hostname.replace("*", "wildcard").replace(":", "_")
        cert_path = CERTS_DIR / f"{safe_name}.crt"
        key_path  = CERTS_DIR / f"{safe_name}.key"

        # Reutilizar cert existente en disco (de sesiones anteriores)
        if cert_path.exists() and key_path.exists():
            return cert_path, key_path

        domain_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = datetime.now(timezone.utc)

        san_entries: list[x509.GeneralName] = [x509.DNSName(hostname)]

        cert = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([
                x509.NameAttribute(NameOID.COMMON_NAME, hostname),
            ]))
            .issuer_name(self._ca_cert.subject)
            .public_key(domain_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + timedelta(days=DOMAIN_VALID_DAYS))
            .add_extension(
                x509.SubjectAlternativeName(san_entries),
                critical=False,
            )
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True,
            )
            .sign(self._ca_key, hashes.SHA256())
        )

        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(
            domain_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            )
        )
        return cert_path, key_path
