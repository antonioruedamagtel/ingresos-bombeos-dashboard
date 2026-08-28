# INGRESOS BOMBEOS · Dashboard v1.0

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB)](https://www.python.org/)
[![Licencia MIT](https://img.shields.io/badge/licencia-MIT-green)](LICENSE)

Dashboard local y auditable para reconstruir los ingresos de centrales de
bombeo españolas y explorar proyectos futuros mediante escenarios técnicos y
económicos. El repositorio **no contiene tokens ni credenciales**.

## Demo pública sin instalación

Abre la **[demo interactiva en GitHub Pages](https://antonioruedamagtel.github.io/ingresos-bombeos-dashboard/)**.
Incluye un snapshot agregado de las ocho centrales entre enero de 2023 y abril
de 2026, además de un simulador de potencia, almacenamiento, eficiencias y
costes que se ejecuta íntegramente en el navegador. No requiere token ni envía
datos a un servidor.

La demo es educativa: los históricos siguen la metodología del repositorio y
los escenarios futuros son orientativos, no una oferta de mercado ni una
previsión financiera garantizada.

Herramienta de reconstrucción del *revenue stack* de centrales hidroeléctricas
reversibles españolas a partir exclusivamente de datos públicos de OMIE y de
REE / e·sios, con trazabilidad de cada euro hasta su fichero, su volumen, su
precio y su fórmula.

Incluye además un motor prospectivo que permite dar de alta una CHR todavía no
construida, mediante configuración y sin tocar código, y estimar sus ingresos
por *backtest* sintético sobre precios históricos reales y por escenarios.

## Puesta en marcha rápida

1. Descomprime la carpeta en una ubicación local.
2. Haz doble clic en `ABRIR_DASHBOARD.bat`.
3. La primera ejecución crea un entorno aislado e instala las dependencias; al
   terminar se abre `http://127.0.0.1:8050/`.
4. Mantén abierta la ventana de terminal mientras uses el dashboard.

El paquete conserva una muestra local reproducible de enero de 2023. La demo
web añade un extracto agregado hasta abril de 2026 para explorar el histórico
y probar el simulador sin instalar Python. Para una decisión real deben
revisarse las puertas de calidad y las hipótesis del proyecto concreto.

## Contenido

| Documento | Qué contiene |
|---|---|
| `AUDIT_REPORT.md` | auditoría crítica de la versión anterior, con la matriz por componente |
| `ARCHITECTURE.md` | arquitectura, flujo de datos y decisiones técnicas |
| `REVENUE_METHODOLOGY.md` | fórmula de cada mercado y resultados frente al benchmark |
| `VALIDATION_REPORT.md` | alcance de la validación, pruebas superadas y cautelas |
| `CHART_MAP.md` | objetivo, métrica, dimensión y fuente de cada visual |
| `config/assets.csv` | catálogo de centrales |
| `config/future_chr_template.csv` | plantilla para una CHR futura |

## 1. Instalación

Requiere Python 3.10 o superior. `ABRIR_DASHBOARD.bat` automatiza estos pasos en
Windows. Instalación manual:

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

En Linux o macOS: `source .venv/bin/activate`.

## 2. Configuración

Copia `.env.example` a `.env` y pon tu clave personal de e·sios:

```
ESIOS_API_KEY=tu_token
```

Ese token es **exclusivo de e·sios**. Las descargas de OMIE son públicas y no
usan token, clave ni certificado: no traslades nunca la clave a una petición de
OMIE.

### Cómo solicitar el token de e·sios

1. Abre la [documentación oficial de la API e·sios](https://api.esios.ree.es/).
2. Selecciona **Personal token request** y completa el formulario de REE.
3. Cuando recibas la clave personal, copia `.env.example` como `.env`.
4. Sustituye únicamente el valor de `ESIOS_API_KEY` dentro de `.env`.

El archivo `.env` está excluido mediante `.gitignore`: no lo subas, no lo
pegues en una incidencia y no lo compartas en capturas o logs. Si una clave se
publica accidentalmente, revócala o solicita su sustitución.

El dashboard y la muestra de enero de 2023 pueden consultarse **sin token**. La
clave sólo es necesaria para descargar o actualizar los datos procedentes de
e·sios. Consulta la guía ampliada en
[`docs/CONFIGURACION_TOKEN_ESIOS.md`](docs/CONFIGURACION_TOKEN_ESIOS.md).

## 3. Actualización de datos y ejecución

```bat
python cli.py ingest --start 2023-01-01 --end 2023-01-31
python cli.py build  --start 2023-01-01 --end 2023-01-31
python cli.py qa     --start 2023-01-01 --end 2023-01-31
python run_dashboard.py
```

Para periodos largos puede utilizarse la ingesta mensual reanudable, que pide
un paquete por mes y mantiene la misma caché diaria validada:

```bat
python scripts/ingest_i90_monthly.py --start 2023-01-01 --end 2026-04-30
```

El cuadro de mando queda en `http://127.0.0.1:8050/`.

`ingest` descarga el I90DIA día a día, parsea sólo las doce tablas necesarias,
escribe una caché compacta en parquet, la verifica y **sólo entonces** borra el
fichero original. Es reanudable: si se corta la red, vuelve a lanzarlo y sólo
procesará los días pendientes. Para liberar espacio manualmente:

```bat
python cli.py purge-raw
```

Un día reciente que no aparezca no es un error. El I90DIA se publica con unos
noventa días de retraso y el sistema lo marca como `NOT_AVAILABLE_YET`.

## 4. Añadir una central

Añade una fila a `config/assets.csv`. Campos mínimos imprescindibles:

| Campo | Significado |
|---|---|
| `asset_id`, `asset` | identificador y nombre |
| `up_generation`, `up_pumping` | códigos de unidad de programación, varios separados por `\|` |
| `mw_reference` | denominador de los €/MW; documenta cuál es |
| `include_default` | 1 para incluirla en el universo por defecto |

Los alias importan. Una central puede tener códigos distintos en OMIE y en el
I90 y códigos distintos según el periodo. Ejemplos reales ya recogidos: Ip
aparece como `IPG` e `IPB` en OMIE y como `CHIPG` y `CHIPB` en el I90; La Muela
aparece como `MUEL` en OMIE y como `MUEG` en configuraciones históricas. Si
faltan alias, el cierre de volúmenes lo detecta de inmediato.

Todo campo técnico sin fuente pública verificada debe quedar como `UNKNOWN`. El
motor no inventa parámetros.

## 5. Simular un bombeo futuro

En la pestaña **Previsión** no hace falta editar archivos. Introduce:

- potencia de turbinado y bombeo (MW);
- almacenamiento como MWh eléctricos útiles, o bien volumen útil de balsa
  (hm³) y salto neto (m);
- eficiencias, disponibilidad y máximo de ciclos equivalentes diarios;
- OPEX variable y fijo;
- nivel de captura de servicios de ajuste y crecimientos anuales;
- horizonte de proyección.

La conversión de balsa usa energía potencial `ρ·g·V·H`; la capacidad eléctrica
útil aplica después la eficiencia de turbinado. También se puede ejecutar una
simulación básica desde la línea de comandos:

```bat
python cli.py forecast --mw 500 --hours 8 --rte 0.78 --scenario Base
```

El motor hace lo siguiente, en este orden:

* **Nivel 1** selecciona centrales comparables por similitud física.
* **Nivel 2** aplica la configuración de la CHR futura a los precios históricos
  reales que haya en el almacén, produciendo un ingreso sintético histórico.
* **Nivel 3** optimiza el despacho con restricciones físicas: potencia máxima de
  turbinado y de bombeo, almacenamiento máximo y mínimo, rendimiento, rampas,
  disponibilidad, ciclos diarios, estado inicial y final, y prohibición de
  simultaneidad. Si los precios negativos lo exigen, activa una formulación
  entera para que nunca bombee y turbine en el mismo periodo.
* **Nivel 4** añade servicios de ajuste por escenario conservador, central o
  alto, escalando desde la mediana de los comparables observados y nunca desde
  una sola central.
* **Nivel 5** presenta Low / Base / High, desglose de arbitraje, SSAA y OPEX,
  métricas por MW y por MWh almacenado, y una tabla anual auditable.

La cifra es una **simulación de escenarios**, no una valoración bancaria ni una
garantía. No incluye CAPEX, financiación, impuestos, hidrología, restricciones
ambientales, peajes, indisponibilidades no parametrizadas ni una curva externa
de precios futura. Los SSAA parten de la mediana anualizada observada en el
periodo elegido, modulada por el escenario del usuario.

## 6. Cómo interpretar los resultados

**Distingue siempre la clase de dato.** Cada fila del detalle lleva una:

| Clase | Significado |
|---|---|
| `OBSERVADO` | volumen y precio publicados, cruzados por la clave documentada del mercado |
| `PROXY_OBSERVADO` | precio publicado pero no específico de esa unidad |
| `ESTIMADO` | imputado con un modelo. No es una observación |
| `FORECAST` | prospectivo |

**Distingue energía de capacidad.** La banda de regulación secundaria es
remuneración de capacidad: no entra en el saldo generación menos consumo ni en
los precios capturados. Aparece como línea propia.

**Mira siempre la pestaña Calibración / QA antes de usar una cifra.** Cuatro
puertas deben estar en verde: cierre de volúmenes, signo nativo, control de
TRADES frente a PIBCIC y cobertura de precio. Una cobertura de precio del cero
por ciento en desvíos e indisponibilidad no es un fallo: esa energía se publica
pero su precio no.

**El residuo frente a un benchmark externo se publica, no se ajusta.** Y antes
de comparar, comprueba qué mide exactamente el benchmark: si incluye o no
servicios de ajuste cambia por completo la lectura.

## 7. Resolución de errores

| Síntoma | Causa probable | Solución |
|---|---|---|
| `Falta ESIOS_API_KEY` | no existe `.env` o está vacío | copia `.env.example` y pon el token |
| Token no autorizado, HTTP 401 o 403 | clave caducada | renuévala en e·sios |
| Un día no aparece | publicación a noventa días | espera; se marca `NOT_AVAILABLE_YET` |
| `No space left on device` | raw acumulado | `python cli.py purge-raw` |
| Cobertura de precio baja en un mercado | clave de cruce o alias | revisa la columna `price_join` del detalle |
| Cierre de volúmenes no cierra en una central | falta un alias de unidad | añádelo a `config/assets.csv` |
| El cuadro de mando aparece vacío | no se ha ejecutado `build` | lanza `ingest` y después `build` |
| Aviso de servidor de desarrollo | Dash en local | es normal en uso local; para despliegue usa un WSGI |

## 8. Pruebas

```bat
python -m pytest tests -q
```

La versión 1.0 contiene cincuenta y tres controles reproducibles **sin red**,
sobre cachés incluidas en
`tests/data`. Conservan como regresiones doradas: los días de 23, 24 y 25 horas
con 92, 96 y 100 periodos; la granularidad mixta dentro del mismo libro I90; el
signo nativo de P48; la cobertura total del precio de RR; el factor cuatro de la
banda aFRR; la igualdad de TRADES por duración con PIBCIC al MWh; el cierre de
volúmenes de toda la flota; los precios capturados de Aguayo en enero de 2023;
el cambio de granularidad del intradiario de OMIE del 19/03/2025; el ancla de
sistema de la energía de secundaria; y el contraste de once magnitudes por cinco
meses de 2025 contra una tabla de volúmenes publicada por un tercero. Se añaden
controles de conversión balsa–MWh, SOC final exacto, ciclos diarios,
reconciliación de escenarios y exclusión mutua con precios negativos.

**Defecto abierto conocido:** la identidad de volúmenes no cierra en los días de
cambio horario. El sistema los detecta y marca el periodo como no validado. Ver
la sección 13 de `AUDIT_REPORT.md`.

## 9. Fuentes públicas principales

- [OMIE · precios horarios del mercado diario](https://www.omie.es/en/file-access-list?dir=Precios+horarios+del+mercado+diario+en+Espa%C3%B1a&parents%5B0%5D=%2F&parents%5B1%5D=Mercado+Diario&parents%5B2%5D=Precios&realdir=marginalpdbc)
- [OMIE · modelo de ficheros públicos](https://www.omie.es/es/publication/modelo-de-ficheros-para-la-distribucion-publica-de-informacion-del-mercado-de)
- [API e·sios · documentación](https://api.esios.ree.es/)

Las fórmulas, claves de cruce y clases de dato están detalladas en
`REVENUE_METHODOLOGY.md`; la evidencia de calibración, en
`VALIDATION_REPORT.md`.

## 10. Seguridad y contribuciones

- Nunca abras un *pull request* que contenga `.env`, tokens o credenciales.
- Ejecuta `VALIDAR.bat` en Windows o `python -m pytest tests -q` antes de
  proponer cambios.
- Lee [`SECURITY.md`](SECURITY.md) para comunicar una posible exposición de
  credenciales sin publicarla en una incidencia.
- El código se distribuye bajo [licencia MIT](LICENSE). Las fuentes de datos
  conservan sus propias condiciones de uso y atribución.
