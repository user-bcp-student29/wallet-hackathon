# Skill: transaction-normalization

## Objetivo

Convertir un registro de entrada del fixture de wallet, proveedor o ledger a la
forma común `TransactionRecord` antes de conciliar.

## Entradas y salidas

- Entrada: un objeto JSON y su fuente declarada (`wallet`, `provider` o
  `ledger`).
- Salida: un registro normalizado inmutable con identificadores de
  transacción/idempotencia, fuente, referencia externa, monto entero en
  unidades menores, moneda, estado, marca de tiempo UTC y cuenta del ledger
  cuando aplica.

## Restricciones y errores

Nunca conviertas dinero decimal, inventes valores faltantes, accedas a rutas
provenientes de la entrada, aceptes campos desconocidos ni infieras un estado
terminal. Rechaza esquema, montos, IDs, moneda, signos de cuenta, estado y
marca de tiempo inválidos con un `InputValidationError` explícito.

## Ejemplo

`{"transaction_id":"TX-1","idempotency_key":"idem-1",...,"amount_minor":1550}`
desde la wallet se convierte en un registro de wallet con monto `1550` PEN.

## Aceptación

Las tres fuentes se normalizan al tipo común; los decimales inválidos y los
registros mal formados fallan de forma cerrada; la entrada original no se
modifica.
