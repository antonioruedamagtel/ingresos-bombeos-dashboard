# REVENUE_METHODOLOGY.md

## 1. La identidad que gobierna todo el motor

La liquidación de una unidad de programación puede escribirse de dos formas
algebraicamente idénticas:

```
liquidacion = PBF x PMD + Σ_m ΔE_m x P_m
            = P48 x PMD + Σ_{m ⊂ P48} ΔE_m x (P_m − PMD) + Σ_{m ⊄ P48} E_m x P_m
```

La equivalencia se sostiene si y sólo si

```
P48 = PBF + Σ_{m ⊂ P48} ΔE_m
```

Por eso el **cierre de volúmenes es una puerta previa a cualquier euro**. Si la
identidad física no cierra, la identidad económica no significa nada.

Resultado del cierre en enero de 2023, ocho centrales y ambos roles: residuo
máximo por debajo de 1 MWh sobre 987 GWh de programa.

## 2. Regla de valoración por mercado

| Mercado | ¿Dentro de P48? | Fórmula | Precio | Fuente |
|---|---|---|---|---|
| Mercado diario | base | `P48 x PMD` | marginal del diario | I90DIA02 + MARGINALPDBC |
| Intradiario de subastas | sí | `ΔE x (P_IDA − PMD)` | marginal de la sesión | PIBCI + MARGINALPIBC |
| | | *OMIE pasó el intradiario a cuarto de hora el 19/03/2025 manteniendo el diario horario. En los ficheros cuartohorarios el valor es potencia en MW, de modo que la energía es valor por 0,25 h.* | | |
| Intradiario continuo | sí | `ΔE x (P_trade − PMD)` | precio de cada operación | TRADES |
| Restricciones técnicas del diario | sí | `ΔE x (P_RT − PMD)` | por UP y sentido, pay as bid | I90DIA03 + I90DIA09 |
| Reequilibrio económico (ECO) | sí | `ΔE x (P_ECO − PMD)` | por UP y sentido | I90DIA03 + I90DIA09 |
| Restricciones en tiempo real | sí | `ΔE x (P_RT − PMD)` | por UP y sentido | I90DIA08 + I90DIA10 |
| Desvíos e indisponibilidad | sí | energía observada, sin precio público | no publicado | I90DIA08 |
| RR | sí | `ΔE x (P_RR − PMD)` | marginal global por periodo y tipo | I90DIA06 + I90DIA11 |
| mFRR terciaria | sí | `ΔE x (P_mFRR − PMD)` | TERPRO marginal, TERDIR por sentido y QH | I90DIA07 + I90DIA30 |
| Energía de regulación secundaria | **no** | neto de sistema x cuota de banda | 680 y 681 con 10389 y 10390 | estimada, no observable por unidad |
| Banda de regulación secundaria | **no** | `MW x precio x horas` | indicador 10388 pre-SRS, 2130 post-SRS | I90DIA05 |

La asimetría del cuadro es el corazón de la metodología: un mercado cuya energía
ya está dentro de P48 se valora en incremental porque su energía ya fue valorada
a PMD en la base; un mercado cuya energía no está en P48 se valora en bruto.
Mezclar ambas convenciones sobre la misma base produce doble conteo o infracuenta.

## 3. Signos

Ninguna fuente recibe un signo de rol. Todas traen signo nativo:

* `P48` de I90DIA02: generación positiva, bombeo negativo. Verificado sobre
  ocho centrales y 31 días sin un solo conflicto.
* `PDBC` de OMIE: idéntico a PBF al MWh.
* `PIBCI`: programa incremental con signo propio.
* `TRADES`: venta positiva, compra negativa.
* Hojas de energía de servicios: las filas a bajar ya vienen en negativo.

El motor calcula un control de coherencia entre signo nativo y rol configurado y
emite un aviso si discrepan. **Nunca corrige el dato.**

## 4. Claves de cruce de precio

Cada mercado declara su clave. La que casó se registra en el dato.

| Mercado | Clave documentada | Nota |
|---|---|---|
| Restricciones diario y tiempo real | `(día, QH, UP, sentido)` | precio específico de la unidad |
| RR | `(día, QH, tipo de redespacho)` | **I90DIA11 no tiene columna de UP ni de sentido**; publica un único precio marginal por periodo y tipo, común a subir y bajar |
| mFRR TERPRO | `(día, QH, etiqueta, sentido)` | marginal por sentido |
| mFRR TERDIR | `(día, QH, sentido, QH0/QH1)` | sólo si hay exactamente un candidato |

Un descenso a una clave menos específica degrada el dato a `PROXY_OBSERVADO`.
Una ambigüedad de precio no se promedia: se marca y no genera ingreso.

## 5. Energía de la regulación secundaria

Para el periodo anterior al 20/11/2024 la banda asignada es observable por
unidad de programación, pero **la energía activada no se publica por unidad**. El
libro I90DIA de 2023 tiene 37 hojas y ninguna la contiene. En ese periodo la
secundaria se prestaba y liquidaba por **zona de regulación**, no por unidad.

### 5.1. Ancla de sistema, verificada

```
680 x 10389 - 681 x 10390 = 718 - 719
```

En enero de 2023 la identidad se cumple con diferencia nula: +7.273.724 €.

Es imprescindible usar 10389 y 10390, que son horarios y por tanto compatibles
con 680 y 681, y no 682 y 683, que son cuartohorarios: cruzar una serie horaria
con una cuartohoraria por marca temporal toma sólo uno de los cuatro precios de
cada hora.

### 5.2. Estimación por activo

```
neto_activo_h = neto_sistema_h x banda_subir_activo_h / banda_sistema_h
```

Tres restricciones que la hacen defendible:

1. **Sólo el neto.** No se reparte entre subir y bajar. La cuota de banda no es
   la cuota de energía activada en cada sentido, y repartir por sentido produce
   precios efectivos absurdos.
2. **No se reparte entre generación y bombeo.** El resultado se imputa al activo.
3. **La cuota de banda es un proxy de participación económica**, nunca una
   asignación física. Se etiqueta `ESTIMATED_SECONDARY_NET_BAND_SHARE`.

Para Aguayo en enero de 2023 el neto estimado es **+470.414 €**.

## 6. Banda de regulación secundaria

```
MW_h     = media de la potencia asignada a subir en la hora
ingreso  = Σ_h MW_h x precio_banda_h x 1 hora
```

Tres precauciones, cada una corrige un error medido en la versión anterior:

1. **Ponderar por la duración del periodo.** El I90 histórico servido hoy está
   reexpresado a 96 cuartos de hora. Sumar filas sin ponderar multiplica por 4.
2. **Un solo sentido.** La hoja publica banda a subir y a bajar. Sumar ambas
   duplica la capacidad.
3. **Precio correcto.** El indicador 634 vale exactamente la mitad del precio de
   reserva a subir en el periodo pre-SRS, y el indicador 10463, reserva a bajar,
   vale cero, lo que confirma que la remuneración recae sobre el lado a subir.

Composición de los tres errores: 4 x 2 x 0,5 = **factor 4,00**, verificado con
tres anclas independientes (el coste del sistema publicado, el mismo cociente en
un periodo cuartohorario nativo, y el precio marginal derivado de las ofertas
aceptadas de I90DIA13).

La banda es capacidad. **No entra** en el saldo generación menos consumo ni en
los precios capturados.

## 7. Métricas derivadas

```
precio_capturado_generacion = ingreso_energia_lado_generacion / MWh_P48_generacion
coste_capturado_bombeo      = coste_energia_lado_bombeo       / MWh_P48_bombeo
spread_efectivo             = precio_capturado_generacion − coste_capturado_bombeo
EUR/MW                      = ingreso / mw_reference
EUR/MW-año                  = EUR/MW x 365,25 / dias_cubiertos
EUR/MWh-almacenamiento-año  = ingreso / almacenamiento_mwh x 365,25 / dias
ciclos_equivalentes         = MWh_generados / almacenamiento_mwh
factor_utilizacion          = MWh_generados / (P_turbinado x horas)
```

`mw_reference` es un parámetro por activo, documentado en `assets.csv`. Para
Aguayo el valor heredado es 360,4 MW, más próximo a la potencia de bombeo que a
la de turbinado; la elección desplaza todos los comparativos varios puntos y por
eso no se hereda en silencio.

## 8. Resultado frente al benchmark externo, Aguayo enero 2023

| Concepto | Valor | Clase |
|---|---|---|
| Base `P48 x PMD` | 2.094.519 € | observado |
| Intradiario de subastas | +85.927 € | observado |
| Intradiario continuo | -16.772 € | observado |
| Reequilibrio del diario | +765.402 € | observado |
| Restricciones en tiempo real | +31.117 € | observado |
| RR | +807.757 € | observado |
| mFRR terciaria | +600.437 € | observado |
| Energía de secundaria | +470.414 € | **estimado** |
| **Saldo de energía** | **4.838.801 €** | |
| Benchmark implícito 115,95 / 22,12 sobre los P48 | 4.930.971 € | externo |
| **Desviación** | **-1,9 %** | publicada, no ajustada |

`€/MW` sobre los 349,7 MW que implican las propias cifras del benchmark:
13.837 frente a 14.100, un -1,9 %.

Banda aFRR del mismo mes, componente de capacidad separado: 719.583 €.

### 8.1. Contraste externo de volúmenes, enero a mayo de 2025

Once magnitudes por mes frente a la tabla de volúmenes por mercado publicada por
el mismo analista. Coinciden todas salvo dos celdas de marzo desviadas 3,00 MWh.
La cuota de restricciones a bajar sobre la energía de ajuste reproduce también
sus porcentajes publicados: 69,4 % en abril frente al 69 %, y 79,5 % en mayo
frente al 79 %.

Ese contraste identifica además que el "Day-ahead" de su tabla de volúmenes es
el programa base de funcionamiento, mientras que el "Day-ahead" de su cuadro de
ingresos es `P48 x PMD`. Son dos cosas distintas y ambas coinciden con las
nuestras.

## 9. Lo que el motor no hace

1. No ajusta coeficientes para acercarse a un benchmark.
2. No imputa un participante de mercado a una central sin fuente estructural.
3. No inventa un parámetro técnico: lo que no está publicado queda `UNKNOWN`.
4. No mezcla capacidad con energía en el precio capturado.
5. No presenta una simulación prospectiva con la apariencia de una observación.
