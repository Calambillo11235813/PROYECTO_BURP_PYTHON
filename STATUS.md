# 📊 STATUS DEL PROYECTO — Mini-Burp Suite
**Materia:** Ingeniería de Software 2  
**Última actualización:** 2026-04-20  
**Stack:** Python 3.x · socket · threading · CustomTkinter · requests

---

## Resumen General

| Módulo | Casos de Uso | Implementados | Pendientes | Estado |
|---|:---:|:---:|:---:|---|
| **A — Interceptor Proxy (Core)** | 4 | 4 | 0 | ✅ Completo |
| **B — Repeater** | 3 | 3 | 0 | ✅ Completo |
| **C — Intruder (Fuzzing)** | 3 | 3 | 0 | ✅ Completo |
| **D — Reporting & Analysis** | 2 | 0 | 2 | 🔴 No iniciado |
| **Tests unitarios** | — | 50 tests | — | ✅ Pasando |

---

## 🔵 Módulo A — Interceptor Proxy (Core)
> Archivo principal: `proxy/proxy_server.py` · Clase: `ProxyServer`

### CU-01 · Configuración de Proxy
> El usuario define la IP y el puerto local para la escucha de tráfico.

**Estado: ✅ IMPLEMENTADO**

- [x] IP y puerto parametrizados en el constructor `ProxyServer(host, port)`
- [x] Valores por defecto: `127.0.0.1:8080`
- [x] Soporte de argumentos CLI: `python main.py [puerto]` o `python main.py [host] [puerto]`
- [x] Opción `SO_REUSEADDR` para reinicios rápidos sin error de puerto ocupado

```bash
python main.py              # → 127.0.0.1:8080
python main.py 9090         # → 127.0.0.1:9090
python main.py 0.0.0.0 8080 # → todas las interfaces
```

---

### CU-02 · Intercepción de Peticiones
> Captura automática de peticiones salientes del navegador.

**Estado: ✅ IMPLEMENTADO**

- [x] Captura de peticiones **HTTP** (GET, POST, PUT, DELETE, etc.)
- [x] Captura de peticiones **HTTPS** via método `CONNECT` (tunnel TCP)
- [x] Multithreading: cada conexión en su propio hilo (`threading.Thread`)
- [x] `threading.Lock` para thread-safety del contador de peticiones
- [x] Timeout configurable en sockets (`CONNECTION_TIMEOUT = 10s`)
- [x] Parsing completo de la petición: método, host, puerto, path, headers, body
- [x] Validado con Microsoft Edge (interceptado +40 requests en pruebas reales)

> ⚠️ El tunnel HTTPS es **transparente** (no descifra TLS). Para leer
> contenido HTTPS se necesitaría SSL MITM con certificado propio (extensión futura).

---

### CU-03 · Visualización de Historial (Logs)
> Registro tabular de todas las peticiones con sus códigos de respuesta.

**Estado: ✅ IMPLEMENTADO**  
**Archivo:** `proxy/history.py` · Clases: `RequestRecord`, `History`

- [x] Log en consola de cada petición con timestamp, método, host:puerto, path
- [x] Log del status code de cada respuesta HTTP
- [x] Numeración secuencial de peticiones (`[REQUEST #N]`)
- [x] Colores ANSI para distinguir tipos de eventos (azul, verde, amarillo, rojo)
- [x] Truncado automático a 1500 chars para no saturar la consola
- [x] **Historial persistente** en memoria — dataclass `RequestRecord` almacena método, host, port, path, headers, body, response_status, duration_ms y client_ip
- [x] **Filtros combinables** — `history.filter(method, host, status_code, min_status, max_status)` case-insensitive
- [x] **Exportación a `.txt`** — tabla formateada con cabeceras y resumen total
- [x] **Exportación a `.csv`** — compatible con Excel y pandas
- [x] **`print_table()`** — imprime resumen tabular en consola
- [x] **Medición de round-trip** — `duration_ms` calculado con `time.perf_counter()`
- [x] `ProxyServer.history` integrado: cada petición se guarda automáticamente al final de `_handle_client()`
- [x] Thread-safe con `threading.RLock` en `History`

```python
# Ejemplos de uso tras levantar el proxy
proxy.history.print_table()                          # ver en consola
proxy.history.filter(method="POST")                  # solo POSTs
proxy.history.filter(host="google", min_status=400)  # errores en google
proxy.history.export_csv("reports/historial.csv")    # exportar
proxy.history.export_txt("reports/historial.txt")    # exportar legible
```

---

### CU-04 · Modificación en Tiempo Real
> Interrupción del tráfico para editar cabeceras o parámetros antes del envío.

**Estado: ✅ IMPLEMENTADO**

- [x] Modo "intercept ON/OFF" (pausa la petición antes de reenviarla) a través de `InterceptController`
- [x] Gestión de peticiones pausadas mediante una `Queue` (cola FIFO) y `threading.Event`
- [x] Interfaz Gráfica (`CustomTkinter`) para revisar la petición pausada y editarla
- [x] Reenvío de la petición modificada al servidor mediante el botón "Forward"
- [x] Opción de descartar la petición mediante el botón "Drop" (retorna un 403 local)
- [x] Timeout de seguridad (60s) automático para no dejar colgado al navegador

> 💡 El Módulo A Core queda finalizado. Integramos todo en la pestaña `Proxy` de la interfaz gráfica recién creada.

---

## 🟢 Módulo B — Repeater (Análisis Manual)
> Archivo: `repeater.py` · GUI: `gui/repeater_tab.py`

| CU | Descripción | Estado |
|---|---|---|
| CU-05 | Clonación de Petición → enviar al Repeater | ✅ Implementado |
| CU-06 | Reenvío Manipulado (verbos, headers, body libres) | ✅ Implementado |
| CU-07 | Comparativa de Respuestas entre distintos inputs | ✅ Implementado |

**Implementado:**
- [x] Clase `Repeater` con método `send(raw_request) -> RepeaterResponse`
- [x] Parser de petición en texto plano con extracción de método, host, path, headers y body
- [x] Panel dual Request / Response en `RepeaterTab` (editable | solo lectura)
- [x] Selector de timeout y label de estado con duración y bytes recibidos
- [x] Integración con ProxyTab: botón "Send to Repeater" (CU-05)
- [x] Envío en hilo daemon — GUI no bloqueante

---

## 🟢 Módulo C — Intruder (Automatización/Fuzzing)
> Archivo: `intruder.py` · GUI: `gui/intruder_tab.py` · Doc: `MODULO_INTRUDER.md`

| CU | Descripción | Estado |
|---|---|---|
| CU-08 | Definición de Puntos de Inyección (marcadores §payload§) | ✅ Implementado |
| CU-09 | Gestión de Payloads (cargar diccionarios `.txt`) | ✅ Implementado |
| CU-10 | Ejecución de Ataque (envío masivo, registro de respuestas) | ✅ Implementado |

**Implementado:**
- [x] Clase `Intruder` con `load_payloads()`, `set_template()`, `run()` y `stop()`
- [x] Marcador de inyección `§texto§` (mismo estándar que Burp Suite real)
- [x] Diccionarios integrados: `payloads/sqli.txt`, `xss.txt`, `traversal.txt`
- [x] Soporte de archivos de payloads personalizados (cualquier `.txt`)
- [x] Control de concurrencia con `threading.Semaphore` (1-20 hilos configurables)
- [x] Flag de cancelación `stop()` thread-safe
- [x] Dataclass `IntruderResult` con: index, payload, status_code, length, duration_ms, error
- [x] GUI `IntruderTab`: editor de template, panel de payloads, tabla de resultados
- [x] Tabla coloreada por código HTTP (🟢 2xx · 🔵 3xx · 🟡 4xx · 🔴 5xx)
- [x] Botón "Añadir §§" para envolver selección con marcadores
- [x] Export CSV de resultados del ataque
- [x] Envío en hilo daemon — GUI no bloqueante

```python
# Ejemplo de uso programático
intruder = Intruder()
payloads = intruder.load_payloads("payloads/sqli.txt")   # CU-09
intruder.set_template("GET /search?q=§test§ HTTP/1.1\nHost: site.com\n\n")  # CU-08
intruder.run(payloads=payloads, on_result=mi_callback, threads=5)  # CU-10
```

---

## 🔴 Módulo D — Reporting & Analysis
> Integrado en `logic/scanner.py` + `logic/utils.py` (planificados)

| CU | Descripción | Estado |
|---|---|---|
| CU-11 | Detección Pasiva (errores 500, cabeceras inseguras) | ❌ No iniciado |
| CU-12 | Exportación de Resultados a informe técnico | ❌ No iniciado |

**Pendiente implementar:**
- [ ] Análisis de respuestas para flags de seguridad (`X-Frame-Options`, `CSP`, etc.)
- [ ] Detección de errores de servidor (HTTP 500) como indicadores de SQLi
- [ ] Generador de informe en `/reports/`

---

## 📁 Estructura de Archivos

### Implementado ✅
```
PROYECTO_BURP_PYTHON/
├── main.py                 ✅ Punto de entrada: inicializa Proxy y GUI
├── repeater.py             ✅ CU-05/06/07: Motor de reenvío manual (Módulo B)
├── intruder.py             ✅ CU-08/09/10: Motor de fuzzing (Módulo C)
├── README.md               ✅ Documentación de uso del proxy
├── Documentacion.md        ✅ Especificación del proyecto
├── STATUS.md               ✅ Este archivo
├── MODULO_INTRUDER.md      ✅ Documentación técnica del Módulo C
├── .gitignore              ✅ Ignora temporales
├── proxy/
│   ├── __init__.py         ✅ Paquete (expone servidor, handler, intercept, history)
│   ├── server.py           ✅ Socket TCP de bajo nivel (accept loop)
│   ├── handler.py          ✅ Procesa conexiones, túneles, delegación (CU-02, CU-04)
│   ├── history.py          ✅ CU-03: historial persistente
│   ├── proxy_server.py     ✅ Shim de compatibilidad backwards
│   └── MODULO_PROXY.md     ✅ Doc extensa Módulo A
├── logic/
│   └── parser.py           ✅ Parseo puro de strings a dataclass de requests
├── gui/
│   ├── __init__.py         ✅
│   ├── app.py              ✅ Ventana principal, tab control (Proxy/Repeater/Intruder)
│   ├── proxy_tab.py        ✅ UI Intercept, history table, visor (Módulo A)
│   ├── repeater_tab.py     ✅ Panel Request/Response dual (Módulo B)
│   ├── intruder_tab.py     ✅ Editor template + payloads + tabla resultados (Módulo C)
│   └── colors.py           ✅ Tokens de diseño del color oscuro
├── payloads/
│   ├── sqli.txt            ✅ ~40 payloads SQL Injection
│   ├── xss.txt             ✅ ~25 payloads XSS
│   └── traversal.txt       ✅ ~30 payloads Path Traversal
└── tests/
    ├── __init__.py         ✅
    ├── test_proxy.py       ✅ ~50 tests unitarios (todos passing)
    └── README.md           ✅
```

### Pendiente ❌
```
PROYECTO_BURP_PYTHON/
├── logic/
│   ├── scanner.py          ❌ CU-11: detección pasiva de cabeceras inseguras
│   └── utils.py            ❌ Funciones auxiliares
└── reports/                ❌ CU-12: directorio de informes exportados
```

---

## 🧪 Tests

### Suite original — `TestParseRequest` + `TestProxyInit`

| Test | Clase | Estado |
|---|---|---|
| `test_parse_get_request` | `TestParseRequest` | ✅ OK |
| `test_parse_get_with_custom_port` | `TestParseRequest` | ✅ OK |
| `test_parse_connect_request` | `TestParseRequest` | ✅ OK |
| `test_parse_post_with_body` | `TestParseRequest` | ✅ OK |
| `test_parse_empty_request_returns_none` | `TestParseRequest` | ✅ OK |
| `test_headers_parsed_as_dict` | `TestParseRequest` | ✅ OK |
| `test_default_host_port` | `TestProxyInit` | ✅ OK |
| `test_custom_host_port` | `TestProxyInit` | ✅ OK |
| `test_initial_request_count` | `TestProxyInit` | ✅ OK |

### CU-03 — `TestRequestRecord` (10 tests)

| Test | Descripción | Estado |
|---|---|---|
| `test_status_code_parsed_correctly` | Extrae 404 de `"HTTP/1.1 404 Not Found"` | ✅ OK |
| `test_status_code_200` | Extrae 200 correctamente | ✅ OK |
| `test_status_code_tunnel` | CONNECT retorna 0 | ✅ OK |
| `test_url_http` | Reconstruye URL HTTP | ✅ OK |
| `test_url_https` | Reconstruye URL HTTPS | ✅ OK |
| `test_url_custom_port` | Puerto no estándar en la URL | ✅ OK |
| `test_url_connect` | URL en modo CONNECT | ✅ OK |
| `test_to_dict_keys` | Claves del diccionario serializado | ✅ OK |
| `test_to_dict_values` | Valores correctos en el dict | ✅ OK |
| `test_str_representation` | `__str__` contiene id y método | ✅ OK |

### CU-03 — `TestHistory` (20 tests)

| Test | Descripción | Estado |
|---|---|---|
| `test_initially_empty` | Historial vacío al crear | ✅ OK |
| `test_add_increases_count` | `add()` incrementa tamaño | ✅ OK |
| `test_all_returns_copy` | `all()` retorna copia independiente | ✅ OK |
| `test_get_by_id_found` | Busca registro por ID | ✅ OK |
| `test_get_by_id_not_found` | ID inexistente retorna None | ✅ OK |
| `test_filter_by_method` | Filtra por verbo HTTP | ✅ OK |
| `test_filter_method_case_insensitive` | Filtro sin distinción mayúsculas | ✅ OK |
| `test_filter_by_host_substring` | Filtra por substring del host | ✅ OK |
| `test_filter_by_status_code` | Filtra código exacto | ✅ OK |
| `test_filter_by_status_range` | Filtra rango de códigos | ✅ OK |
| `test_filter_combined_method_and_host` | Filtros combinados (AND) | ✅ OK |
| `test_filter_no_match_returns_empty` | Sin resultados → lista vacía | ✅ OK |
| `test_export_txt_creates_file` | Exporta archivo `.txt` | ✅ OK |
| `test_export_txt_contains_data` | `.txt` contiene host y método | ✅ OK |
| `test_export_csv_creates_file` | Exporta archivo `.csv` | ✅ OK |
| `test_export_csv_has_correct_columns` | Columnas correctas en CSV | ✅ OK |
| `test_export_csv_values` | Valores correctos en CSV | ✅ OK |
| `test_export_filtered_subset` | Exporta solo subconjunto filtrado | ✅ OK |
| `test_clear_empties_history` | `clear()` vacía el historial | ✅ OK |
| `test_proxy_has_history_attribute` | `ProxyServer` integra `History` | ✅ OK |

### CU-04 — `TestInterceptController` (11 tests nuevos)

| Test | Descripción | Estado |
|---|---|---|
| `test_initially_disabled` | Flag inicial apagada | ✅ OK |
| `test_no_pending_initially` | Cola vacía al instanciar | ✅ OK |
| `test_enable_sets_flag` | `enable()` prende flag | ✅ OK |
| `test_disable_clears_flag` | `disable()` apaga flag | ✅ OK |
| `test_pending_forward_original` | Forward directo (sin args) | ✅ OK |
| `test_pending_forward_modified` | Forward con contenido editado | ✅ OK |
| `test_pending_drop` | Drop suelta hilo con 403 | ✅ OK |
| `test_next_pending_returns_request` | Cola recupera petición FIFO | ✅ OK |
| `test_pending_count_increments` | Incremento cuenta pendientes | ✅ OK |
| `test_pending_timeout_returns_original` | Resuelve tras timeout largo | ✅ OK |

```
Ran 50 tests in 0.04s — OK ✅
```

---

## 🗺️ Próximos Pasos Sugeridos

```
1. ✅ [Módulo A] CORE y GUI de intercepción completados
2. ✅ [Módulo B] Repeater con panel dual Request/Response implementado
3. ✅ [Módulo C] Intruder con fuzzing, payloads y tabla de resultados implementado
4.    [Módulo D] Implementar logic/scanner.py: detección pasiva de cabeceras inseguras (CU-11)
5.    [Módulo D] Generador de informes en /reports/ con export HTML/PDF (CU-12)
```
