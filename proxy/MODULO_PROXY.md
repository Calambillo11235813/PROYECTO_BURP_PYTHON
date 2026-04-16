# Módulo A — Interceptor Proxy (Core)
**Ingeniería de Software 2 | Mini-Burp Suite**  
**Estado: ✅ COMPLETO** — 4/4 casos de uso implementados

---

## Descripción General

El Módulo A es el núcleo de la herramienta. Gestiona la **capa de red de bajo nivel** usando únicamente las librerías estándar de Python `socket` y `threading`, sin frameworks externos. Se posiciona como intermediario entre el navegador del usuario y el servidor web destino, capturando, analizando y opcionalmente modificando todo el tráfico HTTP en tiempo real.

```
[Navegador / Edge]
       │  TCP connect → 127.0.0.1:8080
       ▼
[ProxyServer — server.py]          ← acepta la conexión
       │  lanza Thread por conexión
       ▼
[ConnectionHandler — handler.py]   ← procesa la petición
       │
       ├─► [parser.py]             ← descompone los bytes HTTP
       ├─► [history.py]            ← guarda el registro (CU-03)
       ├─► [InterceptController]   ← pausa si intercept ON (CU-04)
       │
       └─► Socket al servidor real → respuesta → navegador
```

---

## Archivos del Módulo

| Archivo                 | Responsabilidad principal                      | CU que implementa |
|---|---|---|
| `proxy/server.py`       | Socket TCP: bind, listen, accept, lanzar hilos | CU-01           |
| `proxy/handler.py`      | Procesamiento de cada conexión individual      | CU-02, CU-04    |
| `proxy/history.py`      | Historial persistente, filtros y exportación   | CU-03           |
| `logic/parser.py`       | Parseo de bytes HTTP → `ParsedRequest`         | CU-02 (soporte) |
| `proxy/proxy_server.py` | Shim de compatibilidad (re-exporta `ProxyServer`) | — |

---

## Casos de Uso

---

### CU-01 — Configuración de Proxy
> *El usuario define la IP y el puerto local para la escucha de tráfico.*

**Archivo responsable:** `proxy/server.py` → clase `ProxyServer`

#### ¿Qué hace?

El usuario puede iniciar el proxy en cualquier dirección IP y puerto de su máquina. La configuración se realiza mediante argumentos de línea de comandos o directamente en el código. Antes de aceptar conexiones, el servidor:

1. Crea un socket TCP (`AF_INET + SOCK_STREAM`).
2. Aplica la opción `SO_REUSEADDR` para evitar errores de "puerto ocupado" al reiniciar rápidamente.
3. Hace `bind()` a la IP y puerto configurados.
4. Llama a `listen()` con un backlog de 10 conexiones pendientes.

#### Interfaces de configuración

```bash
python main.py              # host=127.0.0.1  puerto=8080 (defecto)
python main.py 9090         # host=127.0.0.1  puerto=9090
python main.py 0.0.0.0 8080 # escucha en todas las interfaces de red
```

```python
# Desde código:
proxy = ProxyServer(host="127.0.0.1", port=8080)
```

#### Configurar el navegador (Microsoft Edge)

```
Settings → System and performance → Open proxy settings
→ Activar "Use a proxy server"
→ Address: 127.0.0.1   Port: 8080
```

#### Constantes relevantes en `server.py`

| Constante | Valor | Descripción   |
|---|---|---|
| `PROXY_HOST`      | `"127.0.0.1"` | IP de escucha por defecto |
| `PROXY_PORT`      | `8080`        | Puerto por defecto |
| `MAX_CONNECTIONS` | `10`          | Backlog del socket (conexiones en cola) |

---

### CU-02 — Intercepción de Peticiones
> *Captura automática de peticiones salientes del navegador.*

**Archivos responsables:**
- `proxy/server.py` → bucle `accept()` + lanzamiento de hilos
- `proxy/handler.py` → `ConnectionHandler.handle()` + `_receive_all()` + `_forward_request()` + `_handle_https_tunnel()`
- `logic/parser.py` → `parse_request()` + `ParsedRequest`

#### ¿Qué hace?

Cada vez que el navegador abre una conexión TCP al proxy, `server.py` la acepta y lanza un **hilo independiente** (`threading.Thread`) que ejecuta `ConnectionHandler.handle()`. Este método orquesta el ciclo completo:

```
recv_all()          ← lee bytes crudos del socket del navegador
parse_request()     ← descompone la petición (método, host, port, path, headers, body)
_log_request()      ← imprime en consola con colores ANSI
─────────────────────────────────────────────────────────
HTTP:   _forward_request()       ← abre socket al servidor real y reenvía
HTTPS:  _handle_https_tunnel()   ← relay TCP bidireccional (método CONNECT)
─────────────────────────────────────────────────────────
_log_response()     ← imprime status code de la respuesta
sendall()           ← envía la respuesta de vuelta al navegador
```

#### Soporte de protocolos

| Protocolo | Método HTTP             | Comportamiento |
|---|---|---|
| HTTP      | GET, POST, PUT, DELETE… | Lee, imprime y reenvía completamente |
| HTTPS     | CONNECT                 | Tunnel TCP bidireccional (no descifra TLS) |

#### Output en consola (ejemplo real con Edge)

```
────────────────────────────────────────────────────────────
[REQUEST #40] 22:39:36 | Cliente: 127.0.0.1:57862
CONNECT www.bing.com:443
────────────────────────────────────────────────────────────
CONNECT www.bing.com:443 HTTP/1.1
Host: www.bing.com:443
User-Agent: Mozilla/5.0 ... Edg/147.0.0.0

[#40] Túnel HTTPS establecido → www.bing.com:443
```

#### `ParsedRequest` — resultado del parseo

```python
@dataclass
class ParsedRequest:
    method  : str           # "GET", "POST", "CONNECT", …
    host    : str           # "www.google.com"
    port    : int           # 80 (HTTP), 443 (HTTPS)
    path    : str           # "/api/search"
    headers : dict          # {"Host": "...", "User-Agent": "...", ...}
    body    : bytes         # b"param=value" (vacío en GETs)
```

#### Threading: por qué un hilo por conexión

El navegador moderno (Edge) abre **decenas de conexiones simultáneas**. Si el proxy procesara una a la vez, el navegador sufriría timeouts. Al lanzar un `Thread(daemon=True)` por conexión, el bucle `accept()` principal nunca se bloquea. El `threading.Lock` en `ConnectionHandler._next_id()` garantiza que el contador de peticiones no tenga race conditions.

---

### CU-03 — Visualización de Historial (Logs)
> *Registro tabular de todas las peticiones con sus códigos de respuesta.*

**Archivo responsable:** `proxy/history.py` → clases `RequestRecord` y `History`

#### ¿Qué hace?

Cada petición procesada por el proxy se almacena en memoria como un `RequestRecord`. El historial es accesible en cualquier momento y soporta filtros combinables y exportación a archivos.

#### `RequestRecord` — qué se guarda por petición

| Campo | Tipo | Ejemplo |
|---|---|---|
| `id` | `int` | `42` |
| `timestamp` | `datetime` | `2026-04-16 22:39:36` |
| `method` | `str` | `"GET"` |
| `host` | `str` | `"httpbin.org"` |
| `port` | `int` | `80` |
| `path` | `str` | `"/get"` |
| `headers` | `dict` | `{"Host": "httpbin.org", ...}` |
| `body` | `bytes` | `b"username=admin&..."` |
| `response_status` | `str` | `"HTTP/1.1 200 OK"` |
| `duration_ms` | `float` | `142.7` |
| `client_ip` | `str` | `"127.0.0.1"` |

#### API de la clase `History`

```python
# Ver en consola
proxy.history.print_table()

# Filtros (combinables entre sí)
proxy.history.filter(method="POST")
proxy.history.filter(host="google")
proxy.history.filter(status_code=404)
proxy.history.filter(min_status=400, max_status=499)   # rango de errores 4xx
proxy.history.filter(method="POST", host="api.target.com", min_status=200)

# Buscar por ID
proxy.history.get_by_id(42)

# Exportar
proxy.history.export_txt("reports/historial.txt")   # tabla legible
proxy.history.export_csv("reports/historial.csv")   # compatible con Excel/pandas

# Exportar subconjunto filtrado
errores = proxy.history.filter(min_status=500)
proxy.history.export_csv("reports/errores_500.csv", records=errores)

# Limpiar
proxy.history.clear()
```

#### Thread-safety

`History` usa un `threading.RLock` (reentrant lock) para que múltiples hilos de `ConnectionHandler` puedan agregar registros simultáneamente sin corrupción de datos.

---

### CU-04 — Modificación en Tiempo Real
> *Interrupción del tráfico para editar cabeceras o parámetros antes del envío.*

**Archivo responsable:** `proxy/handler.py` → clases `InterceptController` y `PendingRequest`

#### ¿Qué hace?

Cuando el modo intercept está activo (`intercept_enabled = True`), el proxy **pausa** cada petición HTTP antes de reenviarla al servidor. El hilo del handler queda bloqueado esperando una decisión externa (de la GUI o de la CLI). La decisión puede ser:

- **`forward`** — reenviar la petición original o una versión modificada.
- **`drop`** — descartar la petición (el navegador recibe un `403 Forbidden`).

#### Mecanismo: `threading.Event` + `Queue`

```
[Hilo del handler]                    [GUI / CLI — hilo principal]
        │                                          │
        │  intercept.intercept(id, raw, parsed)    │
        │─── crea PendingRequest ──────────────────►│
        │    └── encola en Queue                    │
        │                                          │
        │  pending.wait(timeout=60s)  ◄────────────│  pend = intercept.next_pending()
        │  [BLOQUEADO en Event]        │            │  pend.forward(modified_raw)
        │                              │            │  ó pend.drop()
        │  ◄── Event.set() ────────────┘            │
        │                                          │
        │  decision, final_raw = ("forward", raw)  │
        │  → _forward_request(...)                  │
```

#### Uso desde código

```python
# Activar intercepción
proxy = ProxyServer()
proxy.intercept.enable()
proxy.start()   # en un hilo separado

# Desde la GUI (bucle de eventos):
pending = proxy.intercept.next_pending()   # None si no hay peticiones en espera
if pending:
    print(pending.raw.decode())            # mostrar la petición al usuario
    modified = editar_en_gui(pending.raw)  # el usuario edita
    pending.forward(modified)              # reenviar modificada
    # ó
    pending.drop()                         # descartar
```

#### `PendingRequest` — campos accesibles desde la GUI

| Campo/Método | Descripción |
|---|---|
| `pending.id` | ID secuencial de la petición |
| `pending.raw` | Bytes crudos originales (editable) |
| `pending.parsed` | `ParsedRequest` con método, host, path, headers, body |
| `pending.forward(modified_raw)` | Libera el hilo con decisión "reenviar" |
| `pending.drop()` | Libera el hilo con decisión "descartar" |
| `pending.wait(timeout)` | Bloquea el hilo hasta recibir decisión |

#### Timeout de seguridad

Si la GUI/CLI no resuelve la petición en 60 segundos, el hilo del handler se desbloquea automáticamente y reenvía la petición original. Esto evita que el navegador quede colgado indefinidamente.

```python
decision, final_raw = pending.wait(timeout=60.0)
# decision == "timeout" → se usa el raw original
```

---

## Resumen de Implementación

| CU    | Clase principal                          | Métodos clave | Tests |
|---    |                                       ---|            ---|    ---|
| CU-01 | `ProxyServer`                            | `__init__`, `start`, `stop` | `TestProxyInit` (5 tests) |
| CU-02 | `ConnectionHandler`                      | `handle`, `_receive_all`, `_forward_request`, `_handle_https_tunnel` | `TestParseRequest` (6 tests) |
| CU-03 | `History` + `RequestRecord`              | `add`, `filter`, `export_txt`, `export_csv`, `print_table` | `TestHistory` (20) + `TestRequestRecord` (10) |
| CU-04 | `InterceptController` + `PendingRequest` | `enable`, `disable`, `intercept`, `next_pending`, `forward`, `drop`, `wait` | `TestInterceptController` (9 tests) |

**Total de tests del Módulo A: ~50 tests — todos passing ✅**

---

## Próxima Extensión Propuesta: SSL MITM

El Módulo A actualmente hace un **tunnel transparente** para HTTPS (no descifra TLS). Para interceptar tráfico HTTPS como lo hace Burp Suite se necesitaría:

1. Generar una CA (Certificate Authority) propia con la librería `cryptography`.
2. En `_handle_https_tunnel()`, en lugar de hacer relay TCP, hacer un handshake TLS con el servidor real y otro con el navegador usando un certificado falso firmado por la CA.
3. Instalar la CA en el navegador para que confíe en los certificados generados.

Esta extensión correspondería al **Módulo A v2.0** y es el camino natural hacia un Burp Suite completo.
