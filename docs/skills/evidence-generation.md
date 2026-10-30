# Skill: evidence-generation

## Objetivo

Producir evidencia vinculada a una ejecución de conciliación y a las versiones
exactas de los fixtures.

## Entradas y salidas

- Entrada: ID de ejecución, hora de creación, tres hashes de fixtures, resumen
  y resultados.
- Salida: evidencia JSON en `artifacts/` y un `evidence.md` legible.

## Restricciones

No incluyas credenciales ni alteres los fixtures de origen. La evidencia no
debe dar a entender una integración externa o una aprobación humana que no
ocurrió.

## Ejemplo

La evidencia registra el SHA-256 de los fixtures de wallet, proveedor y ledger
y lista cada clasificación de diferencia.

## Aceptación

La evidencia puede obtenerse por ID de ejecución, referencia los hashes de
origen de la ejecución y contiene el mismo conjunto de resultados
deterministas.
