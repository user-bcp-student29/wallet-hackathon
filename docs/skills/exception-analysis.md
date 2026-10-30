# Skill: exception-analysis

## Objetivo

Explicar a un analista de operaciones los resultados de diferencias
deterministas sin cambiar el resultado ni los datos de origen.

## Entradas y salidas

- Entrada: un `ReconciliationResult` y los IDs/hashes de sus fuentes.
- Salida: una explicación concisa, los campos de apoyo y un siguiente paso
  seguro para el operador.

## Restricciones

No infieras hechos faltantes del proveedor, apruebes pagos, reversas
operaciones, edites ledger/saldos ni afirmes que una diferencia está resuelta
sin una nueva ejecución de conciliación.

## Ejemplo

Para `AMOUNT_MISMATCH`, reporta ambos montos enteros y recomienda revisar el
reporte del proveedor; no elijas qué monto es el válido.

## Aceptación

Toda explicación referencia un tipo de diferencia existente y no recomienda una
acción financiera prohibida. La implementación de un agente en runtime queda
diferida más allá del corte 1.
