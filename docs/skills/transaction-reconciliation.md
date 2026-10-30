# Skill: transaction-reconciliation

## Objetivo

Comparar transacciones de wallet normalizadas con transacciones del proveedor y
asientos del ledger mediante reglas deterministas.

## Entradas y salidas

- Entrada: registros normalizados agrupados por las tres fuentes conocidas.
- Salida: un `ReconciliationResult` por ID de transacción, con estados/montos
  de cada fuente, estado de conciliación, tipos de diferencia, severidad,
  siguiente acción segura e indicador de revisión humana.

## Restricciones

Nunca uses un LLM para aritmética, cambiar saldos o ledger, ejecutar pagos ni
convertir pendiente/timeout en éxito. Los registros duplicados de una fuente
siguen siendo diferencias y no pueden elegirse automáticamente como el
registro correcto.

## Ejemplo

Un monto de wallet `10000` frente a un monto del proveedor `9000` produce
`AMOUNT_MISMATCH`; no se edita ninguna fuente.

## Aceptación

Se clasifican de forma reproducible las coincidencias exactas, las diferencias
de monto/estado, los registros faltantes en una fuente, los duplicados, los
pendientes, los timeouts, los rechazados y las diferencias de monto del ledger.
