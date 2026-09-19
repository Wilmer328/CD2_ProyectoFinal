# April Collections — Ciencia de Datos II

Componente de Ciencia de Datos sobre **April Collections**, una aplicación de
gestión de ventas por catálogo. Predice el riesgo de mora de las clientas y
proyecta las ventas mensuales, para que la dueña decida a quién fiar, cuánto
pedir de abono inicial y cuánto inventario comprar.

**Proyecto final · Ciencia de Datos II · CEUTEC · Sección 77 · Grupo 5**

| Integrante | Cuenta |
|---|---|
| Kevin Jonathan Zuniga Hernández | 62451208 |
| Jose Nahun Reyes Escobar | 20011170 |
| Wilmer Josué Sánchez Gómez | 62211430 |

Docente: Ing. Naomy Zoey Ríos Reyes

## Guía de revisión — dónde está cada cosa

Para quien evalúa el proyecto. Cada pregunta lleva al archivo y la línea exacta.

### Los cuatro entregables

| Entregable | Dónde |
|---|---|
| **Documento** (13 secciones) | [`docs/documento.md`](docs/documento.md) — se lee directamente en GitHub con sus 11 figuras |
| **Dashboard** | <https://cd2proyectofinal-33tjuzgr53xy23jldsgrwu.streamlit.app/> — público, sin registro. Código en [`dashboard/app.py`](dashboard/app.py) |
| **Repositorio** | Este. Estructura más abajo |
| **Presentación** | [`docs/presentacion.html`](docs/presentacion.html) — descargar y abrir en cualquier navegador; flechas para avanzar, tecla **G** para el guion |

### ¿Dónde se calcula…?

| Pregunta | Archivo y línea |
|---|---|
| ¿Cómo se decide si una venta cayó en **mora**? | [`etl/transformar.py` L219](etl/transformar.py#L219) — `estado_pago = 1` si al llegar la fecha prometida quedaba saldo pendiente |
| ¿Cómo se calcula el **historial** de cada clienta sin mirar al futuro? | [`etl/transformar.py` L275](etl/transformar.py#L275) — `_agregar_historial()`, en orden cronológico, restando la fila actual del acumulado |
| ¿Qué **variables** entran al modelo y cuáles se excluyen por contener la respuesta? | [`etl/transformar.py` L317](etl/transformar.py#L317) — lista `COLUMNAS`, y [`modelos/metricas.json`](modelos/metricas.json) bajo `"variables"` y `"excluidas_por_fuga"` |
| ¿Dónde se **entrena** el modelo? | [`notebooks/02_riesgo_de_mora.ipynb`](notebooks/02_riesgo_de_mora.ipynb) — sección 3, celda que empieza con `modelos = {`; el modelo entrenado queda en [`modelos/riesgo_de_mora.joblib`](modelos/riesgo_de_mora.joblib) |
| ¿Dónde se calcula el **puntaje de riesgo** de cada clienta? | [`dashboard/app.py` L112](dashboard/app.py#L112) — `calcular_riesgo()`; la línea 120 ejecuta el modelo |
| ¿Dónde se decide **fiar o no fiar**? | [`dashboard/app.py` L85](dashboard/app.py#L85) — `recomendar()`: cuatro franjas, cuatro acciones |
| ¿Cómo se **proyectan** las ventas? | [`notebooks/03_proyeccion_ventas.ipynb`](notebooks/03_proyeccion_ventas.ipynb) — sección 3 compara cuatro modelos sobre meses ocultos |
| ¿Cómo se **generan** los datos sintéticos? | [`datos/generar.py`](datos/generar.py) — la fiabilidad latente de cada clienta está en `generar_clientas()` |
| ¿Cómo es la **base de datos**? | [`docs/diagrama_bd.md`](docs/diagrama_bd.md) — diagrama entidad-relación, se ve en GitHub |

### ¿Cómo verificar lo que dice el documento?

Sin conexión a nada, solo con Python:

```bash
pip install -r requirements.txt
python -m etl.verificar
```

Ejecuta 17 comprobaciones contra el dataset y el modelo versionados: que el historial no
mira al futuro (fila por fila), que ninguna columna con la respuesta entra al modelo, que la
tasa de mora es la declarada, que la línea base tiene más exactitud que el modelo y detecta
cero moras. Falla si alguna afirmación del documento no se cumple.

### Qué necesita cada cosa para ejecutarse

| Solo con Python (`pip install -r requirements.txt`) | Necesita además el `.env` con Supabase |
|---|---|
| `dashboard/app.py` · `notebooks/02_riesgo_de_mora.ipynb` · `datos/generar.py` · `etl/verificar.py` | `etl/cargar.py` · `etl/ejecutar.py` · `notebooks/01_eda.ipynb` · `notebooks/03_proyeccion_ventas.ipynb` |

Los tres notebooks están **ejecutados y con sus resultados dentro**: se leen en GitHub sin
correr nada. El `.env` solo hace falta para re-ejecutar los que consultan la base.

---

## El proyecto original

April Collections es una PWA construida para el curso de Ingeniería de Software
II, en uso real por una vendedora por catálogo en Honduras. Registra ventas al
contado, con abono inicial o al crédito; lleva el saldo de cada clienta; controla
inventario; y agenda recordatorios de cobro.

- Tablero interactivo: <https://cd2proyectofinal-33tjuzgr53xy23jldsgrwu.streamlit.app/>
- Producto en vivo: <https://www.jsanchez.site>
- Repositorio de la aplicación: <https://github.com/Wilmer328/April_Collections>

Este repositorio es **independiente** de aquel. Comparten el esquema de base de
datos —las migraciones de `supabase/migrations/` son las mismas— y nada más.

## Sobre los datos

**Los datos son sintéticos.** La aplicación lleva pocas semanas en uso y tiene
un puñado de ventas reales, insuficientes para entrenar un modelo. Y aunque
hubiera más, no se usarían: contienen nombres, DNI y teléfonos de clientas que
no consintieron aparecer en un trabajo académico.

El dataset parte de los datos de demostración de la aplicación (ficticios, en la
migración `0003`) y los amplía con un generador que simula el comportamiento del
negocio: clientas con distinta fiabilidad, categorías con distinta rotación,
estacionalidad, ventas a crédito con abonos repartidos en el tiempo. La mora
**emerge** de ese comportamiento; no se asigna al azar. Semilla fija: cualquiera
regenera exactamente el mismo dataset.

Viven en un proyecto de Supabase propio de este curso, con el esquema real de la
aplicación, para que el ETL extraiga de una base PostgreSQL de verdad.

## Estructura

```
supabase/migrations/   esquema de la base: las 8 migraciones de la aplicación
datos/                 generador del dataset sintético y diccionario de datos
etl/                   extracción desde Supabase, transformación, carga a parquet
notebooks/             EDA, modelo de mora, proyección de ventas
modelos/               modelos entrenados y sus métricas
dashboard/             aplicación Streamlit
docs/                  borradores del documento final
```

## Puesta en marcha

Requiere Python 3.14.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.ejemplo .env          # y rellenar DATABASE_URL
```

`DATABASE_URL` es la cadena de conexión del proyecto de Supabase. Está en
`.gitignore`: **nunca se sube**. Cada integrante tiene la suya.

## Cómo reproducir el análisis

```bash
python -m datos.generar      # dataset sintético, semilla fija
python -m etl.cargar         # lo sube a Supabase (idempotente)
python -m etl.ejecutar       # extrae, transforma y deja dataset.parquet
jupyter lab notebooks/       # los cuadernos
streamlit run dashboard/app.py   # el tablero
```

## Estado

| Parte | Estado |
|---|---|
| Generador de datos sintéticos | ✅ 400 clientas · 3.672 ventas · 24 meses |
| Carga a Supabase | ✅ 18.668 filas, idempotente |
| ETL analítico | ✅ 2.188 ventas fiadas · 25,7% mora · 0 nulos |
| EDA | ✅ `notebooks/01_eda.ipynb` · 8 figuras |
| Modelo de riesgo de mora | ✅ `notebooks/02_riesgo_de_mora.ipynb` · Random Forest · ROC-AUC 0,742 |
| Proyección de ventas | ✅ `notebooks/03_proyeccion_ventas.ipynb` · MAPE 14% |
| Dashboard | ✅ `dashboard/app.py` · Streamlit, 4 pestañas |
| Documento | ✅ `docs/documento.md` · 13 secciones · 5.150 palabras |
| Despliegue del tablero | ✅ Streamlit Cloud, público |
| Presentación | ✅ `docs/presentacion.html` · 18 diapositivas, mismo orden que el documento |
