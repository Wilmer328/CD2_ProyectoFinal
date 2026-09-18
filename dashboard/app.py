"""
Tablero de decisiones de April Collections.

Reúne en una sola pantalla lo que producen los cuadernos: el riesgo de mora de
cada clienta, la proyección de ventas y el estado del negocio. No calcula nada
nuevo — carga el modelo ya entrenado y el conjunto de datos ya construido, y los
traduce a decisiones.

Esa separación es deliberada. Un tablero que entrena al abrirse tarda, produce
números distintos cada vez que alguien lo recarga, y mezcla dos
responsabilidades: analizar y comunicar.

No se conecta a Supabase. Lee los archivos versionados en el repositorio, de modo
que cualquiera pueda abrirlo sin credenciales. Es también la razón por la que el
dataset y el modelo se versionan pese a ser artefactos.

USO
    streamlit run dashboard/app.py
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

RAIZ = Path(__file__).resolve().parent.parent

# Paleta de la aplicación, para que el tablero se reconozca como parte del producto.
ROSA, ROSA_OSCURO, ORO = "#c8697a", "#9e3f52", "#c9a96e"
VERDE, GRIS, CREMA = "#4a9e7a", "#7a6570", "#fdf8f4"

st.set_page_config(
    page_title="April Collections · Tablero de decisiones",
    page_icon="💎",
    layout="wide",
)


# ── Carga ─────────────────────────────────────────────────────────────────


@st.cache_data
def cargar_datos() -> pd.DataFrame:
    return pd.read_parquet(RAIZ / "datos" / "procesados" / "dataset.parquet")


@st.cache_resource
def cargar_modelo():
    return joblib.load(RAIZ / "modelos" / "riesgo_de_mora.joblib")


@st.cache_data
def cargar_metricas() -> dict:
    return json.loads((RAIZ / "modelos" / "metricas.json").read_text(encoding="utf-8"))


try:
    datos = cargar_datos()
    modelo = cargar_modelo()
    metricas = cargar_metricas()
except FileNotFoundError as error:
    st.error(
        f"Falta un archivo: `{error.filename}`\n\n"
        "Genera los artefactos antes de abrir el tablero:\n\n"
        "```\npython -m datos.generar\npython -m etl.cargar\n"
        "python -m etl.ejecutar\n```\n\n"
        "y ejecuta `notebooks/02_riesgo_de_mora.ipynb` para entrenar el modelo."
    )
    st.stop()

PREDICTORAS = metricas["variables"]
UMBRAL = metricas["umbral_recomendado"]


# ── Puntaje de riesgo ─────────────────────────────────────────────────────


def recomendar(probabilidad: float) -> str:
    """
    Traduce la probabilidad a una acción concreta.

    Los cortes no salen de la estadística sino del negocio: cuánto duele que una
    clienta no pague frente a cuánto incomoda pedirle un anticipo. El umbral
    intermedio es el que optimizó F1 en la validación; los otros dos se fijaron
    para que las franjas sean accionables.
    """
    if probabilidad >= 0.60:
        return "Vender solo al contado"
    if probabilidad >= UMBRAL:
        return "Pedir abono inicial alto"
    if probabilidad >= 0.25:
        return "Fiar con recordatorio"
    return "Fiar con normalidad"


COLOR_ACCION = {
    "Fiar con normalidad": VERDE,
    "Fiar con recordatorio": ORO,
    "Pedir abono inicial alto": ROSA,
    "Vender solo al contado": ROSA_OSCURO,
}


@st.cache_data
def calcular_riesgo(_datos: pd.DataFrame) -> pd.DataFrame:
    """
    Riesgo actual de cada clienta.

    Se toma su última venta fiada como situación vigente: es la que lleva el
    historial más completo y refleja cómo se comporta hoy.
    """
    ultima = _datos.sort_values("fecha").groupby("cliente_id").tail(1).copy()
    ultima["probabilidad_mora"] = modelo.predict_proba(ultima[PREDICTORAS])[:, 1]
    ultima["recomendacion"] = ultima["probabilidad_mora"].apply(recomendar)

    return ultima.sort_values("probabilidad_mora", ascending=False)


riesgo = calcular_riesgo(datos)


# ── Cabecera ──────────────────────────────────────────────────────────────

st.title("💎 April Collections · Tablero de decisiones")
st.caption(
    "Componente de Ciencia de Datos · Grupo 5 · Sección 77 — "
    "Kevin Zúniga · Nahún Reyes · Wilmer Sánchez"
)

st.warning(
    "**Los datos son sintéticos.** Se generaron con la estructura real de la aplicación "
    "para no exponer información de clientas reales. El modelo y las conclusiones son "
    "válidos como metodología; los números concretos no describen a ninguna persona.",
    icon="⚠️",
)

pestanas = st.tabs([
    "🎯 Riesgo por clienta",
    "📈 Proyección de ventas",
    "📊 Estado del negocio",
    "🔬 Calidad del modelo",
])


# ══ 1. Riesgo por clienta ═════════════════════════════════════════════════

with pestanas[0]:
    st.subheader("A quién fiar, y bajo qué condiciones")
    st.markdown(
        "Cada clienta recibe un **puntaje de riesgo** de no pagar a tiempo su próxima compra "
        "fiada, y una acción recomendada. **Es una ayuda para priorizar, no un veredicto**: "
        "la decisión final la toma quien conoce a la persona."
    )

    reparto = riesgo["recomendacion"].value_counts()
    columnas = st.columns(4)

    for columna, accion in zip(columnas, COLOR_ACCION):
        cuantas = int(reparto.get(accion, 0))
        with columna:
            st.metric(accion, f"{cuantas} clientas",
                      f"{cuantas / len(riesgo):.0%} del total")

    st.divider()

    izquierda, derecha = st.columns([2, 1])

    with derecha:
        st.markdown("**Filtrar**")
        acciones = st.multiselect(
            "Acción recomendada", list(COLOR_ACCION), default=list(COLOR_ACCION),
            label_visibility="collapsed",
        )
        minimo = st.slider("Riesgo mínimo", 0.0, 1.0, 0.0, 0.05)
        buscar = st.text_input("Buscar clienta", placeholder="nombre…")

        st.plotly_chart(
            px.pie(
                values=reparto.values, names=reparto.index, hole=0.45,
                color=reparto.index, color_discrete_map=COLOR_ACCION,
            ).update_layout(showlegend=False, height=260, margin=dict(t=10, b=10)),
            use_container_width=True,
        )

    with izquierda:
        filtrado = riesgo[
            riesgo["recomendacion"].isin(acciones)
            & (riesgo["probabilidad_mora"] >= minimo)
        ]

        if buscar:
            filtrado = filtrado[
                filtrado["cliente_nombre"].str.contains(buscar, case=False, na=False)
            ]

        st.markdown(f"**{len(filtrado)} clientas**")

        st.dataframe(
            filtrado[[
                "cliente_nombre", "probabilidad_mora", "recomendacion",
                "historial_mora", "compras_previas", "total_centavos",
            ]].rename(columns={
                "cliente_nombre": "Clienta",
                "probabilidad_mora": "Riesgo",
                "recomendacion": "Recomendación",
                "historial_mora": "Atrasos previos",
                "compras_previas": "Compras",
                "total_centavos": "Última compra",
            }).assign(**{
                "Última compra": lambda d: d["Última compra"] / 100,
                # ProgressColumn aplica el formato al valor CRUDO, no lo
                # interpreta como proporcion: con 0,79 y formato "%.0f%%"
                # escribia «1%» mientras la barra se dibujaba al 79%. Se escala
                # a 0-100 para que el numero y la barra digan lo mismo.
                "Riesgo": lambda d: d["Riesgo"] * 100,
            }),
            column_config={
                "Riesgo": st.column_config.ProgressColumn(
                    "Riesgo", format="%.0f%%", min_value=0, max_value=100),
                "Última compra": st.column_config.NumberColumn(format="L %.2f"),
            },
            hide_index=True,
            use_container_width=True,
            height=460,
        )

    st.info(
        "**Cómo leer esto.** El riesgo mide qué tan parecida es esta clienta a las que "
        "históricamente no pagaron a tiempo. Un riesgo alto no significa que vaya a fallar: "
        "significa que conviene protegerse pidiendo un anticipo mayor o agendando el cobro.",
        icon="💡",
    )

    st.caption(
        f"**El puntaje sirve para ordenar, no para leerlo como probabilidad literal.** "
        f"El modelo se entrenó con `class_weight=\"balanced\"`, que reequilibra las clases "
        f"al 50/50 para que no aprenda a decir «paga» siempre. Ese ajuste desplaza los "
        f"puntajes hacia arriba: el promedio es {riesgo['probabilidad_mora'].mean():.0%} "
        f"mientras la mora real del histórico es {datos['estado_pago'].mean():.0%}. "
        f"Comparar clientas entre sí es válido; leer un 45% como «45 de cada 100 fallarán», no."
    )


# ══ 2. Proyección ═════════════════════════════════════════════════════════

with pestanas[1]:
    st.subheader("Cuánto se espera vender, y cuánto comprar")

    @st.cache_data
    def serie_mensual(_datos: pd.DataFrame) -> pd.Series:
        """Ventas por mes. Solo las fiadas: es lo que hay en el dataset."""
        por_mes = _datos.groupby(_datos["fecha"].dt.to_period("M"))["total_centavos"].sum() / 100
        por_mes.index = por_mes.index.to_timestamp()
        return por_mes

    serie = serie_mensual(datos)

    # Modelo ingenuo: el que gano la validacion del cuaderno 3. Repetir el
    # ultimo mes es dificil de batir en una serie corta y en crecimiento.
    MESES = 3
    futuro = pd.date_range(serie.index[-1], periods=MESES + 1, freq="MS")[1:]
    proyeccion = pd.Series([serie.iloc[-1]] * MESES, index=futuro)

    # Margen a partir del error real sobre meses ocultos, no de un intervalo teorico.
    margen = serie.diff().abs().tail(6).mean()

    figura = go.Figure()
    figura.add_trace(go.Scatter(
        x=serie.index, y=serie.values, name="Histórico",
        line=dict(color=ROSA_OSCURO, width=2.5), mode="lines+markers"))
    figura.add_trace(go.Scatter(
        x=[serie.index[-1], *futuro], y=[serie.iloc[-1], *proyeccion.values],
        name="Proyección", line=dict(color=ORO, width=2.5, dash="dash"),
        mode="lines+markers"))
    figura.add_trace(go.Scatter(
        x=[*futuro, *futuro[::-1]],
        y=[*(proyeccion + margen).values, *(proyeccion - margen).clip(lower=0).values[::-1]],
        fill="toself", fillcolor="rgba(201,169,110,0.2)",
        line=dict(width=0), name="Margen de error", hoverinfo="skip"))
    figura.update_layout(
        height=420, yaxis_title="Lempiras vendidos (ventas fiadas)",
        hovermode="x unified", margin=dict(t=20))

    st.plotly_chart(figura, use_container_width=True)

    columnas = st.columns(MESES)
    for columna, (fecha, valor) in zip(columnas, proyeccion.items()):
        with columna:
            st.metric(
                fecha.strftime("%B %Y").capitalize(),
                f"L {valor:,.0f}",
                f"entre L {max(0, valor - margen):,.0f} y L {valor + margen:,.0f}",
                delta_color="off",
            )

    st.divider()
    st.markdown("### Estacionalidad observada")

    por_mes_del_anio = (
        datos.groupby(datos["fecha"].dt.month)["total_centavos"].sum() / 100
    )
    meses_nombre = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
                    "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    por_mes_del_anio.index = [meses_nombre[m - 1] for m in por_mes_del_anio.index]

    st.plotly_chart(
        px.bar(
            x=por_mes_del_anio.index, y=por_mes_del_anio.values,
            labels={"x": "", "y": "Lempiras acumulados"},
            color=por_mes_del_anio.values,
            color_continuous_scale=[[0, "#e8d8dc"], [1, ROSA_OSCURO]],
        ).update_layout(height=320, coloraxis_showscale=False, margin=dict(t=20)),
        use_container_width=True,
    )

    st.warning(
        "**Dos años de historial son pocos para proyectar con estacionalidad.** Cada mes "
        "del año está representado por dos observaciones. En la validación, los modelos "
        "que intentaron aprovechar la estacionalidad quedaron por detrás del que "
        "simplemente repite el último mes. La proyección sirve para dimensionar una "
        "compra, no como cifra exacta.",
        icon="⚠️",
    )


# ══ 3. Estado del negocio ═════════════════════════════════════════════════

with pestanas[2]:
    st.subheader("Qué está pasando con las ventas fiadas")

    facturado = datos["total_centavos"].sum() / 100
    cobrado = datos["cobrado_al_corte"].sum() / 100
    pendiente = datos["pendiente_al_corte"].sum() / 100

    columnas = st.columns(4)
    columnas[0].metric("Fiado en el periodo", f"L {facturado:,.0f}")
    columnas[1].metric("Cobrado a tiempo", f"L {cobrado:,.0f}", f"{cobrado / facturado:.1%}")
    columnas[2].metric("Pendiente al vencer", f"L {pendiente:,.0f}",
                       f"{pendiente / facturado:.1%}", delta_color="inverse")
    columnas[3].metric("Ventas en mora", f"{datos['estado_pago'].mean():.1%}",
                       f"{int(datos['estado_pago'].sum())} de {len(datos):,}")

    st.divider()
    izquierda, derecha = st.columns(2)

    with izquierda:
        st.markdown("**Mora según atrasos previos de la clienta**")
        tramos = datos["historial_mora"].clip(upper=3)
        tabla = datos.groupby(tramos)["estado_pago"].agg(["mean", "size"])
        tabla.index = [f"{i}{'+' if i == 3 else ''} atrasos" for i in tabla.index]

        st.plotly_chart(
            px.bar(
                x=tabla.index, y=tabla["mean"] * 100,
                labels={"x": "", "y": "% en mora"},
                color=tabla["mean"], color_continuous_scale=[[0, VERDE], [1, ROSA_OSCURO]],
                text=[f"{v:.1%}" for v in tabla["mean"]],
            ).update_layout(height=340, coloraxis_showscale=False, margin=dict(t=20)),
            use_container_width=True,
        )

    with derecha:
        st.markdown("**Mora según categoría del producto**")
        por_categoria = datos.groupby("categoria_producto")["estado_pago"].agg(["mean", "size"])
        por_categoria = por_categoria[por_categoria["size"] >= 30].sort_values("mean")

        st.plotly_chart(
            px.bar(
                x=por_categoria["mean"] * 100, y=por_categoria.index, orientation="h",
                labels={"x": "% en mora", "y": ""},
                color=por_categoria["mean"],
                color_continuous_scale=[[0, VERDE], [1, ROSA_OSCURO]],
                text=[f"{v:.1%}" for v in por_categoria["mean"]],
            ).update_layout(height=340, coloraxis_showscale=False, margin=dict(t=20)),
            use_container_width=True,
        )

    st.caption(
        "Solo se muestran categorías con al menos 30 ventas: con menos, el porcentaje "
        "es ruido de muestra pequeña."
    )


# ══ 4. Calidad del modelo ═════════════════════════════════════════════════

with pestanas[3]:
    st.subheader("Qué tan bien funciona, y qué no puede hacer")

    elegido = metricas["metricas"][metricas["modelo"]]

    columnas = st.columns(4)
    columnas[0].metric("Modelo", metricas["modelo"])
    columnas[1].metric("ROC-AUC", f"{elegido['roc_auc']:.3f}")
    columnas[2].metric("Recall (moras detectadas)", f"{elegido['recall']:.1%}")
    columnas[3].metric("Precisión", f"{elegido['precision']:.1%}")

    st.divider()

    izquierda, derecha = st.columns([3, 2])

    with izquierda:
        st.markdown("**Comparación con las alternativas**")
        comparacion = pd.DataFrame(metricas["metricas"]).T
        comparacion.columns = [c.replace("_", "-").upper() for c in comparacion.columns]
        st.dataframe(
            comparacion.style.format("{:.3f}", na_rep="—"),
            use_container_width=True,
        )

        st.markdown(
            f"La **línea base** predice siempre «paga». Acierta el "
            f"{metricas['metricas']['Línea base']['exactitud']:.1%} de las veces y detecta "
            "**cero** moras. Está en la tabla a propósito: es la demostración de por qué "
            "la exactitud no puede medir este problema."
        )

    with derecha:
        st.markdown("**Cómo se evaluó**")
        st.markdown(
            f"""
- **Partición temporal**: entrenado con {metricas['ventas_entrenamiento']:,} ventas
  hasta {metricas['entrenado_hasta']}, probado con las
  {metricas['ventas_prueba']:,} posteriores.
- **Sin reparto aleatorio**: una clienta aparece varias veces, y repartir al azar
  dejaría que su futuro entrenara la predicción de su pasado.
- **Tres columnas excluidas** por contener la respuesta:
  `{'`, `'.join(metricas['excluidas_por_fuga'])}`.
            """
        )

    st.divider()
    st.markdown("### Limitaciones")

    st.markdown(
        """
1. **Los datos son sintéticos.** El modelo aprendió de un comportamiento simulado con la
   estructura real de la aplicación. Con datos reales los números cambiarán; lo que se
   traslada es la metodología, no los coeficientes.

2. **El plazo por defecto introduce un sesgo.** Cuando una venta no tuvo recordatorio
   agendado no existe fecha prometida, y se asume un plazo de 30 días — más generoso que
   los 8 o 15 que se pactan de palabra. Esas ventas aparecen con menos mora de la real.

3. **El grupo sin abono inicial no es comparable.** Se concede a quien ya goza de
   confianza, así que su baja mora refleja esa selección previa y no el efecto de no
   pedir anticipo.

4. **Esto no decide por nadie.** El tablero ordena prioridades para una persona que
   conoce a sus clientas. Negar crédito basándose en un modelo entrenado con datos
   simulados sería irresponsable, y por eso este componente **no está conectado a la
   aplicación en producción**.
        """
    )


st.divider()
st.caption(
    "April Collections · [Producto en vivo](https://www.jsanchez.site) · "
    "[Repositorio del componente de datos](https://github.com/Wilmer328/CD2_ProyectoFinal)"
)
