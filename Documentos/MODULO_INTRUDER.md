# 💥 Módulo C — Intruder

**Mini-Burp Suite · Ingeniería de Software 2**
**Autores:** Diogo Nicolas Rodriguez Gomez, Javier Soliz Rueda

---

## ¿Qué es el Intruder?

El **Intruder** es el motor de fuzzing automatizado de Mini-Burp Suite. Permite definir
una petición HTTP con **puntos de inyección**, cargar un **diccionario de payloads** y
lanzar un ataque masivo y controlado contra un servidor web para detectar vulnerabilidades.

Está inspirado directamente en el módulo **Intruder de Burp Suite Professional**.

---

## Casos de Uso implementados

| CU | Descripción | Estado |
|---|---|---|
| **CU-08** | Definición de Puntos de Inyección | ✅ Implementado |
| **CU-09** | Gestión de Payloads (diccionarios `.txt`) | ✅ Implementado |
| **CU-10** | Ejecución de Ataque con registro de respuestas | ✅ Implementado |

---

## Arquitectura del Módulo

```
intruder.py              ← Lógica pura (sin GUI). Testeable en aislado.
    ├── IntruderResult   ← Dataclass: resultado de un envío individual
    └── Intruder         ← Motor de ataque principal

gui/intruder_tab.py      ← Pestaña CustomTkinter de la interfaz gráfica
    └── IntruderTab      ← CTkFrame con toda la UI del módulo

payloads/
    ├── sqli.txt         ← Diccionario SQL Injection (~40 payloads)
    ├── xss.txt          ← Diccionario XSS (~25 payloads)
    └── traversal.txt    ← Diccionario Path Traversal (~30 payloads)
```

**Principio de Responsabilidad Única aplicado:**
- `intruder.py` solo sabe enviar peticiones HTTP y reportar resultados.
- `intruder_tab.py` solo sabe mostrar datos y reaccionar a eventos de usuario.
- Los payloads son archivos de texto plano completamente independientes.

---

## El Marcador de Inyección `§`

El Intruder usa el símbolo `§` (sección) para delimitar los puntos de inyección,
exactamente igual que Burp Suite.

```
GET /search?q=§test§ HTTP/1.1
Host: example.com
```

En cada iteración del ataque, el texto entre `§…§` se sustituye por un payload:

| Iteración | Payload | Petición resultante |
|---|---|---|
| 1 | `' OR 1=1--` | `GET /search?q=' OR 1=1-- HTTP/1.1` |
| 2 | `<script>alert(1)</script>` | `GET /search?q=<script>alert(1)</script> HTTP/1.1` |
| 3 | `../etc/passwd` | `GET /search?q=../etc/passwd HTTP/1.1` |

**Puedes tener múltiples marcadores** en el mismo template:
```
POST /login HTTP/1.1
Host: example.com
Content-Type: application/x-www-form-urlencoded

user=§admin§&pass=§password§
```

---

## Interfaz Gráfica

### Layout de la pestaña

```
┌─────────────────────────────────────────────────────────────────┐
│  💥 Attack │ ⏹ Stop │ Hilos: [5] │ Timeout: [10] │      Estado │
├──────────────────────────────┬──────────────────────────────────┤
│  📝 Template                 │  🎯 Payloads                     │
│                              │  ┌──────────────────────────┐   │
│  GET /search?q=§test§ ...   │  │ 🗄 Cargar SQLi            │   │
│  Host: example.com           │  │ 🌐 Cargar XSS             │   │
│                              │  │ 📂 Cargar Traversal       │   │
│                              │  │ 📁 Archivo personalizado… │   │
│                              │  └──────────────────────────┘   │
│                              │  Vista previa: 40 cargados       │
│           [Añadir §§]        │  '                               │
│                              │  ''                              │
│                              │  ' OR 1=1--                      │
├──────────────────────────────┴──────────────────────────────────┤
│  📊 Resultados               │ 💾 Export CSV │ 🗑 Limpiar       │
│  #  │ Payload          │ Status │ Length │ ms                   │
│  1  │ '                │  200   │  4532  │ 143                  │
│  2  │ ' OR 1=1--       │  500   │  312   │ 89   ← 🔴 rojo      │
│  3  │ <script>…        │  200   │  4532  │ 137                  │
└─────────────────────────────────────────────────────────────────┘
```

### Coloreado de la tabla de resultados

| Color | Código HTTP | Significado |
|---|---|---|
| 🟢 Verde | 2xx | Respuesta exitosa |
| 🔵 Azul | 3xx | Redirección |
| 🟡 Amarillo | 4xx | Error del cliente |
| 🔴 Rojo | 5xx | **Error del servidor → posible vulnerabilidad** |
| ⬜ Gris | ERR | Error de red o timeout |

> **Tip:** Un código `500` ante ciertos payloads SQLi es un fuerte indicador de vulnerabilidad de inyección SQL.

---

## Uso paso a paso

### 1. Preparar el template

Pega la petición HTTP que quieres atacar en el editor de **Template**:

```http
GET /products?category=§electronics§ HTTP/1.1
Host: vulnerable-site.com
User-Agent: Mozilla/5.0
Connection: close
```

Usa el botón **Añadir §§** para envolver automáticamente el texto seleccionado
con los marcadores de inyección.

### 2. Cargar payloads

Haz clic en uno de los botones de la sección Payloads:

- **Cargar SQLi** → carga `payloads/sqli.txt` (~40 vectores SQL Injection)
- **Cargar XSS** → carga `payloads/xss.txt` (~25 vectores XSS)
- **Cargar Traversal** → carga `payloads/traversal.txt` (~30 vectores Path Traversal)
- **Archivo personalizado…** → abre cualquier `.txt` con un payload por línea

### 3. Configurar el ataque

- **Hilos:** número de peticiones concurrentes (1-20). Recomendado: 5-10.
- **Timeout:** segundos máximos de espera por petición (1-120s). Recomendado: 10s.

### 4. Iniciar el ataque

Pulsa **💥 Attack**. La tabla de resultados se irá poblando en tiempo real.
La GUI **no se congela** — el ataque corre en un hilo daemon.

Para cancelar en cualquier momento: **⏹ Stop**.

### 5. Analizar resultados

Ordena la tabla por la columna **Status** o **Length**:
- Busca códigos `500` → posible SQLi.
- Busca variaciones en la columna `Length` → respuestas anómalas.
- Exporta con **💾 Export CSV** para análisis externo (Excel, pandas, etc.).

---

## Formato del archivo de payloads `.txt`

```
# Esto es un comentario (se ignora)
# Las líneas vacías también se ignoran

' OR 1=1--
' OR '1'='1
admin'--
```

- Una línea = un payload.
- Las líneas que empiezan con `#` son comentarios y se ignoran.
- Encoding: UTF-8.

---

## API de la clase `Intruder` (uso programático)

```python
from intruder import Intruder

intruder = Intruder()

# CU-09: Cargar payloads desde archivo
payloads = intruder.load_payloads("payloads/sqli.txt")

# CU-08: Definir template con punto de inyección
template = "GET /search?q=§test§ HTTP/1.1\nHost: example.com\n\n"
intruder.set_template(template)

# CU-10: Ejecutar ataque (bloqueante, llamar desde un hilo)
def on_result(result):
    print(f"[{result.index}] {result.payload!r:30} → {result.status_code} ({result.length}B)")

intruder.run(payloads=payloads, on_result=on_result, threads=5, timeout=10)
```

### Clase `IntruderResult`

| Atributo | Tipo | Descripción |
|---|---|---|
| `index` | `int` | Número de orden del intento (1-based) |
| `payload` | `str` | Payload utilizado |
| `status_code` | `int` | Código HTTP de la respuesta (0 si error de red) |
| `length` | `int` | Tamaño del cuerpo de respuesta en bytes |
| `duration_ms` | `float` | Tiempo de ida y vuelta en milisegundos |
| `error` | `str \| None` | Mensaje de error si la petición falló, else `None` |
| `success` | `bool` | `True` si no hubo error de red |

---

## Threading: ¿cómo funciona el ataque concurrente?

```
[IntruderTab._on_attack()]
    │  Lanza Thread daemon "IntruderAttack"
    ▼
[Intruder.run()]                ← corre fuera del hilo de la GUI
    │  Para cada payload:
    │    Semaphore.acquire()    ← limita la concurrencia a N hilos
    │    Thread("IntruderWorker-N").start()
    │        │
    │        ├─ _send_one()    ← sustituye §§, envía petición HTTP
    │        │      └─ on_result(IntruderResult)
    │        │           └─ widget.after(0, callback)  ← publica al hilo GUI
    │        └─ Semaphore.release()
    │
    └─ t.join() para todos los workers
           └─ widget.after(0, _on_attack_done)
```

El `threading.Semaphore(threads)` garantiza que nunca haya más de N peticiones
en vuelo simultáneamente, evitando saturar el servidor o la red local.

---

## Consideraciones de seguridad y ética

> ⚠️ **IMPORTANTE:** Esta herramienta está diseñada **exclusivamente para fines educativos**
> y para pruebas en entornos autorizados (laboratorios, CTFs, servidores propios).
> Usar esta herramienta contra sistemas sin autorización explícita puede ser ilegal
> y está estrictamente prohibido.

Entornos de práctica recomendados:
- [DVWA (Damn Vulnerable Web Application)](https://github.com/digininja/DVWA)
- [WebGoat (OWASP)](https://github.com/WebGoat/WebGoat)
- [HackTheBox](https://www.hackthebox.com/) / [TryHackMe](https://tryhackme.com/)
- [http://httpbin.org](http://httpbin.org) para pruebas de conectividad sin vulnerabilidades

---

## Archivos del módulo

| Archivo | Líneas aprox. | Responsabilidad |
|---|---|---|
| `intruder.py` | ~290 | Motor de fuzzing (lógica pura) |
| `gui/intruder_tab.py` | ~380 | Interfaz gráfica CustomTkinter |
| `payloads/sqli.txt` | ~45 | Diccionario SQL Injection |
| `payloads/xss.txt` | ~35 | Diccionario XSS |
| `payloads/traversal.txt` | ~40 | Diccionario Path Traversal |
| `MODULO_INTRUDER.md` | — | Esta documentación |
