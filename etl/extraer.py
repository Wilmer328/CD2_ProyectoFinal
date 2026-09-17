"""
Extraccion: lee las tablas operativas desde PostgreSQL.

Es la «E» del ETL. No transforma nada ni calcula nada: trae las filas tal como
estan en la base y las entrega como DataFrames. Separarlo de la transformacion
permite comprobar que lo extraido coincide con lo que hay en la base, sin que
se mezcle con decisiones de analisis.

Se consulta con SQL y no con un ORM a proposito: las agregaciones —el total de
cada venta, lo cobrado hasta una fecha— las resuelve PostgreSQL mucho mejor
que Python recorriendo filas, y el SQL queda a la vista para quien revise el
trabajo.

USO
    python -m etl.extraer            muestra un resumen de lo que hay
"""

from __future__ import annotations

import pandas as pd
import sqlalchemy as sa

from etl.conexion import crear_motor

#: Cada consulta trae una tabla operativa completa. Solo las columnas que el
#: analisis va a usar: traer `creado_en` de todo engordaria la memoria sin
#: aportar nada, porque la fecha que importa es `fecha`, la del negocio.
CONSULTAS = {
    "clientes": """
        select id, nombre, dni, telefono, creado_en::date as alta
        from public.clientes
    """,
    "productos": """
        select id, nombre, categoria, costo_centavos, precio_centavos, stock
        from public.productos
    """,
    "ventas": """
        select id, cliente_id, fecha, tipo_pago
        from public.ventas
    """,
    "venta_items": """
        select venta_id, producto_id, nombre, precio_centavos, costo_centavos, cantidad
        from public.venta_items
    """,
    "abonos": """
        select venta_id, monto_centavos, fecha
        from public.abonos
    """,
    "recordatorios": """
        select venta_id, cliente_id, fecha as fecha_prometida, estado
        from public.recordatorios
        where venta_id is not null
    """,
}

#: Columnas que son fechas. Pandas las trae como texto u objeto si no se le
#: dice, y comparar fechas como texto funciona por casualidad hasta que deja
#: de funcionar.
FECHAS = {
    "clientes": ["alta"],
    "ventas": ["fecha"],
    "abonos": ["fecha"],
    "recordatorios": ["fecha_prometida"],
}


def extraer(motor: sa.Engine | None = None) -> dict[str, pd.DataFrame]:
    """
    Trae las seis tablas operativas.

    :returns: un DataFrame por tabla, con las fechas ya como datetime.
    """
    motor = motor or crear_motor()
    tablas: dict[str, pd.DataFrame] = {}

    with motor.connect() as conexion:
        for nombre, consulta in CONSULTAS.items():
            marco = pd.read_sql_query(sa.text(consulta), conexion)

            for columna in FECHAS.get(nombre, []):
                marco[columna] = pd.to_datetime(marco[columna])

            tablas[nombre] = marco

    return tablas


def resumir(tablas: dict[str, pd.DataFrame]) -> None:
    """Imprime que se extrajo, para comprobarlo de un vistazo."""
    print("  EXTRAIDO DE SUPABASE\n")

    for nombre, marco in tablas.items():
        print(f"    {nombre:<15} {len(marco):>7,} filas  ·  {len(marco.columns)} columnas")

    ventas = tablas["ventas"]
    print(f"\n    periodo         {ventas['fecha'].min():%Y-%m-%d} a {ventas['fecha'].max():%Y-%m-%d}")
    print(f"    clientas        {tablas['clientes']['id'].nunique():,}")

    reparto = ventas["tipo_pago"].value_counts()
    print("\n    TIPO DE PAGO")
    for tipo, cuantas in reparto.items():
        print(f"      {tipo:<12} {cuantas:>6,}  ({cuantas / len(ventas):.1%})")


if __name__ == "__main__":
    resumir(extraer())
