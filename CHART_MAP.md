# Mapa de visualizaciones

| Vista | Pregunta que responde | Métrica y unidad | Dimensión | Fuente |
|---|---|---|---|---|
| Ingresos por central | ¿Qué activos generan más valor? | Ingreso reconstruido, € | Central y periodo | Detalle analítico OMIE + e·sios |
| Revenue stack | ¿De qué mercados procede el ingreso? | Ingreso incremental, € | Mercado / componente | I90, PMD e intradiario OMIE |
| Evolución temporal | ¿Cuándo se genera o destruye valor? | Ingreso, € por día | Fecha y central | Detalle analítico |
| Precio capturado | ¿A qué precio compra y vende cada activo? | €/MWh | Central y sentido | Volumen y precio cruzados |
| PMD histórico | ¿Cuál es la forma de precios usada? | €/MWh | Hora | `marginalpdbc` de OMIE |
| Proyección Low/Base/High | ¿Qué rango de ingreso neto resulta? | M€ por año | Año y escenario | Backtest PMD + supuestos del usuario |
| Puente económico | ¿Qué aporta cada componente al resultado? | M€ en el primer año | Arbitraje, SSAA, OPEX | Motor prospectivo |
| Cobertura / QA | ¿Qué evidencia es utilizable? | % y recuentos | Mercado y clase de dato | Reglas de calidad y reconciliaciones |

Todos los gráficos responden a los filtros globales de central y periodo. Las
tablas que acompañan a cada visual conservan el detalle necesario para auditar
la cifra y diferencian observado, proxy observado, estimado y forecast.
