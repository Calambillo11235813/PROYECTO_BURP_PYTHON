"""
main.py
-------
Punto de entrada del Proxy HTTP Interceptor.

Uso:
    python main.py              → inicia en 127.0.0.1:8080
    python main.py 9090         → puerto personalizado
    python main.py 0.0.0.0 9090 → escucha en todas las interfaces
"""

import sys
from proxy.proxy_server import ProxyServer, PROXY_HOST, PROXY_PORT


def main():
    host = PROXY_HOST
    port = PROXY_PORT

    # Parseo simple de argumentos (sin librerías externas)
    args = sys.argv[1:]
    if len(args) == 1:
        port = int(args[0])
    elif len(args) == 2:
        host = args[0]
        port = int(args[1])

    proxy = ProxyServer(host=host, port=port)
    proxy.start()


if __name__ == "__main__":
    main()
