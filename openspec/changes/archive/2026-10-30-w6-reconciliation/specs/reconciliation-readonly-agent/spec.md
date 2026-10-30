# Spec Delta

## Purpose

Permite que un agente de IA explique el snapshot de conciliación y recomiende
un seguimiento seguro, usando únicamente herramientas de solo lectura, sin
poder ejecutar pagos ni cambiar datos.

## ADDED Requirements

### Requirement: Herramientas de solo lectura sin argumentos
El sistema SHALL exponer exactamente cuatro herramientas de agente sin
argumentos (`get_wallet_payments`, `get_settlements`, `get_ledger`,
`get_reconciliation_incidents`) y SHALL rechazar cualquier otro nombre de
herramienta o cualquier argumento suministrado.

#### Scenario: Herramienta desconocida
- **WHEN** el flujo intenta invocar un nombre de herramienta fuera de la lista
  permitida
- **THEN** el despachador rechaza la llamada sin ejecutar ninguna acción

#### Scenario: Argumento suministrado
- **WHEN** se intenta pasar un argumento a cualquiera de las cuatro
  herramientas permitidas
- **THEN** el despachador rechaza la llamada

### Requirement: Flujo LangGraph de tres nodos
El sistema SHALL ejecutar el análisis de `GET /agent/analysis` como un grafo
LangGraph de exactamente tres nodos (recolectar snapshot, analizar, validar
guardrails de salida), sin bucles ni recalcular el estado de las incidencias.

#### Scenario: Análisis no recalcula incidencias
- **WHEN** se ejecuta `GET /agent/analysis`
- **THEN** el estado de las incidencias (`OPEN`/`RESOLVED`) permanece igual
  antes y después de la llamada

#### Scenario: Entorno sin LangGraph instalado
- **WHEN** el intérprete activo no tiene LangGraph instalado
- **THEN** `GET /agent/analysis` responde `503` con guía de instalación

### Requirement: CrewAI opcional y deshabilitado por defecto
El sistema SHALL mantener CrewAI deshabilitado salvo que `ENABLE_CREWAI=true`
y `CREWAI_MODEL` estén configurados, SHALL darle al agente CrewAI solo conteos
agregados y códigos de motivo sin herramientas, y SHALL validar su
recomendación contra una lista permitida antes de devolverla.

#### Scenario: CrewAI desactivado por defecto
- **WHEN** no se configuran `ENABLE_CREWAI` ni `CREWAI_MODEL`
- **THEN** `GET /agent/analysis` reporta `crewai_status: "DISABLED"` y no
  invoca ningún modelo

#### Scenario: Recomendación fuera de la lista permitida
- **WHEN** CrewAI está habilitado y devuelve un texto que no coincide
  exactamente con la lista permitida
- **THEN** el guardrail de salida rechaza la recomendación

### Requirement: Servidor MCP local de solo lectura
El sistema SHALL exponer un servidor MCP local por stdio que ofrezca
únicamente las mismas cuatro herramientas de lectura, llamando solo a rutas
`GET` fijas de la API W6 en `127.0.0.1`, sin herramienta de creación de pagos,
controles de liquidación, conciliación o escritura de revisión.

#### Scenario: API W6 no disponible
- **WHEN** la API W6 local no está en ejecución
- **THEN** el servidor MCP no puede completar sus consultas de lectura

#### Scenario: Herramienta de escritura inexistente
- **WHEN** un cliente MCP intenta listar herramientas de escritura
  (creación de pagos, controles o revisión humana)
- **THEN** ninguna de esas herramientas aparece en el servidor MCP
