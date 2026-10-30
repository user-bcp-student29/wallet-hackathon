# Especificación de conciliación W6

## Registro común de transacción

Cada registro normalizado tiene `transaction_id`, `idempotency_key`, `source`,
`external_reference`, `amount_minor`, `currency`, `status` y `created_at`.
`amount_minor` es un entero no negativo, nunca un decimal. La fuente es una de
`wallet`, `provider` o `ledger`. Las monedas admitidas son códigos de tres
letras en mayúsculas tipo ISO; el grupo sintético proporcionado usa PEN.

Los registros de wallet y proveedor representan una operación. Los registros
del ledger representan movimientos de cuenta con signo asociados a una
transacción: un débito de wallet es negativo y su crédito de clearing
correspondiente es positivo. El movimiento absoluto de wallet se compara con el
monto de la transacción de wallet. Los registros de transacción duplicados en
wallet o proveedor se clasifican como `DUPLICATE` e impiden la coincidencia. Se
esperan varios asientos del ledger.

## Estados de conciliación

- `MATCHED`: existen las tres fuentes, estados y montos coinciden y no hay
  duplicados.
- `PENDING_REVIEW`: la wallet o el proveedor reporta una operación pendiente o
  con timeout; no se infiere un resultado final.
- `DIFFERENCE`: una o más fuentes discrepan o faltan.
- `HUMAN_REVIEW_REQUIRED`: una discrepancia crítica, como un pago rechazado con
  movimiento en el ledger o un timeout sin resolver, necesita atención del
  operador.
- `BLOCKED`: la entrada requerida es inválida o no pasa un guardrail de
  entrada.

Los tipos de diferencia incluyen `MISSING_IN_PROVIDER`, `MISSING_IN_WALLET`,
`MISSING_IN_LEDGER`, `AMOUNT_MISMATCH`, `STATUS_MISMATCH`, `DUPLICATE`,
`PENDING`, `TIMEOUT` y `DECLINED`. Un resultado incluye estados y montos de las
fuentes, severidad, siguiente acción recomendada no financiera y el indicador
`requires_human_review`.

## API

- `GET /settlements`: devuelve todas las filas simuladas del proveedor con
  `id`, `amount` y `status`.
- `GET /ledger`: devuelve las filas de partida doble del grupo con `id`,
  `operation`, `kind`, `account` y `amount`.
- `GET /reconciliations/incidents`: devuelve las incidencias `OPEN` y
  `RESOLVED` conocidas con `id`, `payment_id`, `reason` y `status`.
- `POST /reconciliations`: compara el grupo completo de wallet en memoria, el
  reporte del proveedor, el ledger y el saldo calculado de la wallet. No
  requiere cuerpo. Devuelve solo `status` y `differences`; devuelve `MATCHED`
  con una lista vacía o `DIFFERENCES` con las incidencias abiertas actuales.
  Las ejecuciones repetidas conservan los IDs de incidencia y solo este
  endpoint recalcula el estado de las incidencias.
- `POST /control/settlements`: simula localmente las alteraciones del reporte
  del proveedor `AMOUNT`, `MISSING`, `DUPLICATE`, `ORPHAN`,
  `CALLBACK_UNDELIVERED` y `CLEAR`. Este endpoint no debe cambiar el estado de
  la wallet ni del ledger.
- `POST /payments` y `POST /payments/{payment_id}/confirm`: ayudas locales W2
  para crear y confirmar un pago sintético antes de conciliar. La confirmación
  solo actualiza datos sintéticos en memoria de wallet/proveedor/ledger y es
  idempotente.
- `POST /reconciliation/runs`: valida, carga los tres fixtures locales
  acotados, normaliza, concilia y devuelve una ejecución.
- `GET /reconciliation/runs`: lista las ejecuciones del proceso actual.
- `GET /reconciliation/runs/{run_id}`: obtiene el resumen y los resultados de
  una ejecución.
- `GET /reconciliation/runs/{run_id}/differences`: obtiene sus resultados que no
  coinciden.
- `GET /reconciliation/runs/{run_id}/evidence`: obtiene hashes de entrada
  reproducibles, metadatos de la ejecución y resultados.

Todas las respuestas son JSON. Los payloads inválidos devuelven 400, los
cuerpos demasiado grandes devuelven 413 y las solicitudes de conciliación por
encima del límite local devuelven 429. Los IDs de ejecución desconocidos
devuelven 404. Solo las ayudas sintéticas W2 actualizan el estado de
wallet/ledger; los controles de liquidación cambian solo los datos de prueba
del proveedor y la conciliación en sí es de solo lectura. OpenAPI se publica en
`/openapi.json`.

## Seguridad y reproducibilidad

El resultado y las clasificaciones de la conciliación son deterministas. Los
agentes de IA, cuando se introduzcan, pueden explicar los hallazgos
deterministas pero no pueden alterar entradas, saldos ni ledger. Las ejecuciones
identifican los hashes de sus fixtures y la hora de creación en UTC. Las
fuentes inválidas fallan de forma cerrada y exponen un error explícito.
