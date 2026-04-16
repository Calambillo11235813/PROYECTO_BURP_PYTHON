# Módulo `proxy` — HTTP Interceptor
**Ingeniería de Software 2 | Herramienta de Pentesting tipo Burp Suite**

---

## ¿Qué hace este módulo?

Este módulo implementa un **Proxy HTTP interceptor** desde cero usando únicamente las librerías
estándar de Python `socket` y `threading`. Su función principal es:

> Posicionarse **entre el navegador y el servidor**, recibir cada petición HTTP/HTTPS,
> imprimirla en consola (interceptación), y reenviarla transparentemente al destino original.

En la práctica, al levantar `python main.py` y configurar Edge con el proxy `127.0.0.1:8080`,
**todo el tráfico del navegador pasa por aquí** — exactamente como funciona Burp Suite.

---

## Archivos del módulo

```
proxy/
├── __init__.py         ← Expone ProxyServer al resto del proyecto
└── proxy_server.py     ← Toda la lógica (420 líneas)
```

---

## Clase `ProxyServer`

### Atributos de instancia

| Atributo | Tipo | Descripción |
|---|---|---|
| `host` | `str` | IP donde escucha el proxy (`127.0.0.1` por defecto) |
| `port` | `int` | Puerto del proxy (`8080` por defecto) |
| `_server_socket` | `socket.socket` | Socket TCP del servidor (el que acepta conexiones) |
| `_running` | `bool` | Flag para el bucle principal; `False` al hacer `stop()` |
| `_request_count` | `int` | Contador global de peticiones interceptadas |
| `_lock` | `threading.Lock` | Mutex para proteger `_request_count` de race conditions |

### Constantes globales

```python
PROXY_HOST        = "127.0.0.1"
PROXY_PORT        = 8080
BUFFER_SIZE       = 4096   # bytes leídos por recv() en cada llamada
MAX_CONNECTIONS   = 10     # backlog del socket (cola de conexiones pendientes)
CONNECTION_TIMEOUT = 10    # segundos sin datos → cierre del socket
```

---

## Métodos y su responsabilidad

### `start()` — El corazón del servidor
```
socket() → bind() → listen() → [bucle] accept() → Thread(target=_handle_client)
```
Crea el socket TCP con `AF_INET + SOCK_STREAM`, lo enlaza al host:puerto y entra en
un bucle infinito esperando conexiones. **Cada conexión aceptada lanza un hilo nuevo.**

La opción `SO_REUSEADDR` es clave: permite reutilizar el puerto inmediatamente después
de un `Ctrl+C`, sin esperar el tiempo de `TIME_WAIT` de TCP.

```python
self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
```

---

### `_handle_client()` — Orquestador por hilo
Ejecutado en su **propio hilo** para cada cliente. Coordina el flujo completo:

```
recv → parse → log (interceptar) → forward / tunnel
```

Maneja excepciones de forma silenciosa (`socket.timeout`, `ConnectionResetError`)
para que un cliente roto no derribe al servidor completo. El `finally` siempre
cierra el socket del cliente.

---

### `_receive_all()` — Lectura completa del socket

```python
while True:
    chunk = sock.recv(BUFFER_SIZE)   # lee hasta 4096 bytes
    data += chunk
    if len(chunk) < BUFFER_SIZE:
        break                        # probablemente no hay más datos
```

`recv()` no garantiza leer todos los datos en una sola llamada (el kernel puede
fragmentarlos). Este método acumula chunks hasta que el socket deja de enviar.

---

### `_parse_request()` — Disección de la petición HTTP

Toma los bytes crudos y devuelve la tupla:
```python
(method, host, port, path, headers_dict, body)
```

Maneja tres casos:

| Caso | Ejemplo | Comportamiento |
|---|---|---|
| `CONNECT` | `CONNECT www.bing.com:443 HTTP/1.1` | Extrae host:puerto para tunnel HTTPS |
| URL absoluta | `GET http://example.com/path HTTP/1.1` | Parsea scheme + host + port + path |
| URL relativa | `GET /path HTTP/1.1` | Busca el host en la cabecera `Host:` |

Las cabeceras se devuelven como `dict` para facilitar su inspección:
```python
{"Host": "example.com", "User-Agent": "Mozilla/5.0...", "Authorization": "Bearer ..."}
```

---

### `_forward_request()` — Reenvío HTTP

Abre un **segundo socket TCP** hacia el servidor real, manda la petición original
byte a byte y devuelve la respuesta completa. El proxy es completamente transparente:
el servidor destino ve la petición como si viniera del navegador directamente.

```
[Edge] →(socket A)→ [ProxyServer] →(socket B)→ [Servidor real]
```

---

### `_handle_https_tunnel()` — Tunnel HTTPS (método CONNECT)

Cuando el navegador quiere conectarse a un sitio HTTPS, el proxy NO puede leer
el contenido porque está cifrado con TLS. El flujo es:

```
1. Edge envía:   CONNECT www.bing.com:443 HTTP/1.1
2. Proxy abre socket TCP hacia www.bing.com:443
3. Proxy responde: HTTP/1.1 200 Connection Established
4. A partir de aquí, el proxy retransmite bytes en ambas direcciones (relay)
```

El relay bidireccional se implementa con **2 hilos adicionales**:

```python
t1 = Thread(target=relay, args=(client_socket, server_socket))  # Edge → Bing
t2 = Thread(target=relay, args=(server_socket, client_socket))  # Bing → Edge
```

> **Nota de pentesting:** Esta implementación hace un tunnel *opaco* (no descifra TLS).
> Herramientas como Burp Suite van un paso más allá: hacen un **SSL MITM** generando
> un certificado falso firmado por su propia CA para poder leer el HTTPS también.

---

### `_log_request()` / `_log_response()` — La interceptación visible

Son los métodos que muestran el tráfico en consola con colores ANSI.
Esto es lo que vemos cuando Edge hace conexiones:

```
────────────────────────────────────────────────────────────
[REQUEST #40] 22:39:36 | Cliente: 127.0.0.1:57862
CONNECT www.bing.com:443
────────────────────────────────────────────────────────────
CONNECT www.bing.com:443 HTTP/1.1
Host: www.bing.com:443
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) Edg/147.0.0.0
```

Las respuestas largas se truncan a 1500 caracteres para no saturar la consola.

---

## Flujo completo de una petición

```
┌─────────────────────────────────────────────────────────────────┐
│  Microsoft Edge (127.0.0.1:8080 configurado como proxy)         │
└──────────────────────────┬──────────────────────────────────────┘
                           │  TCP connect a 127.0.0.1:8080
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  ProxyServer.start()  ←  server_socket.accept()                 │
│                                                                  │
│  Lanza Thread #N  ─────► _handle_client(client_socket)          │
│                               │                                  │
│                          _receive_all()      ← lee bytes crudos  │
│                          _parse_request()    ← disecciona HTTP   │
│                          _log_request()      ← INTERCEPTACIÓN ✓  │
│                               │                                  │
│                    ┌──────────┴──────────┐                       │
│                    │ HTTP                │ HTTPS (CONNECT)        │
│                    ▼                    ▼                        │
│            _forward_request()   _handle_https_tunnel()           │
│            (socket al dest.)    (relay TCP bidireccional)        │
│                    │                    │                        │
│            _log_response()      "200 Connection Established"     │
│            sendall() al Edge    + 2 hilos relay                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Threading: por qué se necesita

| Sin threading | Con threading |
|---|---|
| `accept()` bloquea hasta que llega **una** conexión | `accept()` lanza un hilo y vuelve a escuchar **inmediatamente** |
| El proxy atiende **1 petición a la vez** | El proxy atiende **N peticiones en paralelo** |
| Edge hace ~40 conexiones simultáneas → timeout | Edge funciona fluidamente |

El `threading.Lock` en `_handle_client()` es necesario porque múltiples hilos
podrían intentar incrementar `_request_count` al mismo tiempo → **race condition**:

```python
with self._lock:          # solo un hilo entra a la vez
    self._request_count += 1
    req_id = self._request_count
```

---

## Lo que vimos en tiempo real con Edge

Edge no es un navegador "simple" — hace **decenas de conexiones en paralelo**:

| Destino interceptado | Propósito |
|---|---|
| `www.bing.com:443` | Motor de búsqueda predeterminado de Edge |
| `functional.events.data.microsoft.com:443` | Telemetría / analytics de Microsoft |
| Otros dominios microsoft.com | Sincronización, actualizaciones, servicios |

Todo esto llega como `CONNECT` porque Edge usa HTTPS. El proxy los maneja transparentemente
con `_handle_https_tunnel()` y el navegador funciona con normalidad.

---

## Posibles extensiones (para el parcial / proyecto)

- [ ] **SSL MITM**: Interceptar y descifrar HTTPS generando certificados dinámicos con `cryptography`
- [ ] **Filtro de peticiones**: Interceptar solo ciertas URLs (regex sobre el host/path)
- [ ] **Modificar peticiones**: Cambiar cabeceras o cuerpo antes del reenvío
- [ ] **GUI**: Mostrar las peticiones en una interfaz gráfica (tkinter o web)
- [ ] **Guardar tráfico**: Exportar peticiones a archivos `.txt` o `.har`
- [ ] **Repetidor**: Reenviar manualmente una petición modificada (como el Repeater de Burp)
