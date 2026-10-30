# Criterios de aceptación W6 · Corte 1

| ID | Criterio de aceptación | Verificación |
|---|---|---|
| CA01 | Cargar fuentes sintéticas independientes de wallet, proveedor y ledger. | Una prueba de integración inicia una ejecución con los tres archivos fixture. |
| CA02 | Normalizar los registros al contrato común de transacción sin dinero decimal. | Las pruebas de normalización verifican los campos requeridos y rechazan montos decimales. |
| CA03 | Identificar coincidencias exactas. | `test_exact_match`. |
| CA04 | Detectar diferencias de monto y de estado. | `test_amount_mismatch`, `test_status_mismatch`. |
| CA05 | Detectar registros faltantes en wallet, proveedor y ledger. | Tres pruebas de fuente faltante. |
| CA06 | Detectar transacciones duplicadas en wallet/proveedor. | `test_duplicate_transaction`. |
| CA07 | Clasificar de forma segura transacciones pendientes, con timeout y rechazadas. | Pruebas de pendiente, timeout y rechazado. |
| CA08 | Exponer la API local de crear/listar/detalle/diferencias/evidencia y OpenAPI. | Pruebas de integración HTTP. |
| CA09 | Mantener acotados los fixtures de entrada y rechazar esquemas inválidos y payloads demasiado grandes. | Pruebas del cargador protegido y de validación de la API. |
| CA10 | Producir evidencia reproducible de la ejecución con hashes de fixtures y resultados. | Prueba de integración y `evidence.md`. |
| CA11 | Nunca mover dinero ni mutar el ledger durante la conciliación. | Pruebas de inmutabilidad del estado. |
| CA12 | Ejecutar localmente con Python de biblioteca estándar y pruebas automatizadas. | Los comandos documentados se ejecutan correctamente. |
| CA13 | Implementar los contratos W6 de `/settlements`, `/ledger`, incidencias, conciliación y controles del proveedor. | `test_w6_contract.py`. |
| CA14 | Conservar la identidad de las incidencias entre ejecuciones repetidas y resolverlas al eliminar la causa. | Pruebas del ciclo de vida de monto y callback. |
| CA15 | Simular crear/confirmar W2 y callback no entregado sin sistemas externos. | Pruebas de integración de pagos W2 y callback. |

La aprobación humana, la orquestación con LangGraph, los agentes CrewAI, MCP y
los guardrails completos de runtime son criterios de seguimiento, no
afirmaciones de este corte.
