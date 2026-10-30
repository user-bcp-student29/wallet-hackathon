# Design

## Context

El repositorio no tenía antes ninguna integración de wallet, proveedor ni
ledger; todo se construye desde cero como datos sintéticos en memoria dentro
de un único proceso Python (ver `proposal.md` para la motivación). La API
base usa solo la biblioteca estándar; LangGraph, CrewAI y MCP requieren
Python 3.10–3.13, mientras que el servidor base puede ejecutarse en Python
3.14.

## Goals / Non-Goals

**Goals:**
- Mantener la API base (`wallet-reconciliation`) ejecutable sin ninguna
  dependencia de terceros.
- Aislar las dependencias de IA (`reconciliation-readonly-agent`) en un
  entorno Python separado para no forzar una versión de Python sobre todo el
  proyecto.
- Garantizar que la capacidad de revisión humana (`reconciliation-human-review`)
  sea la única con persistencia real entre reinicios del proceso.

**Non-Goals:**
- No se implementa autenticación de revisor ni identidad de producción.
- No se conecta ninguna wallet, proveedor o ledger real.
- No se agrega corrección automática de diferencias ni movimiento de dinero.

## Decisions

- **Entorno Python aislado (`.venv-ai`) para LangGraph/CrewAI/MCP**: en lugar
  de requerir Python 3.13 para todo el proyecto, el servidor base sigue
  funcionando con cualquier Python 3.10+ y solo quien quiera el análisis de
  IA crea `.venv-ai`. Alternativa descartada: forzar Python 3.13 en todo el
  proyecto, lo que habría bloqueado la ejecución del núcleo determinista en
  entornos con Python más nuevo.
- **CrewAI opt-in vía variables de entorno (`ENABLE_CREWAI`, `CREWAI_MODEL`)**:
  evita invocar un modelo de pago por defecto y mantiene el análisis
  determinista como camino principal. Alternativa descartada: activarlo
  automáticamente si la librería está instalada, lo que llamaría a un modelo
  sin que el operador lo decida explícitamente.
- **Despachador de herramientas con lista cerrada y sin argumentos**: las
  cuatro herramientas de lectura no reciben parámetros, eliminando por
  construcción la posibilidad de inyectar una ruta de archivo o un payload de
  control. Alternativa descartada: herramientas parametrizadas con
  validación en tiempo de ejecución, que exigiría mantener una superficie de
  validación más amplia para el mismo beneficio.
- **MCP como proceso stdio separado que llama a la API HTTP en loopback**: el
  servidor MCP no comparte memoria con la API; solo hace `GET` contra
  `127.0.0.1`. Esto mantiene la API como única fuente de verdad y evita que
  el proceso MCP necesite su propia copia del estado del grupo W6.
- **Revisión humana en SQLite append-only, separada del estado en memoria**:
  la decisión humana es un hecho de auditoría independiente del ciclo de vida
  de la incidencia; guardarla aparte asegura que sobreviva a un reinicio
  aunque la incidencia (en memoria) se reinicie a su estado semilla.
  Alternativa descartada: guardar la revisión junto con la incidencia en
  memoria, lo que habría perdido el historial en cada reinicio.
- **Namespace aleatorio de 8 hex en los IDs de incidencia
  (`INC-<namespace>-NNNN`)**: cada arranque del proceso genera un namespace
  nuevo, así una revisión guardada antes de un reinicio no puede asociarse
  por error a una incidencia distinta que reutilice el mismo número
  secuencial tras el reinicio.

## Risks / Trade-offs

- [Reinicio del servidor pierde wallet/proveedor/ledger/incidencias] →
  Mitigación: documentado explícitamente en `README.md`; aceptable porque el
  MVP es una demo local, no producción.
- [Entorno `.venv-ai` ausente] → Mitigación: `GET /agent/analysis` responde
  `503` con guía de instalación en lugar de fallar de forma opaca.
- [Etiqueta de revisor no autenticada podría malinterpretarse como
  identidad real] → Mitigación: el texto de la UI y de la API aclara que es
  declarativa; queda como tarea pendiente para cualquier despliegue real.
- [CrewAI mal configurado (variable activada sin modelo)] → Mitigación: el
  endpoint responde `503` en vez de intentar una llamada que fallaría sin
  contexto claro para el operador.

## Migration Plan

No aplica: es la primera versión de estas capacidades en el repositorio: no
hay datos ni comportamiento previo que migrar. El despliegue consiste en
ejecutar `python app.py` (núcleo) y, opcionalmente, instalar
`requirements-ai.txt` en `.venv-ai` para habilitar el agente y MCP.
