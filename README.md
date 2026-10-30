# Wallet Hackathon · Conciliación W6

MVP local del flujo W6: compara una wallet sintética, el reporte de
liquidación del proveedor y el ledger de partida doble. La conciliación es
determinista y no mueve dinero ni repara diferencias automáticamente.

## Ejecución local

Requiere Python 3.10+ y no usa paquetes de terceros.

```powershell
python app.py
```

Abre <http://127.0.0.1:8000>. Opcional:

```powershell
$env:PORT = "8010"
python app.py
```

El grupo inicia con un pago W2 local confirmado `PAY-1500` por S/ 15.00. El
dashboard puede crear y confirmar otro pago simulado, aplicar controles al
reporte del proveedor, conciliar e inspeccionar incidencias, liquidaciones y
asientos del ledger. La API W6 funciona sin dependencias de terceros.

## Flujo de agente opcional de solo lectura

El endpoint de análisis local usa LangGraph para recolectar un snapshot W6 con
cuatro herramientas de solo lectura permitidas y validar su recomendación. No
concilia, no resuelve incidencias ni cambia datos de wallet, liquidación o
ledger. CrewAI está deshabilitado salvo que se active explícitamente; por
defecto no se llama a ningún modelo.

CrewAI y LangGraph requieren Python 3.13 en este entorno opcional. Crea un
entorno aislado para que el servidor W6 base pueda seguir usando otra
instalación de Python:

```powershell
py -3.13 -m venv .venv-ai
.\.venv-ai\Scripts\python.exe -m pip install -r requirements-ai.txt
.\.venv-ai\Scripts\python.exe app.py
```

Luego abre `http://127.0.0.1:8000` y elige **Analizar snapshot (solo
lectura)**, o llama a `GET /agent/analysis`. Si LangGraph no está instalado en
el intérprete activo, el endpoint responde `503` con una guía de instalación.

Para activar CrewAI, define explícitamente `ENABLE_CREWAI=true` y
`CREWAI_MODEL` en el entorno del servidor y configura allí las credenciales del
proveedor elegido. El crew no tiene herramientas y solo recibe conteos
agregados y códigos de motivo de incidencias; no puede ejecutar pagos ni
modificar registros. Su salida debe coincidir exactamente con una
recomendación permitida o se rechaza. No actives un modelo en la nube salvo que
enviar ese resumen sintético sea aceptable.

Ejecuta todas las pruebas con IA habilitada:

```powershell
.\.venv-ai\Scripts\python.exe -m unittest discover -s tests -v
```

### MCP y revisión humana persistente

El servidor MCP local usa stdio y expone solo `get_wallet_payments`,
`get_settlements`, `get_ledger` y `get_reconciliation_incidents`. Lee la API W6
en ejecución en `127.0.0.1`; inicia la API primero. La configuración para VS
Code está en `.vscode/mcp.json`. Para ejecutarlo manualmente desde una segunda
terminal:

```powershell
.\.venv-ai\Scripts\python.exe mcp_server.py
```

Si usas un puerto distinto, define `$env:W6_API_PORT` con ese puerto antes de
iniciar el proceso MCP. MCP no expone herramientas para crear pagos, controles
del proveedor, conciliación ni escritura de revisiones.

Abre una incidencia en el dashboard e ingresa una etiqueta de revisor y un
motivo. **Confirmar hallazgo** y **Discrepar del hallazgo** agregan una decisión
a `artifacts/human_reviews.sqlite3`; el historial sobrevive a los reinicios.
Las decisiones son solo registros de auditoría y nunca aprueban, reversan ni
ejecutan pagos. La etiqueta del revisor no está autenticada en esta demo local,
por lo que no es un mecanismo de identidad ni autorización de producción. Las
incidencias usan IDs únicos por proceso para que un servidor nuevo no herede
por error la revisión de una ejecución anterior.

## Contrato de la API W6

OpenAPI se sirve en `/openapi.json`.

| Método y ruta | Contrato |
|---|---|
| `GET /wallet/payments` | Arreglo JSON de los pagos sintéticos actuales de la wallet. Lo usan el agente de solo lectura y el servidor MCP. |
| `GET /ledger` | Arreglo JSON de `id`, `operation`, `kind`, `account`, `amount`. Incluye dos asientos `FUNDING` iniciales y las filas de débito/crédito del pago inicial. |
| `GET /settlements` | Arreglo JSON de filas del proveedor: `id`, `amount`, `status`. Incluye estados pendiente, confirmado, rechazado o reversado según el grupo. |
| `GET /reconciliations/incidents` | Arreglo JSON de `id`, `payment_id`, `reason`, `status` para incidencias `OPEN` y `RESOLVED`. |
| `GET /reconciliation/reviews` | Historial local de decisiones humanas (solo se agrega), guardado en SQLite. |
| `POST /reconciliations/incidents/{incident_id}/reviews` | Registra `reviewer`, `decision` (`CONFIRM_FINDING` o `DISPUTE_FINDING`) y `rationale` obligatorio para una incidencia OPEN. |
| `GET /agent/analysis` | Ejecuta el flujo opcional de LangGraph de solo lectura; requiere el entorno de IA con Python 3.13. |
| `POST /reconciliations` | Sin cuerpo. Devuelve `{"status":"MATCHED","differences":[]}` o `DIFFERENCES` con las incidencias abiertas actuales. Solo este endpoint recalcula el estado de las incidencias. |
| `POST /control/settlements` | Aplica un control local al reporte del proveedor; nunca cambia la wallet ni el ledger. |
| `POST /payments` | Ayuda local W2: `{"amountCents":1500}` crea un pago sintético pendiente y su fila del proveedor. |
| `POST /payments/{payment_id}/confirm` | Ayuda local W2: confirma un pago pendiente y escribe sus filas de débito/crédito una sola vez. |

Controles del proveedor admitidos:

```json
{"paymentId":"PAY-1500","mode":"AMOUNT","amountCents":1600}
{"paymentId":"PAY-1500","mode":"MISSING"}
{"paymentId":"PAY-1500","mode":"DUPLICATE"}
{"paymentId":"PAY-ORPHAN","mode":"ORPHAN","amountCents":1600}
{"paymentId":"PAY-1501","mode":"CALLBACK_UNDELIVERED"}
{"paymentId":"PAY-1500","mode":"CLEAR"}
```

`CALLBACK_UNDELIVERED` requiere un pago pendiente en la wallet y simula un
resultado confirmado del proveedor cuyo callback no actualizó la wallet.
Confirma el pago mediante W2 y concilia de nuevo para resolver su incidencia de
estado. Las incidencias se identifican por pago/recurso y motivo: repetir la
conciliación no crea duplicados; al eliminar la causa, la incidencia original
pasa a `RESOLVED` y conserva su ID. Si la causa reaparece, la misma incidencia
se reabre.

Secuencia de demo de diferencia de monto:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/reconciliations -Method Post
Invoke-RestMethod -Uri http://127.0.0.1:8000/control/settlements -Method Post -ContentType 'application/json' -Body '{"paymentId":"PAY-1500","mode":"AMOUNT","amountCents":1600}'
Invoke-RestMethod -Uri http://127.0.0.1:8000/reconciliations -Method Post
Invoke-RestMethod -Uri http://127.0.0.1:8000/reconciliations/incidents
Invoke-RestMethod -Uri http://127.0.0.1:8000/control/settlements -Method Post -ContentType 'application/json' -Body '{"paymentId":"PAY-1500","mode":"CLEAR"}'
Invoke-RestMethod -Uri http://127.0.0.1:8000/reconciliations -Method Post
```

`POST /reconciliations` responde `200`, las entradas inválidas devuelven `400`,
los cuerpos de más de 16 KiB devuelven `413` y más de 60 solicitudes de
conciliación por minuto desde un mismo cliente local devuelven `429`. La
conciliación compara todos los pagos del grupo, las filas del proveedor, los
asientos del ledger y los saldos calculados de la wallet; nunca corrige una
diferencia.

## API de ejecuciones con fixtures

El primer corte vertical también ofrece una API reproducible sobre tres
archivos fixture sintéticos y acotados:

| Método y ruta | Resultado |
|---|---|
| `POST /reconciliation/runs` | Carga fixtures, normaliza, concilia y crea una ejecución con evidencia. Acepta sin cuerpo o `{}`. |
| `GET /reconciliation/runs` | Lista los resúmenes de ejecuciones en memoria. |
| `GET /reconciliation/runs/{run_id}` | Obtiene todos los resultados de una ejecución con fixtures. |
| `GET /reconciliation/runs/{run_id}/differences` | Obtiene los resultados que no coinciden. |
| `GET /reconciliation/runs/{run_id}/evidence` | Obtiene los hashes de los fixtures y los resultados. |

## Arquitectura y seguridad

```text
fixtures/*.json -> validación de entrada acotada -> TransactionRecord
               -> conciliación determinista -> API de ejecución/evidencia

Ayuda local de pagos W2 -> wallet + liquidación + ledger simulados
                        -> los controles W6 solo cambian el reporte de liquidación
                        -> POST /reconciliations solo actualiza incidencias
```

El dinero se guarda en unidades menores enteras (`S/ 15.50 = 1550`). Las rutas
de los fixtures son fijas; la API no acepta archivos elegidos por el llamador.
Esquemas inválidos, claves JSON duplicadas, decimales, estados inválidos,
monedas no admitidas, archivos demasiado grandes o valores con apariencia de
secreto fallan de forma explícita. La demo local escucha solo en `127.0.0.1`.

La conciliación detecta filas de liquidación ausentes o duplicadas, diferencias
de monto o estado, asientos del ledger faltantes, inesperados o mal formados, y
diferencias de saldo. El mismo pago/recurso + motivo conserva su ID de
incidencia entre ejecuciones. Solo una conciliación posterior puede pasar una
incidencia a `RESOLVED`.

No hay una wallet, proveedor ni ledger reales conectados. Los endpoints W2 de
crear/confirmar solo modifican datos sintéticos en memoria. Los controles
afectan únicamente el reporte del proveedor. La conciliación nunca cambia
saldos ni asientos del ledger.

## Ingeniería de IA, herramientas, MCP y HITL

LangGraph orquesta el flujo local de snapshot de solo lectura. CrewAI está
disponible como paso de análisis explícito y deshabilitado por defecto cuando
se configura un modelo. Un servidor MCP local por stdio expone solo
herramientas de lectura, y las decisiones humanas se agregan a un registro de
auditoría SQLite local. Como trabajo futuro: ampliar las pruebas adversariales
de guardrails, trazas/evaluación e integrar las superficies W1–W5.

Las decisiones de revisión humana se declaran con una etiqueta de revisor pero
no están autenticadas. Solo confirman o discrepan de hallazgos; no son
aprobaciones y nunca ejecutan un pago. Los roles, prompts, skills, guardrails y
contratos de herramientas se describen en
[`docs/ai-engineering.md`](docs/ai-engineering.md) y
[`docs/tools.md`](docs/tools.md). Skills:
[`normalización`](docs/skills/transaction-normalization.md),
[`conciliación`](docs/skills/transaction-reconciliation.md),
[`análisis de excepciones`](docs/skills/exception-analysis.md) y
[`evidencia`](docs/skills/evidence-generation.md).

## SDD, pruebas y evidencia

El proyecto usa [OpenSpec](https://github.com/Fission-AI/OpenSpec) para
especificar antes de implementar. Las especificaciones vigentes de las tres
capacidades (`wallet-reconciliation`, `reconciliation-readonly-agent`,
`reconciliation-human-review`) están en
[`openspec/specs/`](openspec/specs/); la propuesta, el diseño y las tareas de
su change original archivada están en
[`openspec/changes/archive/2026-10-30-w6-reconciliation/`](openspec/changes/archive/2026-10-30-w6-reconciliation/).
Verifica las especificaciones con `openspec validate --all --strict`.

```powershell
python -m unittest discover -s tests -v
python generate_evidence.py
```

Las pruebas cubren normalización/clasificación de fixtures, guardrails de
entrada y salida, herramientas de solo lectura y el flujo LangGraph, contratos
HTTP, identidad/resolución de incidencias, creación y confirmación de pagos W2,
y los escenarios de callback/monto/faltante/duplicado/huérfano.
[`evidence.md`](evidence.md) registra los últimos resultados y hashes de la
ejecución con fixtures; [`artifacts/`](artifacts/) contiene su evidencia en
formato legible por máquina. Los pasos de la demo están en
[`demo/demo_scenario.md`](demo/demo_scenario.md).

## Límites actuales

Los registros de ejecuciones con fixtures viven en memoria mientras dure el
proceso. Los archivos de evidencia son locales. La semilla del grupo W6 y el
mock W2 están en memoria y se reinician al apagar el servidor. En este
incremento no hay integración de producción, base de datos duradera de la
wallet, corrección automática, herramienta MCP de escritura ni identidad
autenticada de revisor de producción. La base SQLite persiste solo el registro
de auditoría de revisión humana; el estado de wallet, liquidación, ledger e
incidencias permanece en memoria.
