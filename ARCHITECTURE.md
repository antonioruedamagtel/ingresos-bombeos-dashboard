# ARCHITECTURE.md

## 1. Principio de separación

```
        FUENTE                PARSER              DOMINIO            MOTOR              QA               INTERFAZ
   ┌──────────────┐     ┌──────────────┐    ┌─────────────┐   ┌──────────────┐   ┌────────────┐   ┌────────────┐
   │ e·sios       │     │ i90_parser   │    │ assets      │   │ physical     │   │ gates      │   │ dashboard  │
   │ archive 34   │────►│ (xls/xlsx/   │───►│ aliases     │──►│ energy       │──►│ coverage   │──►│ 8 pestañas │
   │ indicadores  │     │  csv)        │    │ markets     │   │ balancing    │   │ quality    │   │ CLI        │
   │ OMIE público │────►│ omie_parsers │    │ components  │   │ afrr         │   │ calibration│   │            │
   └──────────────┘     └──────────────┘    └─────────────┘   │ forecast     │   └────────────┘   └────────────┘
                                                              └──────────────┘
          RAW                 NORMALIZED                                          ANALYTICS
   ficheros temporales   parquet por día/fuente                            parquet + espejo CSV
```

Cada capa sólo conoce a la anterior. El motor económico no sabe de HTTP ni de
Excel; la interfaz no sabe de mercados ni de precios, sólo lee `analytics`.

## 2. Estructura del proyecto

```
ingresos_bombeos_v2/
├── cli.py                     interfaz de línea de comandos
├── run_dashboard.py           lanzador del cuadro de mando
├── config/
│   ├── assets.csv             catálogo de centrales
│   └── future_chr_template.csv plantilla para CHR futuras
├── ib/
│   ├── util/
│   │   ├── timeframe.py       Europe/Madrid, DST, granularidad variable
│   │   └── grid.py            rejilla canónica (día, cuarto de hora)
│   ├── sources/
│   │   ├── http.py            sesión resiliente, retry, backoff, timeout
│   │   ├── esios_archive.py   archivo I90DIA, id 34
│   │   ├── esios_indicators.py indicadores con caché
│   │   └── omie_files.py      descargas públicas de OMIE, sin token
│   ├── parsers/
│   │   ├── i90_parser.py      xls, xlsx y csv; granularidad deducida por hoja
│   │   └── omie_parsers.py    PDBC, PIBCI, PIBCIC, TRADES, MARGINAL*
│   ├── domain/
│   │   ├── assets.py, aliases.py, markets.py, revenue_components.py
│   ├── engines/
│   │   ├── physical_program_engine.py   P48, PBF, cierre de volúmenes
│   │   ├── energy_revenue_engine.py     base diario, IDA, MIC
│   │   ├── balancing_revenue_engine.py  RT, reequilibrio, RR, mFRR
│   │   ├── afrr_engine.py               banda y energía de secundaria
│   │   └── forecast_engine.py           despacho óptimo y escenarios
│   ├── repositories/
│   │   ├── raw_cache.py       LOW-DISK y caché diaria reanudable
│   │   └── processed_store.py capa analytics en parquet
│   ├── qa/
│   │   ├── reconciliation.py  puertas de control
│   │   ├── quality_flags.py   cobertura y trazabilidad
│   │   └── calibration.py     benchmarks externos
│   ├── ui/
│   │   ├── theme.py           paleta validada y layout
│   │   └── dashboard.py       ocho pestañas
│   └── pipeline.py            orquestación
└── tests/                     26 pruebas, sin red
```

## 3. Rejilla temporal canónica

La clave de cruce de todo el sistema es `(día, cuarto de hora físico)`, no el
timestamp local.

Motivo: en el día de veinticinco horas la hora repetida produce dos timestamps
naive idénticos y cualquier merge se abre en abanico. El número de periodo en
orden físico es unívoco en los tres tipos de día: 92, 96 y 100 cuartos de hora.

Toda magnitud se lleva a esa rejilla antes de operar:

| Magnitud | Conversión desde tabla horaria |
|---|---|
| Energía en MWh | se reparte entre los cuatro cuartos |
| Potencia en MW | se replica |
| Precio en €/MWh o €/MW | se replica |

## 4. Flujo de datos

```
1. ingest    e·sios archive 34 ──► parseo selectivo de 12 hojas ──► parquet diario ──► borrado del raw
2. build     parquet diario + OMIE ──► motores ──► detalle trazable ──► analytics
3. qa        puertas: volumen, signo nativo, TRADES vs PIBCIC, cobertura
4. dashboard analytics ──► ocho pestañas
```

La ingesta es reanudable: nunca se escribe un checkpoint para un día que falló,
y el raw sólo se borra tras verificar la caché compacta.

## 5. Política de datos

| Capa | Formato | Contenido | Vida |
|---|---|---|---|
| RAW | ficheros originales | libros I90, zip de OMIE | temporal, se borra tras verificar |
| NORMALIZED | parquet particionado por año y mes | formato largo del I90, indicadores | persistente |
| ANALYTICS | parquet más espejo CSV | detalle de ingresos, cuadres, calidad | persistente |

No se introduce base SQL: el volumen no lo justifica y el parquet particionado
cubre las consultas del cuadro de mando. El espejo CSV mantiene compatibilidad
durante la transición desde la versión anterior.

## 6. Estados de resiliencia

`NOT_AVAILABLE_YET`, `DOWNLOAD_ERROR`, `PARSE_ERROR`, `MISSING_PRICE`,
`AMBIGUOUS_PRICE`, `OBSERVADO`, `PROXY_OBSERVADO`, `ESTIMADO`, `FORECAST`.

Un día reciente ausente del I90 no es un fallo: la publicación lleva unos
noventa días de retraso y se marca `NOT_AVAILABLE_YET`.

## 7. Decisiones técnicas y por qué

| Decisión | Alternativas | Razón |
|---|---|---|
| Clave (día, cuarto de hora) | timestamp naive, timestamp con zona | única sin ambigüedad en días de 23 y 25 horas |
| Parquet, sin SQL | SQLite, Postgres | volumen moderado, lectura columnar suficiente, cero operación |
| Programación lineal con HiGHS vía scipy | PuLP con CBC, Pyomo, OR-Tools | sin dependencia extra, resuelve un año horario en decenas de milisegundos; con pérdidas de ciclo positivas la relajación lineal nunca bombea y turbina a la vez, de modo que las binarias sólo hacen falta si se imponen mínimos técnicos |
| Dash | React, Streamlit | continuidad con la herramienta existente, sin ganancia sustancial en migrar |
| Estrategias de cruce de precio declarativas | fallbacks implícitos | la estrategia que casó queda registrada en el dato, así una cobertura nula se diagnostica mirando la tabla |
