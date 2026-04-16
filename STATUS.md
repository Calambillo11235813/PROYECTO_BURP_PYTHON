# 📊 STATUS DEL PROYECTO — Mini-Burp Suite
**Materia:** Ingeniería de Software 2  
**Última actualización:** 2026-04-16  
**Stack:** Python 3.x · socket · threading · CustomTkinter (pendiente)

---

## Resumen General

| Módulo | Casos de Uso | Implementados | Pendientes | Estado |
|---|:---:|:---:|:---:|---|
| **A — Interceptor Proxy (Core)** | 4 | 3 | 1 | 🟡 En progreso |
| **B — Repeater** | 3 | 0 | 3 | 🔴 No iniciado |
| **C — Intruder (Fuzzing)** | 3 | 0 | 3 | 🔴 No iniciado |
| **D — Reporting & Analysis** | 2 | 0 | 2 | 🔴 No iniciado |
| **Tests unitarios** | — | 39 tests | — | ✅ Pasando |

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

**Estado: ❌ NO IMPLEMENTADO**

- [ ] Modo "intercept ON/OFF" (pausa la petición antes de reenviarla)
- [ ] Interfaz (CLI o GUI) para editar la petición pausada
- [ ] Reenvío de la petición modificada al servidor
- [ ] Opción de descartar la petición

> 💡 Este CU requiere la GUI (`CustomTkinter`) o al menos una interfaz de edición
> por consola con `input()`. Es el siguiente paso lógico tras terminar el core.

---

## 🔴 Módulo B — Repeater (Análisis Manual)
> Archivo planificado: `repeater.py`

| CU | Descripción | Estado |
|---|---|---|
| CU-05 | Clonación de Petición → enviar al Repeater | ❌ No iniciado |
| CU-06 | Reenvío Manipulado (verbos, headers, body libres) | ❌ No iniciado |
| CU-07 | Comparativa de Respuestas entre distintos inputs | ❌ No iniciado |

**Pendiente implementar:**
- [ ] Clase `Repeater` con método `send(request_str) -> response`
- [ ] Parser de petición en texto plano editado por el usuario
- [ ] Diff visual entre respuesta original y respuesta modificada

---

## 🔴 Módulo C — Intruder (Automatización/Fuzzing)
> Archivo planificado: `intruder.py`

| CU | Descripción | Estado |
|---|---|---|
| CU-08 | Definición de Puntos de Inyección (marcadores en la petición) | ❌ No iniciado |
| CU-09 | Gestión de Payloads (cargar diccionarios `.txt`) | ❌ No iniciado |
| CU-10 | Ejecución de Ataque (envío masivo, registro de respuestas) | ❌ No iniciado |

**Pendiente implementar:**
- [ ] Diccionarios de payloads: `/payloads/sqli.txt`, `xss.txt`, `traversal.txt`
- [ ] Motor de fuzzing con control de tasa (rate limiting)
- [ ] Detección de anomalías en respuestas (status code, tamaño, tiempo)

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
├── main.py                 ✅ Punto de entrada con args CLI
├── test_proxy.py           ✅ 39 tests unitarios (todos passing)
├── README.md               ✅ Documentación de uso
├── Documentacion.md        ✅ Especificación del proyecto
├── STATUS.md               ✅ Este archivo
├── proxy/
│   ├── __init__.py         ✅ Paquete Python (expone ProxyServer, History, RequestRecord)
│   ├── proxy_server.py     ✅ Clase ProxyServer (~440 líneas)
│   ├── history.py          ✅ CU-03: RequestRecord + History (filtros + exportación)
│   └── MODULO_PROXY.md     ✅ Documentación técnica del módulo
└── tests/
    ├── __init__.py         ✅ Paquete de tests
    └── README.md           ✅ Convenciones y comandos
```

### Pendiente ❌
```
PROYECTO_BURP_PYTHON/
├── proxy_core.py           ❌ (fusionado en proxy/proxy_server.py)
├── repeater.py             ❌
├── intruder.py             ❌
├── gui/
│   ├── app_ui.py           ❌
│   ├── components.py       ❌
│   └── themes.json         ❌
├── logic/
│   ├── parser.py           ❌
│   ├── scanner.py          ❌
│   └── utils.py            ❌
├── payloads/
│   ├── sqli.txt            ❌
│   ├── xss.txt             ❌
│   └── traversal.txt       ❌
├── reports/                ❌ (directorio)
└── requirements.txt        ❌
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

```
Ran 39 tests in 0.004s — OK ✅
```

---

## 🗺️ Próximos Pasos Sugeridos

```
1. ✅ [Módulo A - CU-03] COMPLETADO — history.py con filtros y exportación
2.    [Módulo A - CU-04] Modo intercept ON/OFF con edición por consola
3.    [Módulo B]         Implementar repeater.py con clase Repeater
4.    [GUI]              Interfaz CustomTkinter con tabla de historial (usa History)
5.    [Módulo C]         Motor de fuzzing + diccionarios de payloads
6.    [Módulo D]         Scanner pasivo de cabeceras inseguras
```
