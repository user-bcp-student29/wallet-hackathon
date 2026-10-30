# Plan de conciliación W6

1. Definir el registro común y las reglas de validación.
2. Agregar tres fixtures JSON sintéticos e independientes que cubran los
   resultados requeridos.
3. Implementar la carga acotada de fixtures y la normalización por fuente.
4. Implementar la coincidencia determinista, las clasificaciones, las
   severidades y los indicadores de revisión.
5. Agregar una API HTTP local para crear y consultar ejecuciones y evidencia.
6. Agregar pruebas unitarias y de integración HTTP para todos los criterios de
   aceptación del primer corte.
7. Generar un reporte de evidencia desde el mismo servicio determinista.
8. Documentar la ejecución local, la API, los supuestos y los siguientes cortes
   de implementación.

## Arquitectura

`fixtures/*.json -> cargador/normalizador de fuentes -> motor de conciliación
-> almacén de ejecuciones -> API HTTP -> reporte JSON/evidencia`

El primer corte usa solo la biblioteca estándar de Python. El almacenamiento de
ejecuciones es local al proceso y los fixtures sintéticos se leen desde un
directorio fijo del proyecto; los parámetros de la solicitud no pueden elegir
rutas arbitrarias del sistema de archivos.
