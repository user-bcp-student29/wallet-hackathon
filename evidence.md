# Evidencia de conciliación W6

- Ejecución: `run-70890f71a444`
- Generado el (UTC): `2026-10-30T18:46:20+00:00`
- Fuentes: fixtures JSON sintéticos de wallet, proveedor y ledger.
- Ejecución: servicio local determinista en Python; sin integraciones externas.
- Movimiento de dinero: ninguno.
- Pruebas automatizadas: `PASS — 47 pruebas`
- Flujo de API W6: `MATCHED → AMOUNT_MISMATCH → RESOLVED`.

## Evidencia de aceptación

| Verificación | Resultado |
|---|---:|
| Transacciones procesadas | 10 |
| Coincidentes | 1 |
| Diferencias | 8 |
| Pendientes de revisión | 1 |
| Requieren revisión humana | 4 |

SHA-256 de los fixtures:

- `ledger`: `c6bd613f822028378000b714e9d37ca0f2a2391e51694df2b47cc56151760589`
- `provider`: `b47481b94055726d8728fe62a84777080bc1b5176e3a04dcff63abadc7b74508`
- `wallet`: `12153c182010dc3a1b5fb6e1ac0dcf96b6a2361552aa2d03bc156a7a849bcdc2`

## Resultados por transacción

| Transacción | Conciliación | Tipos de diferencia | Severidad | Revisión humana |
|---|---|---|---|---|
| `TX-AMOUNT` | `DIFFERENCE` | AMOUNT_MISMATCH | `MEDIUM` | No |
| `TX-DECLINED` | `HUMAN_REVIEW_REQUIRED` | DECLINED | `CRITICAL` | Sí |
| `TX-DUPLICATE` | `HUMAN_REVIEW_REQUIRED` | DUPLICATE | `HIGH` | Sí |
| `TX-MATCH` | `MATCHED` | — | `NONE` | No |
| `TX-MISSING-LEDGER` | `DIFFERENCE` | MISSING_IN_LEDGER | `MEDIUM` | No |
| `TX-MISSING-PROVIDER` | `DIFFERENCE` | MISSING_IN_PROVIDER | `MEDIUM` | No |
| `TX-MISSING-WALLET` | `DIFFERENCE` | MISSING_IN_WALLET | `MEDIUM` | No |
| `TX-PENDING` | `PENDING_REVIEW` | MISSING_IN_LEDGER, PENDING | `LOW` | No |
| `TX-STATUS` | `HUMAN_REVIEW_REQUIRED` | STATUS_MISMATCH, DECLINED | `CRITICAL` | Sí |
| `TX-TIMEOUT` | `HUMAN_REVIEW_REQUIRED` | MISSING_IN_LEDGER, STATUS_MISMATCH, TIMEOUT, PENDING | `HIGH` | Sí |

## Validación

Comando: `python -m unittest discover -s tests -v` — PASS — 47 pruebas.

## Notas de guardrails y HITL

- El esquema de origen, los tipos de monto, la moneda, los identificadores,
  el tamaño de los fixtures y los valores con apariencia de secreto se
  validan antes de conciliar.
- Se bloquean los nombres de herramientas financieras y las
  recomendaciones financieras inseguras.
- Los resultados marcados para revisión humana son orientativos; este corte
  no ejecuta acciones financieras ni aprueba pagos.
- Ejecución con control de monto: `MATCHED` a `DIFFERENCES` (`AMOUNT_MISMATCH`), incidencia `INC-1e3dd5e1-0001` conservada al repetir, luego `RESOLVED` tras limpiar.
- Evidencia del flujo W6: `artifacts/w6-contract-flow.json`.
