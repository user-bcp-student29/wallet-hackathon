# Escenarios de demo W6

Inicia la app con `python app.py` y abre `http://127.0.0.1:8000`. El dashboard
usa solo datos locales y sintéticos.

## 1. Pago W2 confirmado y camino feliz

El grupo inicia con `PAY-1500` confirmado por S/ 15.00, una liquidación del
proveedor coincidente y dos asientos de pago en el ledger. Primero haz clic en
**Ejecutar POST /reconciliations**:

```json
{"status":"MATCHED","differences":[]}
```

Para probar en cambio la ayuda W2, haz clic en **Crear pago de S/ 15.00** y
luego en **Confirmar pago**. Esto solo cambia el estado simulado en memoria de
wallet/proveedor y agrega los asientos de débito/crédito del pago. La
conciliación en sí nunca cambia la wallet ni el ledger.

## 2. Diferencia de monto y resolución

Con `PAY-1500` seleccionado:

1. Haz clic en **Reportar S/ 16.00** (`POST /control/settlements` con modo
   `AMOUNT`).
2. Concilia de nuevo. El resultado es `DIFFERENCES` con el motivo
   `AMOUNT_MISMATCH`.
3. Consulta `GET /reconciliations/incidents`; la incidencia está `OPEN`.
4. Repite la conciliación; la incidencia conserva el mismo ID.
5. Haz clic en **Limpiar alteración** (`mode: CLEAR`) y concilia otra vez.
6. El resultado es `MATCHED`; el mismo ID de incidencia ahora está `RESOLVED`.

El control altera solo el reporte del proveedor. El monto de la wallet y el
ledger permanecen sin cambios.

## 3. Callback no entregado y confirmación W2

1. Crea un nuevo pago de S/ 15.00; queda `PENDING`.
2. Selecciona **No entregar callback**. La liquidación simulada del proveedor
   reporta `CONFIRMED`, pero el estado de la wallet sigue `PENDING`.
3. Concilia e inspecciona la incidencia `STATUS_MISMATCH`.
4. Confirma el pago seleccionado con la ayuda W2 y concilia de nuevo.
5. La diferencia de estado del callback desaparece y la incidencia original
   queda `RESOLVED`.

## Controles adicionales

- **Quitar del reporte** produce `MISSING_SETTLEMENT`.
- **Duplicar fila** produce `DUPLICATE_SETTLEMENT`.
- **Agregar operación huérfana** crea una fila del proveedor sin transacción de
  wallet y produce `ORPHAN_SETTLEMENT`.
- `GET /ledger` incluye los dos asientos `FUNDING` iniciales y los movimientos
  de pago.

La conciliación solo detecta problemas; no mueve dinero ni repara
saldos/ledger automáticamente.
