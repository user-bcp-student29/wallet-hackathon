# Propuesta: corte de conciliación determinista W6

## Problema

Operaciones necesita una comparación repetible de transacciones de wallet,
transacciones del proveedor y asientos del ledger contable. La demo actual solo
modela un control de liquidación y no ofrece tres fuentes independientes,
normalización compartida de transacciones ni ejecuciones de conciliación
trazables.

## Cambio propuesto

Agregar un servicio local de conciliación determinista que cargue tres
fixtures JSON sintéticos, los normalice a un registro común de transacción,
clasifique coincidencias y diferencias, y exponga cada ejecución y su evidencia
mediante una API HTTP local. El primer corte vertical se mantiene sin
dependencias y ejecutable localmente.

## Alcance

- Fixtures independientes de wallet, proveedor y ledger.
- Validación estricta de esquema, montos, estados, moneda, tamaño y duplicados.
- Coincidencia y clasificación deterministas, incluidos los estados pendiente y
  rechazado.
- API para iniciar, listar e inspeccionar ejecuciones y obtener sus diferencias
  y evidencia.
- Pruebas automatizadas unitarias y de integración de API, más evidencia local
  generada.

## Fuera de alcance

- Integraciones reales de pagos, wallet, proveedor, base de datos o producción.
- Decisiones financieras basadas en LLM o movimiento automático de dinero.
- CrewAI, LangGraph, MCP y revisión humana interactiva en el corte original sin
  dependencias. Más abajo se documentan incrementos posteriores acotados de
  análisis con LangGraph/CrewAI, MCP y revisión humana persistente.
- Reversos o ediciones de saldos y asientos del ledger.

## Incremento posterior de agentes

El incremento actual agrega cuatro herramientas W6 de solo lectura sin
argumentos y un flujo LangGraph acotado. CrewAI es opt-in y está deshabilitado
por defecto; su agente no tiene herramientas y recibe solo conteos agregados y
códigos de motivo. Una lista permitida determinista valida cada recomendación.
Este incremento no cambia el estado de la conciliación.

## Incremento posterior de MCP y revisión humana

El adaptador MCP local por stdio expone solo operaciones GET fijas en loopback.
Las decisiones de revisión humana se agregan a un registro de auditoría SQLite
local para incidencias OPEN. Las decisiones confirman o discrepan de un
hallazgo y nunca aprueban ni ejecutan un pago. Los nombres de revisor son
etiquetas declaradas y no identidades autenticadas; sigue siendo una
demostración local y no una autorización de producción.

## Riesgos y supuestos

- Un asiento del ledger se vincula a una transacción por `transaction_id`; la
  comparación de montos usa la suma de sus asientos.
- Los montos son unidades menores enteras y todos los fixtures iniciales usan
  PEN.
- Un timeout del proveedor se representa con el estado `TIMEOUT`; no se trata
  como una liquidación exitosa.
- Los datos de los fixtures solo se consideran confiables tras validarse; una
  entrada inválida hace fallar la ejecución de forma explícita en lugar de
  producir un reporte parcial con apariencia de éxito.
