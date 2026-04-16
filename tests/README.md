# Carpeta de Tests — Mini-Burp Suite

Esta carpeta contiene todos los tests unitarios e de integración del proyecto.

## Convención de nombres

| Tipo de test | Nombre del archivo | Ejemplo |
|---|---|---|
| Unitario por módulo | `test_<modulo>.py` | `test_history.py` |
| Integración entre módulos | `test_integration_<flujo>.py` | `test_integration_proxy_history.py` |

## Cómo ejecutar

```bash
# Todos los tests
python -m pytest tests/ -v

# Un archivo específico
python -m pytest tests/test_history.py -v

# Con reporte de cobertura (requiere pytest-cov)
python -m pytest tests/ --cov=proxy --cov-report=term-missing
```

## Tests actuales

| Archivo | Módulo que prueba | Tests |
|---|---|---|
| *(pendiente mover desde raíz)* | `proxy_server.py` + `history.py` | 39 |
