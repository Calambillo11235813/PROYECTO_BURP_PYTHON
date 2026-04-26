🤖 Módulo E — Local AI Intelligence (Ollama Integration)
Estado: 🛠️ En Planificación / Investigación

Motor: Ollama (Llama 3 / Phi-3) local API

### CU-13 · Copiloto de Evasión de WAF (Módulo B - Repeater)
Asistente inteligente para transformar payloads detectados por firewalls.

Descripción: Cuando una petición en el Repeater recibe un código de bloqueo (403 Forbidden o similar), el usuario puede solicitar una "Sugerencia de Bypass".

Lógica de IA: Se envía al modelo local el par Request/Response junto con el payload bloqueado. La IA analiza si el bloqueo es por firmas de texto, codificación o cabeceras mal formadas.

Salida: Sugerencias de mutación (ej. Double URL encoding, cambio de User-Agent, o uso de caracteres equivalentes en Unicode).

### |CU-14 · Generación Dinámica de Payloads (Módulo C - Intruder)
Creación de vectores de ataque basados en el contexto del punto de inyección.

Descripción: En lugar de usar listas estáticas, el Intruder utiliza la IA para generar payloads personalizados para el campo marcado con §.

Lógica de IA: La IA identifica si el marcador está dentro de un JSON, un parámetro de URL o un Header. Si detecta que el parámetro se llama id, generará payloads de SQLi numéricos; si se llama redirect, se enfocará en Open Redirect y SSRF.

Salida: Un diccionario temporal de 10-20 payloads de alta probabilidad de éxito, reduciendo el ruido en el servidor objetivo.

### CU-15 · Detección de Anomalías Lógicas e IDOR (Módulo A - Proxy)
Identificación heurística de fallos de control de acceso en el tráfico pasivo.

Descripción: La IA analiza el History (CU-03) buscando patrones de comportamiento que el escáner estático ignora.

Lógica de IA: Compara diferentes peticiones a un mismo endpoint (ej. /api/v1/user/101 y /api/v1/user/102). Si detecta que al cambiar el ID el servidor responde con datos sensibles sin una cookie de sesión robusta, marca la petición como "Sospecha de IDOR".

Salida: Alerta visual en la tabla del historial con una etiqueta de "Anomalía de Lógica"