# Spec Delta

## Purpose

Permite a un operador dejar constancia persistente y auditable de su criterio
sobre una incidencia de conciliación abierta, sin ejecutar ninguna acción
financiera ni cambiar el estado de la incidencia.

## ADDED Requirements

### Requirement: Registro de decisión humana sobre incidencias abiertas
El sistema SHALL aceptar `POST /reconciliations/incidents/{incident_id}/reviews`
con `reviewer`, `decision` (`CONFIRM_FINDING` o `DISPUTE_FINDING`) y
`rationale` obligatorio solo para incidencias en estado `OPEN`, y SHALL
rechazar la solicitud con `409` si la incidencia no está `OPEN`.

#### Scenario: Revisión de incidencia abierta
- **WHEN** se envía una decisión válida para una incidencia `OPEN`
- **THEN** la decisión se guarda y la respuesta incluye su ID, `reviewer`,
  `decision`, `rationale` e incidencia asociada

#### Scenario: Incidencia no abierta
- **WHEN** se intenta registrar una revisión para una incidencia `RESOLVED` o
  inexistente
- **THEN** el sistema responde `409`

#### Scenario: Decisión fuera de la lista permitida
- **WHEN** `decision` no es `CONFIRM_FINDING` ni `DISPUTE_FINDING`
- **THEN** el sistema rechaza la solicitud

#### Scenario: Motivo ausente
- **WHEN** `rationale` está vacío o ausente
- **THEN** el sistema rechaza la solicitud

### Requirement: Persistencia append-only en SQLite
El sistema SHALL almacenar cada decisión en un registro SQLite de solo
agregado que sobreviva a reinicios del proceso, e incluya marca de tiempo UTC,
identidad de la incidencia, etiqueta del revisor, decisión y motivo.

#### Scenario: Historial tras reinicio
- **WHEN** el servidor se reinicia después de registrar decisiones
- **THEN** `GET /reconciliation/reviews` sigue devolviendo esas decisiones

#### Scenario: Múltiples decisiones para la misma incidencia
- **WHEN** se registran dos decisiones distintas para la misma incidencia
- **THEN** ambas quedan en el historial sin sobrescribirse

### Requirement: La revisión humana no cambia el estado ni mueve dinero
El sistema SHALL tratar cada decisión humana como un registro de auditoría
que NUNCA aprueba, reversa ni ejecuta un pago, y que NUNCA cambia por sí sola
el estado `OPEN`/`RESOLVED` de la incidencia.

#### Scenario: Confirmar hallazgo no resuelve la incidencia
- **WHEN** se registra `CONFIRM_FINDING` sobre una incidencia `OPEN`
- **THEN** la incidencia permanece `OPEN` hasta que una conciliación posterior
  la resuelva

### Requirement: Identidad de revisor declarativa, no autenticada
El sistema SHALL aceptar `reviewer` como una etiqueta de texto declarada por
el usuario, sin verificar su identidad, y SHALL documentar que esto no
constituye una autorización de producción.

#### Scenario: Revisor sin autenticar
- **WHEN** se registra una decisión con cualquier etiqueta de `reviewer`
- **THEN** el sistema la acepta sin validar que corresponda a una identidad
  real
