# AUDIT_REPORT.md

**Proyecto:** INGRESOS BOMBEOS ESPAÑA
**Auditoría:** metodológica y de código, fase 1
**Fecha:** 26/08/2026
**Alcance:** Handover Blueprint, `core/revenue.py`, `core/i90.py`, `core/common.py`, `sources/esios.py`,
`config/assets.csv`, `calibracion_afrr.py`, `consolidar_modelo_afrr_v050.py`, READMEs de patch v0.4.1 a v0.6.1.
**Método:** contraste contra una reconstrucción independiente de Aguayo enero de 2023 realizada descargando de
nuevo los 31 libros I90DIA de e·sios y los ficheros públicos de OMIE, sin ejecutar el código del proyecto.

## 0. Resumen ejecutivo

La arquitectura económica del proyecto es **correcta**. La identidad de puente de ingresos cierra en volumen
con residuo de 0,05 %. Los errores encontrados no están en el diseño sino en tres puntos concretos de
implementación, dos de ellos con efecto material sobre las cifras publicadas:

| # | Hallazgo | Severidad | Efecto medido |
|---|---|---|---|
| A-1 | El precio de RR nunca cruza porque `I90DIA11` no tiene columna de UP ni de Sentido y el tercer fallback exige Sentido | **Crítica** | -807.757 € en Aguayo enero 2023, cobertura RR 0 % |
| A-2 | La banda aFRR se valora sumando filas cuartohorarias sin factor temporal, sobre ambos sentidos, con el indicador 634 que es la mitad del precio de banda | **Crítica** | **factor 4,00 exacto de sobreestimación**, propagado al estimador post-SRS y a todo €/MW-año |
| A-3 | Doble aplicación de signo sobre P48 y sobre las energías de servicio (`value.abs() * signo`) | Alta, latente | Nula hoy en Aguayo, incorrecta en cuanto una UP tenga signo mixto |
| A-4 | Intradiario (IDA y MIC) ausente del motor de producción | Alta | +69.155 € en Aguayo enero 2023, variable en general |
| A-5 | En libros históricos, `I90DIA30` se lee con cabecera desplazada y pierde la columna Sentido | Media | mFRR AD queda sin precio en periodos legacy |
| A-6 | El redespacho `ECO` del mercado diario se etiqueta como restricción técnica | Media | Sin efecto en el total, atribución de mercado incorrecta |
| A-7 | Sin regresión DST cerrada, sin zona horaria explícita | Media | No cuantificado |

## 1. Matriz de auditoría por componente

| Componente | Metodología actual | Evidencia disponible | Confianza | Riesgo detectado | Acción propuesta |
|---|---|---|---|---|---|
| Identidad del puente `P48 = PBF + Σ Δ` | Hipótesis v0.5.9 | Cierre propio: residuo 0,0 MWh en AGUB y -60,0 MWh en AGUG sobre 114 GWh | **VALIDADO** | Ninguno | Elevar a test dorado |
| Base energética `P48 × PMD` | Implementada en `_day_ahead_revenue` | 2.094.519 € reproducido de forma independiente frente a los 2,095 M€ del proyecto | **VALIDADO** | `value.abs()` innecesario | Usar el signo nativo de P48 |
| Servicios en forma incremental `ΔE × (P − PMD)` | Implementada en `_service_revenue` | Las dos formas de cálculo coinciden dentro del 0,5 % | **VALIDADO** | Sólo es válida si la energía está dentro de P48 | Documentar la regla y aplicarla en bruto a lo que quede fuera |
| Restricciones del mercado diario | `I90DIA03` energía, `I90DIA09` precio, por UP y sentido | 765.402 € reproducido al euro | **VALIDADO** | Mezcla `ECO` con restricción técnica | Separar en dos líneas de mercado |
| mFRR AP (TERPRO) | `I90DIA07` energía, `I90DIA30` precio marginal | 600.437 € reproducido al euro; validación previa contra indicador 2197 al 100 % | **VALIDADO** | Ninguno | Conservar |
| mFRR AD (TERDIR) | `I90DIA30` con QH0/QH1 y sentido | Validado en 2026; en 2023 el sentido se pierde por cabecera | **PROBABLE** | Cobertura nula en histórico | Corregir la lectura de cabecera de `I90DIA30` |
| RR | `I90DIA06` energía, `I90DIA11` precio | Cobertura 0 % en el proyecto, 100 % en la reconstrucción | **INCORRECTO** | Clave de cruce equivocada | Fallback por `(datetime, tipo de redespacho)` |
| Restricciones en tiempo real | `I90DIA08` energía, `I90DIA10` precio | Cobertura real máxima 17,9 % | **PENDIENTE DE VALIDACIÓN** | Limitación de la fuente, no del código | Etiquetar y separar `Desvíos` e `Indisponibilidad` |
| Banda aFRR pre-SRS | `I90DIA05` × indicador 634, suma de filas | Factor 4,00 de sobreestimación demostrado | **INCORRECTO** | Escala y precio | Reescribir según sección 3 |
| Estimador aFRR post-SRS | Mediana €/MW-mes sobre `mw_reference` | Hereda el factor 4 y usa MW instalados como driver | **INCORRECTO** | Sesgo al alza y driver inadecuado | Recalibrar sobre banda asignada |
| Energía aFRR (secundaria) | No implementada | No publicada por UP en el I90 de 2023 | **AUSENTE** | Hueco de ingreso real | Estimar por cuota de banda, etiquetado |
| Intradiario de subastas | No implementado en producción | ΔE reproducido exactamente contra PIBCI | **AUSENTE** | Falta un mercado del stack | Integrar con `MARGINALPIBC` |
| Intradiario continuo | No implementado en producción | TRADES × duración = PIBCIC con MAE 0 | **AUSENTE** | Falta un mercado del stack | Integrar con TRADES |
| Desvíos | No implementado | Fuera de P48 por definición | **AUSENTE** | Residuo no explicado | Backlog, valoración en bruto |
| Signo nativo PDBC | Regla del proyecto | PDBC reproduce PBF exactamente: AGUG +114.317,9 y AGUB -37.614,7 MWh | **VALIDADO** | Ninguno | Conservar |
| TRADES = cantidad × duración | Regla del proyecto | MAE 0 frente a PIBCIC reproducido | **VALIDADO** | Ninguno | Conservar |
| Crosswalk participante a UP | No existe | Búsqueda propia confirma que no hay enlace en el I90 | **CORRECTAMENTE NO ASUMIDO** | Ninguno | Mantener como estimado |
| Gestión de fechas y DST | Mapeo por orden físico de columna | Sin test | **PENDIENTE DE VALIDACIÓN** | Alto en marzo y octubre | Tests de 92, 96 y 100 periodos |
| Granularidad del I90 | Deducida por hoja | Correcta: mezcla horaria y cuartohoraria detectada por hoja | **VALIDADO** | Ninguno en el parser | Documentar |
| LOW-DISK y caché reanudable | Descarga, parseo, caché, borrado | Reproducido en la auditoría | **VALIDADO** | Ninguno | Conservar |

## 2. Hallazgo A-1. El precio de RR nunca cruza

### Evidencia

La hoja `I90DIA11` del libro de 2023 tiene esta estructura real, verificada célula a célula:

```
Redespacho              | Tipo   | Cuarto de Hora del dia | Total | 1 .. 96
Reserva de sustitución  | RRFRON |                        | 27,73 | ...
Reserva de sustitución  | RR     |                        | 16,42 | ...
```

No hay columna de Unidad de Programación ni columna de Sentido. Existe **un único precio marginal por periodo
y por tipo de redespacho**, común a subir y a bajar.

### Causa raíz en el código

`core/revenue.py`, función `_service_revenue`, intenta tres cruces sucesivos:

1. `merge(on=["datetime","direction","up"])`. Falla: las filas de energía traen `up = AGUG/AGUB` y
   `direction = subir/bajar`, las de precio traen ambos vacíos.
2. Fallback por `(datetime, up)`. Falla por la misma razón.
3. Fallback de filas globales, `merge(on=["datetime","direction"])`. **Falla porque exige `direction`**, y la
   tabla global de RR no tiene sentido.

El diagnóstico v0.6.1 concluyó que había que buscar el precio de RR en el catálogo de indicadores de e·sios.
No es necesario: el precio estaba en el propio I90 y el problema era la clave de cruce.

### Corrección propuesta

Añadir un cuarto fallback para filas globales cruzando sólo por `datetime`, con desempate por tipo de
redespacho extraído de `concept` en ambos lados (`RR` frente a `RRFRON`), y control de ambigüedad.

### Efecto medido

| | Proyecto v0.6.0 | Reconstrucción |
|---|---|---|
| Cobertura de precio RR | 0,0 % | 100,0 % |
| Energía RR Aguayo | 25.114,4 MWh | 25.114,4 MWh |
| Aportación incremental RR | 0 € | **+807.757 €** (AGUG +386.669, AGUB +421.088) |
| Saldo generación menos consumo | 3,572 M€ | 4,368 M€ |

## 3. Hallazgo A-2. La banda aFRR está sobreestimada exactamente por cuatro

### Evidencia

Tres defectos que se componen:

**3.1. Ausencia de factor temporal.** `_afrr_pre_cutoff` calcula `revenue_gross = value.abs() * service_price`
fila a fila, con el comentario explícito de que el valor se trata como MW de un intervalo horario. Pero el
I90DIA05 histórico servido hoy por e·sios está reexpresado a 96 cuartos de hora. Cada hora aporta cuatro
filas y ninguna se pondera por 0,25 h. **Factor 4.**

**3.2. Suma de los dos sentidos.** El código no filtra `Sentido`. La hoja publica banda a subir y banda a
bajar. En Aguayo ambas valen 50,15 MW de media, así que la energía de banda se cuenta dos veces. **Factor 2.**

**3.3. Precio equivocado.** Se usa el indicador 634. Para el periodo pre-SRS, 634 es exactamente la mitad
del precio de reserva a subir (indicador 10388): ratio 2,0012 en enero de 2023 y 2,0016 en la ventana de
calibración del modelo. Además el indicador 10463, reserva a bajar, vale cero en todo el periodo, lo que
confirma que la remuneración pre-SRS recae sobre la banda a subir. **Factor 0,5.**

Composición: 4 × 2 × 0,5 = **4,00**.

### Verificación numérica directa

Replicando la fórmula de producción sobre los mismos datos de Aguayo enero 2023:

```
fórmula de producción  (|MW| por QH × 634, ambos sentidos) : 2.877.433 €
fórmula correcta       (MW medio horario a subir × 10388)  :   719.583 €
factor de sobreestimación                                  :        4,00
```

### Verificación cruzada contra el sistema

El indicador 899, coste de asignación de reserva a subir, presenta el mismo artefacto: para abril de 2026,
periodo cuartohorario nativo, `899 = Σ_h (632 × 2130)` con ratio 1,0000. Para enero de 2023, periodo
reexpresado, el ratio es exactamente 4,0000. El precio marginal derivado de las ofertas aceptadas de
`I90DIA13` es de 25 a 33 €/MW, coherente con 10388 (media 23,7 €/MW) e incompatible con los 94,8 €/MW que
resultarían de aceptar 899 sin corregir.

### Propagación

El error contamina `data/processed/afrr_estimator_rates_v050.csv`, y por tanto todos los meses posteriores
al 20/11/2024:

| Activo | Tasa publicada €/MW-mes | Tasa corregida estimada |
|---|---|---|
| Aguayo | 4.849,13 | 1.212,28 |
| Guillena | 2.343,55 | 585,89 |
| Ip | 3.311,42 | 827,86 |
| La Muela | 490,54 | 122,64 |
| Sallente | 627,27 | 156,82 |
| Tajo de la Encantada | 50,11 | 12,53 |

Sobre la validación global de abril de 2026, el ingreso aFRR estimado pasaría de 3.573.970 € a unos
893.500 €. Sobre la media simple de €/MW-año de los siete activos, la corrección resta del orden de
15.000 €/MW-año, lo que reduce la cifra publicada de 147.801 a unos 132.800 frente al benchmark de 100.000.
**Explica aproximadamente un tercio de la desviación, no toda.** El resto queda abierto.

### Corrección propuesta

```python
banda = i90[(sheet == "I90DIA05") & (Sentido == "Subir")]
banda_mw_hora = banda.groupby(["up", hora]).value.mean()      # MW medio de la hora
revenue = banda_mw_hora * precio_banda_hora                    # indicador 10388 pre-SRS
```

Post-SRS la banda deja de ser por UP y el problema pasa a ser de imputación, no de escala.

## 4. Hallazgo A-3. Doble aplicación de signo

`_day_ahead_revenue` calcula `signed_mwh = value.abs() * role_sign`, con `role_sign` derivado de si la UP
figura como generación o bombeo en `assets.csv`. Y `_service_revenue` calcula
`signed_delta_mwh = value.abs() * direction_sign`.

He verificado que **P48 en `I90DIA02` ya trae signo nativo**: AGUG siempre positivo, AGUB siempre negativo,
suma -88.939,235 MWh. Lo mismo ocurre en las hojas de energía de servicios, donde las filas `Bajar` ya son
negativas.

Es exactamente el error que el propio proyecto catalogó como prohibido para PDBC y PIBCI, aplicado aquí a las
fuentes I90. Hoy no produce diferencia en Aguayo porque cada UP tiene signo homogéneo. Falla en cuanto
aparezca una UP con signo mixto, un alias mal clasificado, o una unidad bidireccional. `La Muela` con el alias
`MUEL` es el candidato más probable a manifestarlo.

Corrección: usar el signo nativo y reservar el signo de rol únicamente como control de coherencia, emitiendo
un aviso de calidad cuando ambos discrepen.

## 5. Hallazgo A-4. Falta el intradiario en producción

`calculate_revenues` compone base P48 más restricciones diario, RR, restricciones tiempo real, mFRR y banda
aFRR. No hay componente de intradiario de subastas ni de intradiario continuo, pese a que v0.5.4 y v0.5.8 ya
demostraron cómo obtenerlos.

Reconstruidos de forma independiente para Aguayo enero de 2023:

| Mercado | ΔE AGUG | ΔE AGUB | Incremental AGUG | Incremental AGUB |
|---|---|---|---|---|
| IDA (PIBCI, precio MARGINALPIBC) | +890,6 MWh | -10.579,1 MWh | +9.083 € | +76.844 € |
| MIC (TRADES, precio de operación) | +276,1 MWh | -315,7 MWh | -10.392 € | -6.380 € |

Aportación neta +69.155 €. Pequeña en este mes, pero es un mercado completo del stack que el usuario pide
separar explícitamente, y en meses de alta actividad intradiaria puede no serlo.

## 6. Hallazgo A-5. Cabecera de `I90DIA30` en libros históricos

En el libro de 2023 la hoja `I90DIA30` coloca las etiquetas de periodo en la fila 1 y los nombres de las
columnas meta en la fila 2. `_detect_excel_header` puntúa las filas y elige la fila 1, porque premia el número
de etiquetas de periodo y la fila 2 no tiene ninguna. El resultado es que `Redespacho`, `Tipo Redespacho`,
`Sentido` y `Tipo QH` se convierten en `Unnamed: 0` a `Unnamed: 3`.

Como consecuencia `dir_col` no se encuentra y `direction` queda vacío. La rama de activación directa exige
`direction ∈ {subir, bajar}` y por tanto **el precio de mFRR AD nunca se asigna en periodos históricos**. La
rama AP sobrevive porque agrupa sólo por `datetime` y porque `concept` recoge los valores de la fila
desplazada.

En enero de 2023 el impacto es despreciable, pero es un defecto real de la lectura histórica.

## 7. Hallazgo A-6. El redespacho `ECO` no es una restricción técnica

`I90DIA03` publica, para Aguayo en enero de 2023, filas con `Redespacho = ECO`, `Sentido = Bajar` y
`Tipo Restricción = N/A`, por -48.347,7 MWh en AGUG y -39.782,5 MWh en AGUB. Es el mayor componente del
puente de ingresos, muy por encima de RR y de mFRR.

Producción lo agrega bajo la etiqueta única `RRTT diario`. El importe total coincide, pero la atribución por
mercado es incorrecta: el reequilibrio económico del proceso de restricciones no es la misma cosa que una
restricción técnica y, para el revenue stack comparativo que se pide, deben ir en líneas separadas.

## 8. Hallazgo A-7. Zona horaria y DST

`_reshape_wide_i90` mapea las columnas de intervalo por orden físico, lo cual es correcto y robusto en días
de 23 y 25 horas. Sin embargo el `datetime` se construye como `fecha + (periodo - 1)` sin zona horaria
explícita. El cruce con OMIE, que también usa numeración de periodo, es consistente. El cruce con indicadores
de e·sios, que traen marca temporal real convertida a Europe/Madrid, no está garantizado en los días de
cambio horario. No hay test que lo cubra. Se mantiene como riesgo abierto.

## 9. Hipótesis descartadas por esta auditoría

1. **Que el `P48 × PMD = 2,095 M€` tuviera un error de signo.** Reproducido de forma independiente. Es
   correcto.
2. **Que la reconstrucción OMIE de v0.5.8 duplicara energía sumando PIBCIC y TRADES.** El cierre de volumen
   demuestra que ΔIDA + ΔMIC coincide con el residuo del I90 con exactitud. La cifra de 10,58 M€ de v0.5.8
   procede de valorar programas y no de duplicar energía.
3. **Que hubiera que buscar el precio de RR en el catálogo de e·sios.** Está en `I90DIA11`.
4. **Que `I90DIA05` post-SRS pudiera resolverse por UP.** Confirmado que no.

## 10. Riesgos abiertos, no resueltos en esta fase

1. **Energía de regulación secundaria por UP.** No publicada en el I90 de 2023, que tiene 37 hojas y ninguna
   de energía de secundaria por unidad. Sólo estimable. Estimación por cuota de banda para Aguayo enero 2023:
   +369.745 €, rango 259 k€ a 481 k€.
2. **Residuo de 344 k€, un 6,8 %,** entre la reconstrucción con energía aFRR estimada y el benchmark externo.
3. **Definición exacta del benchmark externo.** No está establecido si su saldo generación menos consumo
   incluye o excluye servicios de ajuste y remuneración de capacidad. Mientras no se establezca, cualquier
   calibración fina contra él es discutible.
4. **Denominador de €/MW.** El valor implícito para Aguayo es 360,4 MW, más próximo a la potencia de bombeo
   que a la de turbinado. Debe ser un parámetro documentado por activo.
5. **Ventana de calibración del estimador aFRR anterior al apagón de abril de 2025**, aplicada a periodos
   posteriores en los que el propio proyecto documenta un factor 3,6 en RRTT.

## 11. Decisiones metodológicas adoptadas

1. La base energética es **P48**, por ser el programa final observable por UP y por reproducir el volumen
   físico del benchmark.
2. Los mercados contenidos en P48 se valoran en **incremental** frente a PMD. Los que no lo están, energía
   aFRR y desvíos, se valoran en **bruto**.
3. La banda aFRR es remuneración de capacidad y **no entra** en el saldo generación menos consumo ni en los
   precios capturados.
4. El precio de banda pre-SRS es el **indicador 10388** aplicado a la banda a subir, con ponderación
   temporal explícita.
5. Ningún coeficiente de ajuste. El residuo se publica siempre, desglosado y con signo.

## 12. Adenda de validación externa, 26/08/2026

Tras redactar las secciones anteriores se han obtenido dos publicaciones del
analista externo que sirve de benchmark, con sus pies de figura metodológicos, y
se ha podido contrastar el motor contra ellas. Esta adenda recoge lo que cambia.

### 12.1. La arquitectura del benchmark es la nuestra

Sus pies de figura declaran `Intraday = CIM + IDA1–IDA7` y
`TTCC = post-day-ahead and real-time constraints`. Contraste de su revenue stack
de Aguayo para enero de 2023, leyendo su gráfica frente a la reconstrucción:

| Componente | Su gráfica | Reconstrucción | |
|---|---|---|---|
| Day-ahead | ~2,1 M€ | 2.094.519 € | coincide |
| Intraday | pequeño | +69.155 € | coincide |
| RR | ~0,8 M€ | 807.757 € | coincide |
| mFRR | ~0,55 M€ | 600.437 € | coincide |
| TTCC | ~0,8 M€ | 796.519 € | coincide |
| aFRR banda | ~2,9 M€ | 719.583 € | difiere por 4,00 |

Su "Day-ahead" es `P48 × PMD`. La base energética del proyecto era la correcta.

### 12.2. El factor cuatro de la banda está también en el benchmark

Su pie de figura dice literalmente *"Source: I90DIA05 assigned reserve and ESIOS
indicator 634 marginal price"*, y sus barras apilan Up y Down. Replicando esa
fórmula exacta sobre nuestros datos:

```
Up     1.438.717 EUR      su grafica muestra ~1.450 kEUR
Down   1.438.717 EUR      su grafica muestra ~1.400 kEUR
Total  2.877.433 EUR      su grafica muestra ~2.850 kEUR
correcto (MW medio horario a subir x 10388)  719.583 EUR
factor 4,00
```

Se reproduce su cifra y su reparto por sentido. **El proyecto no cometió un error
propio: replicó fielmente la fórmula del benchmark.** Dos de las tres decisiones
se cancelan entre sí, porque `(subir + bajar) × 634 = subir × 10388`. Lo que no
se cancela es la ausencia de ponderación temporal sobre una tabla reexpresada a
96 cuartos de hora.

El argumento que cierra la cuestión es económico y no estadístico: el precio
marginal derivado de las ofertas aceptadas de `I90DIA13` está entre 25 y
33 €/MW. Bajo la convención sin ponderar, el proveedor cobraría unos 95 €/MW·h,
cuatro veces su propia oferta. En un mercado marginal eso no es posible.

Queda como recomendación contrastarlo contra una liquidación real de banda, que
resolvería el punto de forma definitiva en cualquier dirección.

### 12.3. Corrección de una interpretación propia

En la sección 10 se apuntó que el benchmark de ~5 M€ podía incluir la banda a su
valor correcto, porque `4.368.387 + 719.583 = 5.087.970` quedaba a un 0,1 %. Era
una coincidencia. El benchmark es **saldo de energía**, sin capacidad, y el hueco
lo cierra la **energía** de regulación secundaria, no la banda.

### 12.4. Nuevo hallazgo A-8: OMIE cambió la granularidad del intradiario el 19/03/2025

Verificado fichero a fichero: `pibci_2025031801.1` publica 24 periodos y
`pibci_2025031901.1` publica 96. El mercado diario permanece horario, de modo que
en un mismo mes conviven un `PDBC` horario y un `PIBCI` cuartohorario.

En los ficheros cuartohorarios el valor publicado es **potencia en MW**, no
energía, así que la energía es valor por 0,25 h. Deducir la granularidad por mes,
o asumirla, produce un error de factor cuatro **en el periodo de producción
actual**, no en un histórico lejano.

Efecto medido sobre el intradiario de Aguayo, frente a los volúmenes publicados:

| Mes | Antes de corregir | Corregido | Publicado |
|---|---|---|---|
| 2025-02 | -12.290,50 | -12.290,50 | -12.290,50 |
| 2025-04 | +61.460,02 | +16.166,32 | +16.166,32 |
| 2025-05 | +119.937,82 | +28.574,92 | +28.574,92 |

### 12.5. Nuevo hallazgo A-9: el 29/04/2025 no se publica por unidad

El día siguiente al apagón, el `I90DIA02` contiene ocho unidades, todas de
interconexión. No hay programa por unidad de programación nacional. La descarga y
el parseo funcionan: simplemente no hay dato.

No debe tratarse como un fallo ni como un día vacío silencioso. Se marca
`NO_UNIT_DATA_PUBLISHED` y el mes que lo contenga queda señalado como incompleto.

### 12.6. Resultado del contraste externo de volúmenes

Aguayo, enero a mayo de 2025, once magnitudes por mes frente a la tabla
publicada. Coinciden **todas** salvo dos celdas de marzo desviadas 3,00 MWh:

| Línea | Fuente propia | Resultado |
|---|---|---|
| Day-ahead | I90DIA26 (PBF) | exacto en los cinco meses |
| RR a subir y a bajar | I90DIA06 | exacto salvo +3,00 MWh en marzo |
| TTCC a subir y a bajar | I90DIA03 | exacto |
| Tiempo real | I90DIA08, familia restricciones | exacto |
| Terciaria a subir y a bajar | I90DIA07 | exacto salvo +3,00 MWh en marzo |
| Indisponibilidades | I90DIA08, familia indisponibilidad | exacto |
| Intradiario | OMIE PIBCI + TRADES | exacto en febrero, abril y mayo |

La cuota de restricciones a bajar sobre la energía de ajuste reproduce también su
afirmación pública: 55,6 % en enero, **69,4 % en abril frente al 69 % publicado**
y **79,5 % en mayo frente al 79 % publicado**.

El intradiario queda con dos diferencias abiertas, +561,60 MWh en enero y
-374,25 MWh en marzo. Son el 0,3 % y el 2,4 % del volumen del mercado y, lo que
importa más, **las dos rutas independientes de cálculo, la del I90 por identidad
y la de OMIE por ficheros, coinciden exactamente entre sí**.

### 12.7. Energía de regulación secundaria: método definitivo

El ancla de sistema queda verificada con diferencia nula en enero de 2023:

```
680 x 10389 - 681 x 10390 = 718 - 719 = +7.273.724 EUR
```

Es imprescindible usar 10389 y 10390, horarios, y no 682 y 683, cuartohorarios:
cruzar una serie horaria con una cuartohoraria por marca temporal toma sólo uno
de los cuatro precios de cada hora.

La estimación por activo se hace **sólo sobre el neto** y con la cuota de banda
como proxy de participación económica, nunca como asignación física, y **no se
reparte entre generación y bombeo**. Repartir por sentido produce precios
efectivos absurdos, porque la cuota de banda no es la cuota de energía activada
en cada dirección.

Para Aguayo en enero de 2023 el neto estimado es **+470.414 €**.

### 12.8. Resultado consolidado de Aguayo, enero de 2023

| Concepto | Importe | Clase |
|---|---|---|
| Base P48 x PMD | 2.094.519 € | observado |
| Intradiario de subastas | +85.927 € | observado |
| Intradiario continuo | -16.772 € | observado |
| Reequilibrio del diario | +765.402 € | observado |
| Restricciones en tiempo real | +31.117 € | observado |
| RR | +807.757 € | observado |
| mFRR terciaria | +600.437 € | observado |
| Energía de secundaria | +470.414 € | **estimado** |
| **Saldo de energía** | **4.838.801 €** | |
| Benchmark implícito 115,95 / 22,12 | 4.930.971 € | externo |
| **Desviación** | **-1,9 %** | |
| Banda aFRR, componente de capacidad aparte | 719.583 € | observado |

`€/MW` sobre los 349,7 MW que implican las propias cifras del benchmark:
**13.837 €/MW frente a 14.100**, un -1,9 %.

## 13. Recalibración del estimador aFRR y defecto abierto de cambio horario

### 13.1. Recalibración con la fórmula corregida

Ventana 01/11/2023 a 31/10/2024, doce meses completos, con banda a subir
ponderada por hora y precio del indicador 10388:

| Activo | Publicado v0.5.0 | Recalibrado | Factor | €/MW-mes sobre banda | Banda mediana |
|---|---|---|---|---|---|
| Aguayo | 4.849,13 | **1.212,32** | **4,00** | 10.051,60 | 37,96 MW |
| Guillena | 2.343,55 | 268,13 | 8,74 | 11.270,63 | 3,73 MW |
| Ip | 3.311,42 | 1.052,16 | 3,15 | 8.974,43 | 10,50 MW |
| La Muela | 490,54 | 116,48 | 4,21 | 9.150,22 | 19,75 MW |
| Sallente | 627,27 | 55,72 | 11,26 | 7.994,50 | 2,15 MW |
| Tajo de la Encantada | 50,11 | 4,29 | 11,67 | 3.340,07 | 0,48 MW |

El factor vale exactamente 4,00 en Aguayo porque su banda a subir y a bajar son
iguales. En los demás activos es mayor, porque el factor real es
`2 x (banda_subir + banda_bajar) / banda_subir` y varios ofertan mucha más banda
a bajar que a subir. Es decir, **el error no es un factor constante: distorsiona
también el reparto relativo entre centrales**.

Efecto agregado sobre un mes completo post-SRS de los siete activos:

```
con el estimador publicado : 3.573.974 EUR/mes
con el estimador corregido :   789.293 EUR/mes
sobreestimacion            : 4,53 x
```

La cifra publicada reproduce con dos euros de diferencia los 3.573.970 € que el
proyecto reportó para abril de 2026, lo que confirma que se ha replicado su
estimador exactamente antes de corregirlo.

Sobre la media simple de €/MW-año de los siete activos la corrección resta unos
**15.400 €/MW-año**, llevando los 147.801 publicados a unos 132.400. Sobre la
media ponderada por potencia resta 10.453.

**Advertencia importante para la lectura:** el benchmark externo de ~100.000
€/MW-año incorpora la banda calculada con la misma fórmula, de modo que también
está inflado. Comparar el motor corregido contra ese benchmark sin corregir
compara cosas distintas. La comparación sigue siendo informativa sobre todo lo
demás, pero no sobre la banda.

La nueva tabla se guarda en `config/afrr_estimator_rates_v2.csv`, con la
columna adicional de €/MW-mes referida a la **banda asignada**, que es el driver
físico correcto y el único que permite extrapolar a una central futura.

### 13.2. Defecto abierto A-10: el cambio horario no cierra

El motor se ejecutó de extremo a extremo sobre dos ventanas de catorce días que
contienen los cambios horarios de 2023. El parser resuelve la granularidad
correctamente, 92 y 100 cuartos de hora y 23 y 25 horas, pero **la identidad de
volúmenes no cierra en el día del cambio**:

| Ventana | Días que cierran | Día del cambio |
|---|---|---|
| 20/03 a 02/04/2023 | trece de catorce en 0,0 MWh | 26/03: residuo absoluto 9.354 MWh |
| 23/10 a 05/11/2023 | trece de catorce en 0,0 MWh | 29/10: residuo absoluto 1.637 MWh |

Afecta a **catorce de quince combinaciones activo-rol** el 26/03 y a **seis de
catorce** el 29/10.

La firma del defecto es informativa: en las unidades de bombeo el residuo **neto
del día es exactamente cero** mientras el absoluto es grande. No falta energía:
está atribuida al periodo equivocado. Es un desalineamiento de periodo entre las
hojas horarias y las cuartohorarias, no un dato ausente. Se descartó que fuera
un problema de alias, verificando que los códigos de La Muela son `MUEL` y
`MUEB` en todas las hojas de ese día, y que la ausencia de restricciones para esa
central ese día es real.

El residuo persiste al agregar por hora, de modo que tampoco es un artefacto del
reparto intrahorario.

Hasta resolverlo, el sistema **identifica los días de cambio horario y no
permite publicar como validado un periodo que los contenga**. Hay una prueba
automática que verifica que la detección funciona.
