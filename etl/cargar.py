"""
Carga el dataset sintetico en la base de Supabase.

Es la «C» del ETL, pero al reves de lo habitual: aqui se CARGA en el sistema
operativo para que despues el ETL analitico pueda EXTRAER de una base
PostgreSQL real, con el mismo esquema que la aplicacion en produccion.

Podria haberse trabajado con los CSV directamente. No se hace porque entonces
el «proceso de extraccion» seria leer un archivo que uno mismo acaba de
escribir, y el proyecto perderia la parte mas parecida a un caso real:
consultar una base con claves foraneas, tipos, restricciones y datos que ya
estaban ahi.

QUE CONSERVA
Los datos de demostracion que sembro la migracion 0003 se quedan. Son
ficticios, no estorban, y son el punto de partida del que se hablo: el dataset
los amplia en lugar de reemplazarlos.

IDEMPOTENTE
Volver a ejecutarlo borra solo lo que cargo la vez anterior —marcado por el
prefijo de nombre— y vuelve a insertar. No toca las filas de la migracion.

USO
    python -m etl.cargar
    python -m etl.cargar --limpiar      solo borra lo cargado antes
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import sqlalchemy as sa

from etl.conexion import contexto_del_negocio, crear_motor

CRUDOS = Path(__file__).resolve().parent.parent / "datos" / "procesados" / "crudos"

#: Orden de carga. Respeta las claves foraneas: una venta necesita su clienta,
#: una linea necesita su venta.
TABLAS = [
    "categorias",
    "clientes",
    "productos",
    "ventas",
    "venta_items",
    "abonos",
    "recordatorios",
]

#: Tablas que llevan `owner_id` y `negocio_id`. Las hijas —venta_items y
#: abonos— no: heredan el acceso a traves de su venta.
CUELGAN_DEL_NEGOCIO = {"categorias", "clientes", "productos", "ventas", "recordatorios"}

#: Columnas que son numeros enteros. El CSV las trae como texto.
ENTEROS = {
    "costo_centavos", "precio_centavos", "monto_centavos", "stock", "cantidad",
}

#: Columnas booleanas.
BOOLEANOS = {"visto"}


def leer_csv(nombre: str) -> list[dict]:
    ruta = CRUDOS / f"{nombre}.csv"

    if not ruta.exists():
        raise RuntimeError(
            f"No existe {ruta}.\n"
            "Genera los datos antes con:  python -m datos.generar"
        )

    with ruta.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def convertir(fila: dict) -> dict:
    """
    Pasa los textos del CSV a los tipos que espera PostgreSQL.

    Las cadenas vacias se convierten en None: en el CSV un campo opcional sin
    valor queda como '', y la base espera NULL. Insertar '' donde deberia ir
    NULL rompe el indice parcial del DNI, que solo se aplica a los que tienen
    valor: todas las clientas sin DNI chocarian entre si.
    """
    convertida = {}

    for clave, valor in fila.items():
        if valor == "" or valor is None:
            convertida[clave] = None
        elif clave in ENTEROS:
            convertida[clave] = int(valor)
        elif clave in BOOLEANOS:
            convertida[clave] = valor.lower() in ("true", "1", "t")
        else:
            convertida[clave] = valor

    return convertida


def limpiar(conexion: sa.Connection) -> dict[str, int]:
    """
    Borra lo que cargo una ejecucion anterior, y solo eso.

    Se borra POR IDENTIFICADOR, leyendo los ids de los propios CSV. Es posible
    porque el generador usa semilla fija: los UUID son los mismos en cada
    ejecucion, asi que los CSV dicen exactamente que filas puso esta carga.

    Eso deja intactos los datos de demostracion de la migracion 0003, cuyos
    UUID los genero PostgreSQL y no aparecen en ningun CSV. Borrar por
    `negocio_id` habria sido mas corto y se los habria llevado por delante.

    El orden respeta las claves foraneas: las ventas antes que las clientas,
    porque `ventas.cliente_id` es RESTRICT. `venta_items` y `abonos` caen
    solos por CASCADE al borrar sus ventas.
    """
    borradas = {}

    for tabla in ["recordatorios", "ventas", "productos", "clientes", "categorias"]:
        ids = [fila["id"] for fila in leer_csv(tabla)]

        if not ids:
            borradas[tabla] = 0
            continue

        total = 0
        LOTE = 500
        for i in range(0, len(ids), LOTE):
            resultado = conexion.execute(
                sa.text(f"delete from public.{tabla} where id = any(:ids)"),
                {"ids": ids[i:i + LOTE]},
            )
            total += resultado.rowcount

        borradas[tabla] = total

    return borradas


def categorias_ya_existentes(conexion: sa.Connection, owner_id: str) -> set[str]:
    """Nombres de categoria que ya tiene esa cuenta, en minusculas."""
    filas = conexion.execute(
        sa.text("select lower(nombre) from public.categorias where owner_id = :o"),
        {"o": owner_id},
    ).scalars().all()

    return set(filas)


def cargar(conexion: sa.Connection, owner_id: str, negocio_id: str) -> dict[str, int]:
    """Inserta las siete tablas, en el orden que respeta las claves foraneas."""
    insertadas = {}
    existentes = categorias_ya_existentes(conexion, owner_id)

    for tabla in TABLAS:
        filas = [convertir(f) for f in leer_csv(tabla)]

        # Las categorias son un catalogo compartido, no filas del dataset: hay
        # un indice unico por (owner_id, lower(nombre)) y los datos demo ya
        # traen varias de las mismas. Se reutilizan las que existen y solo se
        # insertan las que faltan. Los productos apuntan a la categoria por su
        # NOMBRE, no por id, asi que reutilizarlas no rompe nada.
        if tabla == "categorias":
            filas = [f for f in filas if f["nombre"].lower() not in existentes]

        if not filas:
            insertadas[tabla] = 0
            continue

        if tabla in CUELGAN_DEL_NEGOCIO:
            for fila in filas:
                fila["owner_id"] = owner_id
                fila["negocio_id"] = negocio_id

        columnas = list(filas[0])
        sentencia = sa.text(
            f"insert into public.{tabla} ({', '.join(columnas)}) "
            f"values ({', '.join(':' + c for c in columnas)})"
        )

        # En lotes: 6.500 abonos en una sola sentencia agotaria la memoria del
        # pooler, y uno por uno tardaria minutos por la latencia de red.
        LOTE = 500
        for i in range(0, len(filas), LOTE):
            conexion.execute(sentencia, filas[i:i + LOTE])

        insertadas[tabla] = len(filas)

    return insertadas


def main() -> None:
    parser = argparse.ArgumentParser(description="Carga el dataset sintetico en Supabase.")
    parser.add_argument("--limpiar", action="store_true",
                        help="solo borra lo cargado antes, sin volver a insertar")
    args = parser.parse_args()

    motor = crear_motor()

    with motor.begin() as conexion:
        owner_id, negocio_id = contexto_del_negocio(conexion)
        print(f"  negocio  Demostracion ({negocio_id})")
        print(f"  cuenta   demo@jsanchez.site\n")

        borradas = limpiar(conexion)
        total_borrado = sum(borradas.values())

        if total_borrado:
            print(f"  borradas {total_borrado:,} filas de una carga anterior")
            for tabla, n in borradas.items():
                if n:
                    print(f"    {tabla:<15} {n:>7,}")
            print()

        if args.limpiar:
            print("  --limpiar: no se inserta nada.")
            return

        insertadas = cargar(conexion, owner_id, negocio_id)

        print("  INSERTADO")
        for tabla, n in insertadas.items():
            print(f"    {tabla:<15} {n:>7,}")
        print(f"    {'TOTAL':<15} {sum(insertadas.values()):>7,}")


if __name__ == "__main__":
    main()
