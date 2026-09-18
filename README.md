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

## El proyecto original

April Collections es una PWA construida para el curso de Ingeniería de Software
II, en uso real por una vendedora por catálogo en Honduras. Registra ventas al
contado, con abono inicial o al crédito; lleva el saldo de cada clienta; controla
inventario; y agenda recordatorios de cobro.

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
```

## Estado

| Parte | Estado |
|---|---|
| Generador de datos sintéticos | ✅ 400 clientas · 3.672 ventas · 24 meses |
| Carga a Supabase | ✅ 18.668 filas, idempotente |
| ETL analítico | ✅ 2.188 ventas fiadas · 25,7% mora · 0 nulos |
| EDA | ✅ `notebooks/01_eda.ipynb` · 8 figuras |
| Modelo de riesgo de mora | ⬜ pendiente |
| Proyección de ventas | ⬜ pendiente |
| Dashboard | ⬜ pendiente |
| Documento PDF | ⬜ pendiente |
