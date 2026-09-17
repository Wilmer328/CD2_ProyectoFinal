"""
Ejecuta el ETL completo: extraer, transformar y dejar el dataset listo.

Es el unico comando que hace falta correr para obtener el conjunto de datos con
el que trabajan los notebooks y el dashboard. Los tres pasos viven en modulos
separados para poder probarlos por su cuenta; esto solo los encadena.

    Supabase  ──extraer──>  DataFrames  ──transformar──>  dataset analitico
                                                                │
                                                                v
                                              datos/procesados/dataset.parquet

Se guarda en Parquet y no en CSV porque conserva los tipos. Un CSV convierte
todo a texto, y al volver a leerlo las fechas vuelven como cadenas y los
enteros como flotantes: el mismo analisis da numeros distintos segun quien lo
abra. Parquet ademas ocupa bastante menos.

Se guarda tambien una copia en CSV para poder abrirla en Excel, que es lo que
espera quien revisa el trabajo sin Python delante.

USO
    python -m etl.ejecutar
    python -m etl.ejecutar --salida otra/ruta
"""

from __future__ import annotations

import argparse
from pathlib import Path

from etl.extraer import extraer
from etl.transformar import COLUMNAS, construir, resumir

SALIDA = Path(__file__).resolve().parent.parent / "datos" / "procesados"


def main() -> None:
    parser = argparse.ArgumentParser(description="Ejecuta el ETL completo.")
    parser.add_argument("--salida", type=Path, default=SALIDA)
    args = parser.parse_args()

    print("  [1/3] extrayendo de Supabase...")
    tablas = extraer()

    print("  [2/3] transformando...")
    dataset = construir(tablas)[COLUMNAS]

    print("  [3/3] guardando...\n")
    args.salida.mkdir(parents=True, exist_ok=True)

    parquet = args.salida / "dataset.parquet"
    csv = args.salida / "dataset.csv"

    dataset.to_parquet(parquet, index=False)
    dataset.to_csv(csv, index=False, encoding="utf-8")

    resumir(dataset)

    print(f"\n    {parquet.name:<20} {parquet.stat().st_size / 1024:>8,.0f} KB")
    print(f"    {csv.name:<20} {csv.stat().st_size / 1024:>8,.0f} KB")
    print(f"\n  escrito en {args.salida}")


if __name__ == "__main__":
    main()
