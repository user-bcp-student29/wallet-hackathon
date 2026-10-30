# Proposal

## Why

Operaciones necesita comprobar que la wallet, el reporte del proveedor y el
ledger contable registren operaciones consistentes para la billetera digital
de la hackatón. Sin esta capacidad, una diferencia de monto, estado o asiento
entre esas tres fuentes pasaría desapercibida y nadie sabría qué revisar.

## What Changes

- Motor determinista que compara pagos de wallet, filas de liquidación del
  proveedor y asientos del ledger, y clasifica cada diferencia con un motivo
  (`AMOUNT_MISMATCH`, `STATUS_MISMATCH`, `MISSING_SETTLEMENT`,
  `DUPLICATE_SETTLEMENT`, `ORPHAN_SETTLEMENT`, entre otros).
- API HTTP local (`/settlements`, `/ledger`, `/reconciliations`,
  `/reconciliations/incidents`, `/control/settlements`) y ayudas W2
  (`/payments`, `/payments/{id}/confirm`) para generar y conciliar pagos
  simulados.
- Identidad estable de incidencias: la misma combinación de pago y motivo
  conserva su ID entre ejecuciones y pasa a `RESOLVED` solo cuando una
  conciliación posterior confirma que la causa desapareció.
- Flujo de agente de solo lectura (LangGraph, con CrewAI opt-in y
  deshabilitado por defecto) que resume el snapshot de conciliación sin poder
  mutar datos, expuesto también por un servidor MCP local por stdio.
- Revisión humana persistente: un operador puede confirmar o discrepar de una
  incidencia `OPEN` con un motivo obligatorio; la decisión se guarda en un
  registro SQLite de solo agregado que sobrevive a reinicios del proceso,
  pero nunca cambia el estado de la incidencia ni mueve dinero.

## Capabilities

### New Capabilities
- `wallet-reconciliation`: motor determinista que compara wallet, proveedor y
  ledger, clasifica diferencias y mantiene la identidad/estado de las
  incidencias a través de la API W6 y las ayudas W2.
- `reconciliation-readonly-agent`: flujo LangGraph (y CrewAI opcional) y
  servidor MCP que exponen únicamente lectura del snapshot de conciliación,
  sin herramientas de escritura ni acceso a acciones financieras.
- `reconciliation-human-review`: registro persistente y auditable de
  decisiones humanas (`CONFIRM_FINDING` / `DISPUTE_FINDING`) sobre incidencias
  abiertas, sin autenticación de producción y sin efecto sobre saldos.

### Modified Capabilities
_(ninguna; no existen specs previas en este repositorio)_

## Impact

- Código nuevo: `app.py` (rutas W6/W2/agente/revisión), `src/reconciliation/`
  (`models.py`, `service.py`, `guardrails.py`, `w6_group.py`,
  `human_reviews.py`, `agent_tools.py`, `agent_workflow.py`), `mcp_server.py`,
  `index.html` (dashboard), `fixtures/`, `tests/`.
- Dependencias opcionales en un entorno Python 3.13 aislado (`.venv-ai`):
  `langgraph`, `crewai`, `mcp` (ver `requirements-ai.txt`).
- Persistencia: solo el log de revisión humana es durable (SQLite en
  `artifacts/human_reviews.sqlite3`); wallet, proveedor, ledger e incidencias
  viven en memoria del proceso.
- Sin integraciones externas reales: todo dato de wallet/proveedor/ledger es
  sintético y local.
