# Contratos de herramientas gobernadas

El flujo de análisis W6 con LangGraph conecta las primeras cuatro herramientas
de la tabla con el grupo sintético en memoria. Los contratos orientados a
fixtures que aparecen después en la tabla siguen planificados y no se exponen a
través del runtime W6.

Toda herramienta es de solo lectura. Las entradas nunca eligen una ruta
arbitraria del sistema de archivos. Los posibles fallos son explícitos y no
deben convertirse en resultados vacíos exitosos.

| Nombre | Propósito | Entrada | Salida | Validaciones | Errores posibles |
|---|---|---|---|---|---|
| `get_wallet_payments` | Leer pagos sintéticos de la wallet | Sin entrada | IDs, montos y estados de pagos | Devuelve copias bajo el lock del grupo | Error de runtime |
| `get_settlements` | Leer el reporte simulado del proveedor | Sin entrada | IDs, montos y estados de liquidación | Incluye los controles configurados del proveedor | Error de runtime |
| `get_ledger` | Leer filas del ledger de partida doble | Sin entrada | IDs, operaciones, cuentas y montos del ledger | Devuelve copias bajo el lock del grupo | Error de runtime |
| `get_reconciliation_incidents` | Leer los últimos estados de incidencias | Sin entrada | IDs, motivos y estados de incidencias | No recalcula el estado de las incidencias | Error de runtime |
| `load_wallet_transactions` | Cargar la fuente de wallet | Sin entrada | Registros de wallet normalizados | `fixtures/wallet_transactions.json` fijo; límites de bytes/registros/esquema | `InputValidationError`, `OSError` |
| `load_provider_transactions` | Cargar el mock del proveedor | Sin entrada | Registros del proveedor normalizados | `fixtures/provider_transactions.json` fijo; límites de bytes/registros/esquema | `InputValidationError`, `OSError` |
| `load_ledger_entries` | Cargar la fuente contable | Sin entrada | Asientos del ledger normalizados con signo | `fixtures/ledger_entries.json` fijo; verificaciones de cuenta con signo y esquema | `InputValidationError`, `OSError` |
| `find_transaction` | Inspeccionar el resultado de una ejecución | `run_id`, `transaction_id` | Resultado de conciliación coincidente o `None` | Los IDs son exactos; la búsqueda es de solo lectura | Ejecución desconocida |
| `validate_amounts` | Validar campos de dinero | Registros normalizados | Resultado de validación | Unidades menores enteras, rango admitido, moneda | `InputValidationError` |
| `validate_status` | Validar campos de estado | Registros normalizados | Resultado de validación | Lista permitida de estados | `InputValidationError` |
| `detect_duplicates` | Encontrar IDs de operación repetidos | Una lista de registros de una fuente | IDs duplicados y conteos | No elige un duplicado ganador | `InputValidationError` |
| `generate_reconciliation_report` | Producir un reporte determinista | ID de ejecución existente | Resumen/resultados de la ejecución | Lee solo la ejecución almacenada | Ejecución desconocida, error de E/S de salida |

Las capacidades prohibidas incluyen `execute_payment`, `approve_payment`,
`reverse_payment`, `modify_balance`, `modify_ledger` y `delete_transaction`.
Estas herramientas deben fallar de forma cerrada aunque las solicite un agente
o un usuario.

El despachador de herramientas de LangGraph acepta solo los cuatro nombres W6
conectados y rechaza todo argumento, por lo que los llamadores no pueden pasar
rutas ni payloads de control. El flujo no llama a `POST /reconciliations`;
reporta el último snapshot de incidencias e indica a los operadores que
concilien explícitamente cuando necesiten estados de incidencia actualizados.

El servidor MCP por stdio expone esas mismas cuatro herramientas y solo
redirige solicitudes `GET` fijas a `127.0.0.1`. Requiere que la API W6 local
esté en ejecución y no expone creación de pagos, controles de liquidación,
conciliación ni operaciones de escritura de revisión humana.

CrewAI está deshabilitado salvo que `ENABLE_CREWAI=true` y `CREWAI_MODEL` estén
ambos configurados. Cuando se activa, su agente no tiene herramientas y recibe
solo conteos agregados y códigos de motivo de las incidencias. La recomendación
se verifica contra la lista permitida determinista antes de volver al
llamador. Por defecto no se invoca ningún modelo.

La revisión humana es un flujo de operador solo por HTTP y deliberadamente no se
expone a agentes ni a MCP. Cada decisión de solo agregado registra la etiqueta
del revisor, `CONFIRM_FINDING` o `DISPUTE_FINDING`, el motivo, la identidad de
la incidencia y la marca de tiempo UTC. Las etiquetas de revisor no están
autenticadas en esta demo local.
