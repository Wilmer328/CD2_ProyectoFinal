"""
Transformacion: de las tablas operativas al dataset analitico.

Es la «T» del ETL y la parte donde se decide si el modelo vale algo. Aqui se
construye la variable objetivo y las variables predictoras, y hay dos errores
clasicos que se evitan a proposito. Los dos son faciles de cometer y los dos
producen modelos que parecen excelentes y no sirven.

─── ERROR 1: ETIQUETAR VENTAS QUE TODAVIA NO VENCEN ───────────────────────

Una venta de hace tres dias con promesa a treinta no esta en mora: es que aun
no le toca pagar. Marcarla como «puntual» seria afirmar algo que nadie sabe.

Se EXCLUYEN del dataset las ventas cuya fecha de corte todavia no ha pasado.
En estadistica de credito esto se llama censura a la derecha, y es una de las
razones por las que un modelo de riesgo entrenado sin cuidado sobrestima lo
bien que paga la gente: las ventas recientes, que aun no han podido fallar,
entran contadas como buenas.

─── ERROR 2: FUGA DE INFORMACION (data leakage) ───────────────────────────

El historial de mora de una clienta tiene que contar solo las moras
ANTERIORES a la venta que se esta evaluando. Si se le pasa el total de moras
que tuvo en toda su vida, el modelo esta viendo el futuro: para predecir la
venta de marzo estaria usando la mora de agosto.

Un modelo asi saca metricas altisimas en las pruebas y falla en produccion,
porque el dia que hay que decidir si fiar, ese futuro todavia no existe.

Por eso el historial se calcula recorriendo las ventas de cada clienta EN
ORDEN CRONOLOGICO, acumulando solo lo ya ocurrido. Lo mismo para cuantas
compras llevaba y cuanto habia gastado.

─── LA VARIABLE OBJETIVO ──────────────────────────────────────────────────

    estado_pago = 1 (mora)  si al llegar la fecha de corte la venta todavia
                            tenia saldo pendiente
                = 0 (puntual) si ya estaba saldada

La fecha de corte es la que la clienta prometio, guardada en el recordatorio.
Cuando no se agendo recordatorio no hay promesa registrada y se usa un plazo
de 30 dias desde la venta.

Eso introduce un sesgo conocido y hay que decirlo: 30 dias es mas generoso que
los 8 o 15 que se prometen de palabra, asi que las ventas sin recordatorio
salen con menos mora de la real. No se puede corregir —el dato no existe— pero
si se puede declarar, y `tuvo_recordatorio` entra como variable para que el
modelo pueda tenerlo en cuenta.

Las ventas al contado quedan fuera: se pagan en el acto y no pueden entrar en
mora. El modelo responde «¿esta clienta pagara lo que le fie?», y esa pregunta
solo existe cuando se fia.

USO
    python -m etl.transformar
"""

from __future__ import annotations

import numpy as np
import pandas as pd

#: Plazo que se asume cuando no hubo recordatorio con fecha prometida.
PLAZO_POR_DEFECTO = 30

#: Tolerancia en centavos al comparar lo pagado con el total. Evita marcar en
#: mora una venta a la que le faltan cincuenta centavos por un redondeo.
TOLERANCIA = 100


def totales_por_venta(venta_items: pd.DataFrame) -> pd.DataFrame:
    """
    Total y costo de cada venta, sumando sus lineas.

    El total no se guarda en la base a proposito: es la suma de las lineas y
    guardarlo abriria la puerta a que quedara desincronizado. Se calcula aqui,
    igual que lo hace la aplicacion.
    """
    lineas = venta_items.assign(
        importe=venta_items["precio_centavos"] * venta_items["cantidad"],
        costo=venta_items["costo_centavos"] * venta_items["cantidad"],
    )

    return lineas.groupby("venta_id").agg(
        total_centavos=("importe", "sum"),
        costo_centavos=("costo", "sum"),
        articulos=("cantidad", "sum"),
        lineas=("venta_id", "size"),
    )


def categoria_principal(venta_items: pd.DataFrame, productos: pd.DataFrame) -> pd.Series:
    """
    La categoria que mas peso tiene en cada venta, por importe.

    Una venta puede mezclar joyeria y perfumes; se toma la que domina, que es
    la que caracteriza la compra.
    """
    lineas = venta_items.merge(
        productos[["id", "categoria"]].rename(columns={"id": "producto_id"}),
        on="producto_id",
        how="left",
    )

    lineas["importe"] = lineas["precio_centavos"] * lineas["cantidad"]
    lineas["categoria"] = lineas["categoria"].fillna("Sin categoria")

    por_categoria = lineas.groupby(["venta_id", "categoria"])["importe"].sum()

    return por_categoria.reset_index().sort_values("importe").groupby("venta_id")["categoria"].last()


def construir(tablas: dict[str, pd.DataFrame], hoy: pd.Timestamp | None = None) -> pd.DataFrame:
    """
    Construye el dataset analitico a partir de las tablas operativas.

    :param hoy: fecha de referencia para decidir que ventas ya vencieron. Por
        defecto, la fecha de la ultima venta registrada — no la fecha real de
        ejecucion, para que el dataset no cambie segun el dia en que se corra.
    """
    ventas = tablas["ventas"].copy()
    abonos = tablas["abonos"]
    recordatorios = tablas["recordatorios"]

    if hoy is None:
        hoy = ventas["fecha"].max()

    # ── Solo las ventas fiadas ──
    # Al contado se paga en el acto: no puede haber mora, y meterlas diluiria
    # el problema con miles de casos triviales.
    ventas = ventas[ventas["tipo_pago"].isin(["credito", "abono"])].copy()

    # ── Total de cada venta ──
    totales = totales_por_venta(tablas["venta_items"])
    ventas = ventas.merge(totales, left_on="id", right_index=True, how="left")

    # Una venta sin lineas no tiene importe que cobrar: no es analizable.
    ventas = ventas[ventas["total_centavos"].notna() & (ventas["total_centavos"] > 0)]

    # ── Fecha de corte ──
    # La que prometio la clienta, si se agendo recordatorio. Si hubo varios
    # para la misma venta, manda el ultimo: es la promesa vigente.
    promesa = (
        recordatorios.sort_values("fecha_prometida")
        .groupby("venta_id")["fecha_prometida"]
        .last()
    )

    ventas = ventas.merge(
        promesa.rename("fecha_prometida"), left_on="id", right_index=True, how="left"
    )

    ventas["tuvo_recordatorio"] = ventas["fecha_prometida"].notna()
    ventas["fecha_corte"] = ventas["fecha_prometida"].fillna(
        ventas["fecha"] + pd.Timedelta(days=PLAZO_POR_DEFECTO)
    )
    ventas["dias_para_pago"] = (ventas["fecha_corte"] - ventas["fecha"]).dt.days

    # ── Censura: fuera lo que todavia no vence ──
    sin_vencer = ventas["fecha_corte"] > hoy
    censuradas = int(sin_vencer.sum())
    ventas = ventas[~sin_vencer].copy()

    # ── Cuanto se habia pagado al llegar el corte ──
    pagos = ventas[["id", "fecha_corte"]].merge(
        abonos, left_on="id", right_on="venta_id", how="left"
    )

    # Solo los abonos hechos hasta la fecha de corte: los posteriores son
    # justamente lo que llego tarde, y contarlos borraria la mora.
    a_tiempo = pagos[pagos["fecha"].notna() & (pagos["fecha"] <= pagos["fecha_corte"])]
    cobrado = a_tiempo.groupby("id")["monto_centavos"].sum()

    ventas["cobrado_al_corte"] = ventas["id"].map(cobrado).fillna(0).astype("int64")
    ventas["pendiente_al_corte"] = (
        ventas["total_centavos"] - ventas["cobrado_al_corte"]
    ).clip(lower=0)

    # ── La variable objetivo ──
    ventas["estado_pago"] = (ventas["pendiente_al_corte"] > TOLERANCIA).astype("int8")

    # ── Abono inicial ──
    # Lo que entrego el mismo dia de la venta. Es la señal mas directa de
    # compromiso que tiene la dueña en el momento de fiar.
    inicial = (
        abonos.merge(ventas[["id", "fecha"]], left_on="venta_id", right_on="id")
        .query("fecha_x == fecha_y")
        .groupby("venta_id")["monto_centavos"]
        .sum()
    )

    ventas["abono_inicial_centavos"] = ventas["id"].map(inicial).fillna(0).astype("int64")
    ventas["porcentaje_abono_inicial"] = (
        ventas["abono_inicial_centavos"] / ventas["total_centavos"] * 100
    ).round(2)

    # ── Margen ──
    ventas["ganancia_centavos"] = ventas["total_centavos"] - ventas["costo_centavos"]
    ventas["porcentaje_ganancia"] = np.where(
        ventas["total_centavos"] > 0,
        (ventas["ganancia_centavos"] / ventas["total_centavos"] * 100).round(2),
        0.0,
    )

    # ── Categoria dominante ──
    ventas["categoria_producto"] = ventas["id"].map(
        categoria_principal(tablas["venta_items"], tablas["productos"])
    ).fillna("Sin categoria")

    # ── Historial de la clienta, SIN mirar al futuro ──
    ventas = _agregar_historial(ventas)

    # ── Temporales ──
    ventas["mes"] = ventas["fecha"].dt.month
    ventas["anio"] = ventas["fecha"].dt.year
    ventas["dia_semana"] = ventas["fecha"].dt.dayofweek

    # `attrs` viaja dentro del Parquet como JSON, asi que solo admite tipos
    # basicos: un Timestamp aqui hace fallar el guardado.
    ventas.attrs["censuradas"] = censuradas
    ventas.attrs["fecha_referencia"] = hoy.strftime("%Y-%m-%d")

    return ventas.reset_index(drop=True)


def _agregar_historial(ventas: pd.DataFrame) -> pd.DataFrame:
    """
    Historial acumulado de cada clienta, contando solo lo ANTERIOR.

    Se ordena por clienta y fecha, y se desplaza un puesto: en la fila de la
    venta del 3 de marzo, el historial es el que existia el 2 de marzo. Sin ese
    desplazamiento la venta se estaria contando a si misma, que es la forma mas
    sutil de fuga de informacion — la que no se nota mirando el codigo por
    encima porque «solo son sumas acumuladas».
    """
    ventas = ventas.sort_values(["cliente_id", "fecha"]).copy()
    por_clienta = ventas.groupby("cliente_id")

    # cumsum().shift() deja en cada fila el acumulado hasta la fila anterior.
    ventas["historial_mora"] = (
        por_clienta["estado_pago"].cumsum() - ventas["estado_pago"]
    ).astype("int32")

    ventas["compras_previas"] = por_clienta.cumcount().astype("int32")

    gastado = por_clienta["total_centavos"].cumsum() - ventas["total_centavos"]
    ventas["gastado_previo_centavos"] = gastado.astype("int64")

    # Tasa de mora previa. En la primera compra no hay historial: se deja en 0
    # y `compras_previas` dice que no hay evidencia, para que el modelo pueda
    # distinguir «nunca ha fallado» de «nunca ha comprado».
    ventas["tasa_mora_previa"] = np.where(
        ventas["compras_previas"] > 0,
        (ventas["historial_mora"] / ventas["compras_previas"]).round(4),
        0.0,
    )

    # Dias desde su compra anterior. Una clienta que vuelve pronto esta activa.
    anterior = por_clienta["fecha"].shift(1)
    ventas["dias_desde_compra_previa"] = (
        (ventas["fecha"] - anterior).dt.days.fillna(-1).astype("int32")
    )

    return ventas


#: Columnas del dataset analitico, en el orden en que se entregan.
COLUMNAS = [
    # Identificacion (no entran al modelo)
    "id", "cliente_id", "fecha",
    # Predictoras conocidas EN EL MOMENTO DE FIAR
    "tipo_pago", "categoria_producto", "total_centavos", "abono_inicial_centavos",
    "porcentaje_abono_inicial", "porcentaje_ganancia", "articulos", "lineas",
    "dias_para_pago", "tuvo_recordatorio",
    "historial_mora", "compras_previas", "tasa_mora_previa",
    "gastado_previo_centavos", "dias_desde_compra_previa",
    "mes", "anio", "dia_semana",
    # Objetivo
    "estado_pago",
    # Auxiliares para el analisis (no entran al modelo)
    "fecha_corte", "cobrado_al_corte", "pendiente_al_corte",
]


def resumir(dataset: pd.DataFrame) -> None:
    """Imprime lo que salio, con las comprobaciones que importan."""
    print("  DATASET ANALITICO\n")
    print(f"    filas                {len(dataset):>7,}")
    print(f"    columnas             {len(dataset.columns):>7}")
    print(f"    clientas             {dataset['cliente_id'].nunique():>7,}")
    print(f"    excluidas por censura{dataset.attrs['censuradas']:>7,}   (aun no vencian)")
    print(f"    fecha de referencia  {dataset.attrs['fecha_referencia']}")

    mora = dataset["estado_pago"]
    print(f"\n    EN MORA              {mora.sum():>7,}  ({mora.mean():.1%})")
    print(f"    puntuales            {(1 - mora).sum():>7,}  ({1 - mora.mean():.1%})")

    print("\n    MORA SEGUN HISTORIAL DE LA CLIENTA")
    tramos = dataset["historial_mora"].clip(upper=3)
    for tramo, grupo in dataset.groupby(tramos):
        etiqueta = f"{tramo}+" if tramo == 3 else f"{tramo} "
        print(f"      {etiqueta} moras previas  {grupo['estado_pago'].mean():>6.1%}   ({len(grupo):,} ventas)")

    print("\n    NULOS")
    nulos = dataset.isna().sum()
    con_nulos = nulos[nulos > 0]
    if con_nulos.empty:
        print("      ninguno")
    else:
        for columna, cuantos in con_nulos.items():
            print(f"      {columna:<28} {cuantos:>6,}")


if __name__ == "__main__":
    from etl.extraer import extraer

    dataset = construir(extraer())
    resumir(dataset[COLUMNAS])
