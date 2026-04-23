# HTTP Proxy Interceptor
**Ingeniería de Software 2 — Herramienta de Pentesting**

## Descripción
Proxy HTTP interceptor implementado desde cero en Python usando únicamente las librerías estándar `socket` y `threading`. Inspirado en herramientas como **Burp Suite**.

## Estructura del Proyecto
```
SOFTWARE/
├── main.py               ← Punto de entrada
├── test_proxy.py         ← Tests unitarios
├── README.md
└── proxy/
    ├── __init__.py
    └── proxy_server.py   ← Clase principal ProxyServer
```

## Quickstart
```bash
# Iniciar el proxy (puerto por defecto 8080)
python main.py

# Puerto personalizado
python main.py 9090

# Todas las interfaces de red
python main.py 0.0.0.0 8080
```

Luego, **configura tu navegador** para usar el proxy:
- **Host:** `127.0.0.1`
- **Puerto:** `8080`

## Ejecutar Tests
```bash
python test_proxy.py
# ó con pytest:
python -m pytest test_proxy.py -v
```

## Arquitectura

### `ProxyServer` — Métodos principales

| Método | Responsabilidad |
|---|---|
| `start()` | Crea el socket servidor, bucle `accept()` → lanza hilos |
| `stop()` | Cierra el socket y detiene el servidor |
| `_handle_client()` | Orquesta el flujo completo para cada conexión (en su propio hilo) |
| `_receive_all()` | Lee bytes del socket en bloques de `BUFFER_SIZE` |
| `_parse_request()` | Extrae método, host, puerto, path y cabeceras de la petición cruda |
| `_forward_request()` | Abre socket al destino, reenvía petición y retorna respuesta |
| `_handle_https_tunnel()` | Relay TCP para conexiones HTTPS (método CONNECT) |
| `_log_request()` | Imprime la petición interceptada con colores en consola |
| `_log_response()` | Imprime el status code de la respuesta |

### Flujo de una petición HTTP

```
[Navegador]
    │  Petición HTTP cruda
    ▼
[ProxyServer.accept()]          ← socket servidor en 127.0.0.1:8080
    │  Nuevo Thread por conexión
    ▼
[_handle_client()]
    │
    ├─► _receive_all()          ← lee bytes del socket del navegador
    ├─► _parse_request()        ← extrae método, host, puerto, path
    ├─► _log_request()          ← INTERCEPTACIÓN: imprime en consola
    │
    ├─► [HTTP]  _forward_request()        ← socket nuevo al servidor real
    │               │ respuesta
    │           _log_response()
    │           sendall() → navegador
    │
    └─► [HTTPS] _handle_https_tunnel()    ← relay TCP bidireccional
                    └─► "200 Connection Established"
```

### Threading: ¿Por qué un hilo por conexión?

El bucle `accept()` es **bloqueante**: espera hasta que llegue una conexión.
Si manejáramos cada petición secuencialmente, el proxy solo podría atender
a un cliente a la vez. Al lanzar un `threading.Thread` por cada conexión:

- El hilo principal sigue esperando nuevas conexiones sin bloquearse.
- Cada petición se procesa en paralelo.
- El `threading.Lock` protege el contador compartido `_request_count` de **race conditions**.

### Soporte HTTP vs HTTPS

| Protocolo | Método | Comportamiento |
|---|---|---|
| HTTP | GET, POST, etc. | Lee, intercepta y reenvía completamente |
| HTTPS | CONNECT | Establece túnel TCP (no descifra TLS) |

> **Nota:** Para descifrar HTTPS (como Burp Suite) se necesita MITM con certificado SSL propio. Esta implementación hace un tunnel transparente, que es el comportamiento base correcto.

## Configurar Firefox como cliente de prueba

1. `Settings → Network Settings → Manual proxy configuration`
2. HTTP Proxy: `127.0.0.1`  Port: `8080`
3. Marcar: `Also use this proxy for HTTPS`
4. Navegar a cualquier sitio HTTP (ej: `http://httpbin.org/get`)

## Dependencias
Solo librería estándar de Python 3.10+:
- `socket`
- `threading`
- `datetime`
- `sys`
