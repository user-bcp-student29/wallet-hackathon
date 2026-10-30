# wallet-reconciliation Specification

## Purpose
Permite comparar de forma determinista la wallet, el reporte del proveedor y
el ledger contable, y mantener la identidad de cada incidencia detectada a lo
largo de conciliaciones repetidas.

## Requirements

### Requirement: Comparación de tres fuentes
El sistema SHALL comparar, en cada `POST /reconciliations`, los pagos de la
wallet, las filas del reporte del proveedor (`GET /settlements`) y los
asientos del ledger (`GET /ledger`) del grupo completo, sin filtros de fecha
ni cierres diarios.

#### Scenario: Conciliación sin diferencias
- **WHEN** los tres registros de un pago confirmado coinciden en monto y
  estado
- **THEN** el resultado es `{"status":"MATCHED","differences":[]}`

#### Scenario: Conciliación con diferencia de monto
- **WHEN** el reporte del proveedor indica un monto distinto al de la wallet
  para el mismo pago
- **THEN** el resultado es `DIFFERENCES` con una incidencia de motivo
  `AMOUNT_MISMATCH`

### Requirement: Identidad estable de incidencias
El sistema SHALL conservar el mismo ID de incidencia para la misma
combinación de pago/recurso y motivo a través de ejecuciones repetidas de
`POST /reconciliations`, y SHALL marcarla `RESOLVED` solo cuando una
conciliación posterior confirma que la causa desapareció.

#### Scenario: Repetir conciliación sin cambios
- **WHEN** se ejecuta `POST /reconciliations` dos veces seguidas con la misma
  diferencia activa
- **THEN** la incidencia abierta conserva el mismo ID en ambas respuestas

#### Scenario: Causa corregida
- **WHEN** se limpia la alteración que causó la incidencia y se concilia de
  nuevo
- **THEN** la incidencia pasa a `RESOLVED` conservando su ID original

#### Scenario: Causa reaparece
- **WHEN** la misma condición que causó una incidencia `RESOLVED` vuelve a
  ocurrir
- **THEN** la misma incidencia se reabre con estado `OPEN`

### Requirement: Controles de simulación del proveedor
El sistema SHALL ofrecer `POST /control/settlements` con los modos `AMOUNT`,
`MISSING`, `DUPLICATE`, `ORPHAN`, `CALLBACK_UNDELIVERED` y `CLEAR` para alterar
únicamente el reporte de prueba del proveedor, sin modificar la wallet ni el
ledger.

#### Scenario: Alterar monto reportado
- **WHEN** se envía `{"paymentId":"PAY-1500","mode":"AMOUNT","amountCents":1600}`
- **THEN** `GET /settlements` refleja 1600 para ese pago mientras la wallet y
  el ledger permanecen sin cambios

#### Scenario: Operación huérfana
- **WHEN** se envía `mode: "ORPHAN"` con un `paymentId` que no existe en la
  wallet
- **THEN** el reporte del proveedor incluye una fila sin contraparte en la
  wallet y la siguiente conciliación produce `ORPHAN_SETTLEMENT`

#### Scenario: Limpiar alteración
- **WHEN** se envía `{"paymentId":"PAY-1500","mode":"CLEAR"}`
- **THEN** el reporte del proveedor vuelve a reflejar el estado real de la
  wallet para ese pago

### Requirement: Ayudas W2 de pago simulado
El sistema SHALL permitir crear (`POST /payments`) y confirmar
(`POST /payments/{payment_id}/confirm`) un pago sintético, registrando sus
asientos de débito/crédito en el ledger una sola vez por confirmación.

#### Scenario: Crear y confirmar un pago
- **WHEN** se crea un pago con `{"amountCents":1500}` y luego se confirma
- **THEN** el pago queda `CONFIRMED` y el ledger gana exactamente una fila de
  débito en `wallet` y una de crédito en `clearing` por ese pago

#### Scenario: Confirmación repetida
- **WHEN** se confirma un pago que ya estaba `CONFIRMED`
- **THEN** el sistema no agrega asientos de ledger adicionales

### Requirement: Límites de la API de conciliación
El sistema SHALL responder `200` para una conciliación válida, `400` para
entradas inválidas, `413` para cuerpos de más de 16 KiB, y `429` cuando un
mismo cliente local supera 60 solicitudes de conciliación por minuto.

#### Scenario: Límite de tasa excedido
- **WHEN** un cliente envía más de 60 solicitudes `POST /reconciliations` en
  un minuto
- **THEN** las solicitudes adicionales de ese minuto reciben `429`
