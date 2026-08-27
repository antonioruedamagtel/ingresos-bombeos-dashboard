# Informe de validación · Dashboard v1.0

## Veredicto

**Compartible con cautelas.** El dashboard, la reconstrucción histórica incluida
y el simulador funcionan y son reproducibles. La muestra entregada contiene
enero de 2023; las decisiones de inversión deben recalcularse con un histórico
amplio, supuestos corporativos y una curva futura de precios aprobada.

## Evidencia validada

- Aguayo enero de 2023: 4.849.834 € en la capa ENERGY frente a 4.930.968 €
  implícitos en el benchmark; desviación de -1,65 %.
- Aguayo: 13.457 €/MW frente a una referencia aproximada de 14.100 €/MW;
  desviación de -4,6 %.
- Secundaria sistema enero de 2023: identidad agregada reconciliada sin residuo.
- RRTT preapagón: 0,299 M€/mes frente a ~0,32 M€/mes; -6,7 %.
- RRTT posapagón: 1,086 M€/mes frente a ~1,07 M€/mes; +1,5 %.
- mFRR 27–28/04/2026: 425.254 € reconstruidos; residuo inferior a 1 €.
- SSAA abril y mayo de 2025: 16/16 celdas externas reproducidas y participaciones
  TTCC coherentes con 69 % y 79 %.
- Cincuenta y tres controles de código y datos: parser, granularidad, DST,
  signos, cierres, joins, calibraciones y restricciones del simulador.

## Controles del simulador

- Conversión trazable de hm³ y salto neto a MWh hidráulicos y eléctricos.
- Potencias, eficiencias, disponibilidad, SOC inicial/final y ciclos diarios.
- Exclusión mutua exacta entre bombeo y turbinación, también con precios
  negativos, mediante MILP cuando la relajación lineal no es físicamente válida.
- Reconciliación anual: neto = arbitraje + SSAA − OPEX variable − OPEX fijo.
- Escenarios Low, Base y High con supuestos visibles en la interfaz.

## Limitaciones que deben acompañar cualquier cifra

- La energía secundaria histórica por activo es una **estimación** distribuida
  por participación en banda; no una observación física por unidad.
- El PMD y la configuración técnica son públicos o introducidos por el usuario;
  el forecast no incorpora una curva externa futura de precios.
- La anualización de una muestra corta amplifica estacionalidad y eventos
  singulares. La interfaz avisa si hay menos de 90 días; se recomienda 12–36
  meses para exploración y una curva fundamental para valoración.
- No se modelan CAPEX, financiación, impuestos, hidrología, permisos,
  restricciones ambientales, peajes ni costes de arranque.
- Los días de cambio horario se detectan y se marcan; no deben agregarse como
  validados cuando el cierre de volumen falla.

## Resultado de publicación

La aplicación es adecuada para exploración, comparación de activos, trazabilidad
del revenue stack y análisis preliminar de proyectos. No es, por sí sola, una
base suficiente para aprobar una inversión o comprometer un ingreso contractual.
