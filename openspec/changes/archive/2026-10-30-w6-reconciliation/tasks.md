# Tasks

## 1. Motor determinista de conciliación (`wallet-reconciliation`)

- [x] 1.1 Implementar `W6PaymentGroup` con pagos, liquidaciones y ledger en
  memoria, y verificar con `tests/test_w6_contract.py`
- [x] 1.2 Exponer `GET /settlements`, `GET /ledger`,
  `GET /reconciliations/incidents` y `POST /reconciliations` en `app.py`, y
  verificar que `POST /reconciliations` sin alteraciones devuelve
  `{"status":"MATCHED","differences":[]}`
- [x] 1.3 Implementar `POST /control/settlements` con los modos `AMOUNT`,
  `MISSING`, `DUPLICATE`, `ORPHAN`, `CALLBACK_UNDELIVERED` y `CLEAR`, y
  verificar que cada modo solo altera `GET /settlements`
- [x] 1.4 Conservar la identidad de incidencias por pago/motivo entre
  ejecuciones y resolverlas solo tras una conciliación posterior, verificado
  por las pruebas de ciclo de vida de monto y callback en
  `tests/test_w6_contract.py`
- [x] 1.5 Implementar las ayudas W2 `POST /payments` y
  `POST /payments/{payment_id}/confirm` con escritura de ledger idempotente,
  y verificar con las pruebas de pago W2
- [x] 1.6 Aplicar límites de tamaño (`413`) y de tasa (`429`, 60
  solicitudes/minuto) sobre `POST /reconciliations`, y verificar con las
  pruebas de guardrails en `tests/test_api.py`

## 2. Agente de solo lectura y MCP (`reconciliation-readonly-agent`)

- [x] 2.1 Implementar las cuatro herramientas de solo lectura sin argumentos
  en `src/reconciliation/agent_tools.py` y su despachador con lista cerrada,
  verificado por `tests/test_agent_workflow.py`
- [x] 2.2 Orquestar el flujo de tres nodos con LangGraph en
  `src/reconciliation/agent_workflow.py` y exponerlo en
  `GET /agent/analysis`, verificando que el estado de las incidencias no
  cambia antes/después de la llamada
- [x] 2.3 Agregar el analista CrewAI opt-in (`ENABLE_CREWAI`,
  `CREWAI_MODEL`) sin herramientas, validando su recomendación contra una
  lista permitida, y verificar que por defecto reporta `crewai_status:
  "DISABLED"`
- [x] 2.4 Documentar y aislar las dependencias de IA en un entorno Python
  3.13 (`.venv-ai`, `requirements-ai.txt`), y verificar que
  `.\.venv-ai\Scripts\python.exe -m unittest discover -s tests -v` pasa sin
  omisiones
- [x] 2.5 Implementar `mcp_server.py` con las mismas cuatro consultas de
  lectura contra la API W6 en loopback, sin herramientas de escritura, y
  verificar con `tests/test_mcp_server.py` (incluye transporte MCP real)

## 3. Revisión humana persistente (`reconciliation-human-review`)

- [x] 3.1 Implementar `HumanReviewStore` en
  `src/reconciliation/human_reviews.py` con SQLite append-only y
  validaciones de `decision`/`rationale`, verificado por pruebas unitarias
  del almacén
- [x] 3.2 Exponer `POST /reconciliations/incidents/{incident_id}/reviews`
  (solo para incidencias `OPEN`, `409` en caso contrario) y
  `GET /reconciliation/reviews` en `app.py`, verificado con
  `tests/test_api.py`
- [x] 3.3 Agregar un namespace aleatorio a los IDs de incidencia para que una
  revisión no se asocie a otra incidencia tras un reinicio, verificado por
  prueba de identidad de incidencia entre reinicios
- [x] 3.4 Agregar la cola de revisión y el historial de decisiones al
  dashboard (`index.html`), verificado manualmente ejecutando el flujo
  completo en el navegador

## Workflow follow-up

- Archivar este change con `openspec archive w6-reconciliation` para que
  estas tres capacidades queden en `openspec/specs/`.
- Verificar tras el archivo con `openspec list --specs` y
  `openspec validate --strict`.
