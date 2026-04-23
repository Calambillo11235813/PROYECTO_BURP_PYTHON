Proyecto: Herramienta de Pruebas de Vulnerabilidades Web (NetLens)
Materia: Ingeniería de Software 2

Estudiantes: Diogo Nicolas Rodriguez Gomez, Javier Soliz Rueda

Stack Tecnológico: Python 3.x, CustomTkinter, Sockets, Threading.

1. Descripción del Proyecto
Este proyecto consiste en el desarrollo de una herramienta de escritorio para la auditoría de seguridad en aplicaciones web, inspirada en las funcionalidades núcleo de Burp Suite. La aplicación actúa como un Proxy HTTP Interceptor que permite capturar, analizar y modificar el tráfico entre un navegador y un servidor web en tiempo real.

El objetivo principal es proporcionar una plataforma extensible para la identificación de vulnerabilidades comunes como SQL Injection, Cross-Site Scripting (XSS) y Path Traversal, mediante técnicas de manipulación manual y automatizada (fuzzing).

2. Módulos y Casos de Uso

### Módulo A: Interceptor Proxy (Core)
Este módulo gestiona la capa de red y la captura de datos crudos.

CU-01: Configuración de Proxy: El usuario define la IP y el puerto local para la escucha de tráfico.

CU-02: Intercepción de Peticiones: Captura automática de peticiones salientes del navegador.

CU-03: Visualización de Historial (Logs): Registro tabular de todas las peticiones con sus códigos de respuesta.

CU-04: Modificación en Tiempo Real: Interrupción del tráfico para editar cabeceras o parámetros antes del envío.

### Módulo B: Repeater (Análisis Manual)
Permite la manipulación iterativa de peticiones específicas.
5.  CU-05: Clonación de Petición: Envío de una petición capturada al entorno de pruebas manuales.
6.  CU-06: Reenvío Manipulado: Edición libre de verbos HTTP, headers y cuerpo para pruebas de seguridad.
7.  CU-07: Comparativa de Respuestas: Análisis visual de las diferencias entre las respuestas del servidor ante distintos inputs.



### Módulo C: Intruder (Automatización/Fuzzing)
Automatiza la búsqueda de fallos mediante ataques de diccionario.
8.  CU-08: Definición de Puntos de Inyección: Selección de variables dentro de una petición para ser atacadas.
9.  CU-09: Gestión de Payloads: Carga de diccionarios de ataque (.txt) con vectores conocidos (SQLi, XSS).
10. CU-10: Ejecución de Ataque: Envío masivo y controlado de peticiones con registro de variaciones en la respuesta.

### Módulo D: Reporting & Analysis
CU-11: Detección Pasiva: Identificación de errores de servidor (500) o cabeceras inseguras de forma automática.

CU-12: Exportación de Resultados: Generación de un informe técnico con las vulnerabilidades potenciales halladas.


/PROYECTO_BURP_PYTHON
│
├── main.py                 # Punto de entrada (Inicia la UI y el Proxy)
├── proxy_core.py           # Lógica de Sockets y Multithreading (Módulo A)
├── repeater.py             # Lógica de reenvío manual (Módulo B)
├── intruder.py             # Motor de ataques y fuzzing (Módulo C)
│
├── /gui                    # Componentes de la Interfaz Gráfica
│   ├── app_ui.py           # Ventana principal (CustomTkinter)
│   ├── components.py       # Tablas, visores de texto y botones personalizados
│   └── themes.json         # Configuración visual (Dark Mode)
│
├── /logic                  # Capa de procesamiento
│   ├── parser.py           # Convierte bytes de red a objetos legibles
│   ├── scanner.py          # Lógica de detección de vulnerabilidades
│   └── utils.py            # Funciones auxiliares y formateo de datos
│
├── /payloads               # Diccionarios de ataque
│   ├── sqli.txt            # Payloads para SQL Injection
│   ├── xss.txt             # Payloads para Cross-Site Scripting
│   └── traversal.txt       # Payloads para Path Traversal
│
├── /reports                # Almacenamiento de informes generados
└── requirements.txt        # Librerías necesarias (customtkinter, requests, etc.)


🐍 Estándar de Codificación (Basado en PEP 8)
1. Nomenclatura (Naming Conventions)

Elemento,Estilo,Ejemplo
Clases,PascalCase,class ProxyServer:
Funciones,snake_case,def capture_request():
Variables,snake_case,"target_url = ""google.com"""
Constantes,SCREAMING_SNAKE,DEFAULT_PORT = 8080
Archivos/Módulos,snake_case,proxy_core.py

2. Estructura y Espaciado
Indentación: Siempre 4 espacios (no uses Tabs, aunque VS Code los suele convertir automáticamente).

Longitud de línea: Máximo 79-88 caracteres. Si es muy larga, divídela.

Líneas en blanco: * Dos líneas en blanco entre clases y funciones de nivel superior.

Una línea en blanco entre métodos dentro de una clase.

3. Importaciones
Deben estar al principio del archivo y ordenadas así:

Librerías estándar (ej. socket, threading).

Librerías de terceros (ej. customtkinter, requests).

Módulos locales propios del proyecto.

4. Comentarios y Documentación
Docstrings: Todas las clases y funciones públicas deben tener un docstring explicando qué hacen, sus parámetros y qué retornan.

Comentarios inline: Úsalos para explicar lógica compleja, no para repetir lo que el código ya dice.

Ejemplo de Docstring:

class ProxyServer:
    """
    Escucha conexiones entrantes y las redirige al servidor objetivo.
    
    Args:
        host (str): Dirección IP local para escuchar.
        port (int): Puerto local.
    """
    def __init__(self, host, port):
        self.host = host
        self.port = port

5. Manejo de Errores
No uses except: pass. Siempre especifica el tipo de error que esperas capturar (ej. except socket.error as e:).

Usa bloques try/except/finally para asegurar que los recursos (como las conexiones de red) se cierren correctamente.

6. Tamaño Máximo Recomendado por Archivo
Un archivo de código Python no debería superar las 400-500 líneas de código efectivo (sin contar líneas en blanco ni comentarios). Esta regla aplica para todos los módulos del proyecto.

Por qué es importante:
- Archivos largos son difíciles de leer, mantener y revisar en equipo.
- Un archivo que crece más de 500 líneas generalmente es señal de que tiene demasiadas responsabilidades (violación del Principio de Responsabilidad Única - SRP).
- Facilita la navegación en el editor y la búsqueda de errores durante debugging.

Guía práctica por tipo de archivo:

Tipo de archivo,Límite recomendado,Límite máximo absoluto
Módulo de lógica (proxy, history, etc.),200-300 líneas,500 líneas
Archivo de UI / Interfaz gráfica,300-400 líneas,600 líneas
Archivo de tests,Sin límite estricto,Separar en varios archivos si supera 600 líneas
Archivo de utilidades (utils.py),100-200 líneas,300 líneas
Punto de entrada (main.py),Máximo 50 líneas,100 líneas

Referencia: PEP 8 no establece un límite absoluto de líneas por archivo, pero la comunidad Python y herramientas como flake8 siguen la regla de mantener módulos pequeños y cohesivos.


3. Tipo de Aplicación — Herramienta de Escritorio Instalable
Mini-Burp Suite está diseñada como una aplicación de escritorio nativa para Windows, instalable directamente en el equipo del usuario sin necesidad de un navegador ni conexión a internet para funcionar.

Características de la distribución:
- La herramienta se empaqueta como un ejecutable (.exe) usando PyInstaller, lo que permite instalarla en el escritorio sin que el usuario final necesite tener Python instalado.
- Al ejecutarse, abre una ventana gráfica de escritorio (construida con CustomTkinter) que presenta la interfaz de intercepción, historial y análisis.
- No depende de servidores externos: toda la lógica corre localmente en la máquina del usuario.
- El proxy escucha en localhost (127.0.0.1), por lo que el navegador debe configurarse manualmente para apuntar a él.

Comando para generar el ejecutable (una vez finalizado el desarrollo):

pyinstaller --onefile --windowed --name MiniburpSuite main.py

Esto genera un archivo dist/MiniburpSuite.exe que puede copiarse al escritorio y ejecutarse directamente con doble clic.
