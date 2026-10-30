# Notas de ingeniería de IA y harness

## Corte vertical actual

El núcleo de conciliación sigue siendo determinista. Un entorno opcional con
Python 3.13 ejecuta un flujo LangGraph sobre el snapshot local W6. CrewAI solo
está disponible si se activa explícitamente con un modelo; está deshabilitado
por defecto, recibe conteos agregados y códigos de motivo, y no tiene
herramientas. El navegador solo muestra los resultados de la API y no decide
resultados financieros.

## Prompts y roles de agente

El runtime activo tiene un único rol opcional de CrewAI:

- **Analista de conciliación:** elegir un seguimiento permitido a partir de un
  snapshot agregado; sin herramientas, delegación ni acciones financieras.

Los demás roles planificados son personas de desarrollo y revisión, no agentes
de runtime:

- **Arquitecto de software:** contratos de dominio, arquitectura y revisión de
  seguridad.
- **Desarrollador backend:** validación de fixtures, normalización, API y motor.
- **Desarrollador frontend:** dashboard operativo con vista de resultados de
  solo lectura.
- **QA / Pruebas:** verificaciones deterministas unitarias, de API, de
  seguridad y de integración.
- **Líder de capítulo / Revisor:** revisión técnica con resultado `APPROVED`,
  `CHANGES_REQUIRED` o `HUMAN_REVIEW_REQUIRED`.
- **Analista de conciliación:** explicar los hallazgos del motor y recomendar
  solo seguimientos seguros; nunca cambiar saldos, ledger ni el estado de pagos.

Todo prompt de agente debe indicar su alcance, las herramientas de solo lectura
permitidas, las acciones prohibidas que mueven dinero, el esquema de salida y
las condiciones de escalamiento.

## Skills

Las reglas iniciales de normalización y conciliación se implementan como
funciones de Python, con contratos de skill reutilizables documentados en
[`skills/transaction-normalization.md`](skills/transaction-normalization.md)
y [`skills/transaction-reconciliation.md`](skills/transaction-reconciliation.md).
Los contratos de análisis de excepciones y generación de evidencia están en
[`skills/exception-analysis.md`](skills/exception-analysis.md) y
[`skills/evidence-generation.md`](skills/evidence-generation.md).

## Herramientas y MCP

El flujo LangGraph solo puede acceder a cuatro herramientas W6 sin argumentos:
`get_wallet_payments`, `get_settlements`, `get_ledger` y
`get_reconciliation_incidents`. El despachador rechaza otros nombres y todo
argumento, por lo que ninguna solicitud puede aportar una ruta de archivo ni un
payload de control de liquidación. Las ayudas de demo W2 y los controles de
liquidación no se exponen como herramientas del agente. El flujo no recalcula
los estados de las incidencias. Un servidor MCP local por stdio expone las
mismas cuatro consultas fijas de solo lectura llamando a la API W6 en loopback;
no tiene listener de red, herramienta de mutación ni credenciales de
producción.

## LangGraph y CrewAI

LangGraph ejecuta tres nodos acotados: recolectar fuentes de solo lectura,
analizar el snapshot y aplicar guardrails de salida. Sin configuración
explícita de CrewAI, el análisis es determinista y local. Cuando se activa con
`ENABLE_CREWAI=true` y `CREWAI_MODEL`, CrewAI recibe solo conteos agregados y
códigos de motivo; su recomendación debe coincidir exactamente con la lista
permitida. No tiene herramientas ni delegación. La aritmética de conciliación y
las transiciones de estado de las incidencias permanecen en la API W6
determinista.

## Guardrails

- **Entrada:** campos JSON estrictos, sintaxis del ID de transacción, dinero
  entero, moneda en mayúsculas, lista permitida de estados, marcas de tiempo
  UTC, rutas de fixtures fijas, límites de bytes/registros y escaneo de valores
  con apariencia de secreto.
- **Herramientas:** lista permitida de nombres de herramientas analíticas de
  solo lectura; bloqueo de acciones de pago, reverso, saldo, ledger y borrado.
- **Salida:** solo pasan recomendaciones seguras conocidas; el lenguaje de
  acciones financieras se bloquea y las recomendaciones desconocidas escalan.
- **Runtime:** hay límites de tamaño de solicitud y fixture, y un límite de
  solicitudes de conciliación por cliente. LangGraph tiene una ruta fija de tres
  nodos sin bucles. MCP no acepta argumentos de herramienta y solo llama a rutas
  GET fijas en loopback.

## Revisión humana

Los timeouts, asientos del ledger rechazados y registros duplicados del
proveedor pueden marcarse como que requieren revisión humana. Para las
incidencias W6 actualmente OPEN, el dashboard registra `CONFIRM_FINDING` o
`DISPUTE_FINDING` y un motivo obligatorio en un registro SQLite de solo
agregado. Los eventos de revisión sobreviven a los reinicios e incluyen marca
de tiempo, incidencia, etiqueta del revisor, decisión y motivo. La etiqueta del
revisor no está autenticada y las decisiones nunca ejecutan pagos ni cambian el
estado de la incidencia. Los IDs de incidencia únicos por proceso evitan que una
revisión se asocie a otra incidencia tras un reinicio.

## Harness y observabilidad

Cada ejecución tiene un ID único, marca de tiempo UTC, hashes SHA-256 de los
fixtures, resultados deterministas y evidencia JSON. El estado de la ejecución
es local al proceso. Los secretos no se configuran ni se registran. Las
decisiones humanas son duraderas en una base SQLite local; el estado financiero
y de incidencias permanece en memoria. Los siguientes cortes deberían agregar
tiempos por nodo/herramienta y eventos de decisión de guardrails sin registrar
payloads sensibles.

## SDD y decisiones

El proyecto usa OpenSpec para especificar antes de implementar. Las
especificaciones vigentes de W6 están en `openspec/specs/`
(`wallet-reconciliation`, `reconciliation-readonly-agent`,
`reconciliation-human-review`); la propuesta, el diseño y las tareas de la
change original archivada están en
`openspec/changes/archive/2026-10-30-w6-reconciliation/`. El primer corte
mantiene dependencias de la biblioteca estándar de Python, usa fixtures en
lugar de integraciones reales y aplaza deliberadamente las decisiones
autónomas de agentes hasta validar el núcleo determinista.
