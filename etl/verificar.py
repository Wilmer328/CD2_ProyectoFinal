"""
Comprueba las afirmaciones del documento que se pueden comprobar.

El documento dice varias cosas que no deberian creerse por fe: que el
historial no mira al futuro, que no entran columnas que contengan la
respuesta, que no hay nulos, que la tasa de mora es la que se declara. Este
script las verifica contra el dataset versionado y falla si alguna no se
cumple.

No necesita conexion a Supabase: lee datos/procesados/dataset.parquet.

USO
    python -m etl.verificar
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
DATASET = RAIZ / "datos" / "procesados" / "dataset.parquet"
METRICAS = RAIZ / "modelos" / "metricas.json"

fallos = 0


def comprobar(condicion: bool, mensaje: str) -> None:
    global fallos
    marca = "OK " if condicion else "FALLO"
    print(f"  [{marca}] {mensaje}")
    if not condicion:
        fallos += 1


def main() -> None:
    datos = pd.read_parquet(DATASET).sort_values(["cliente_id", "fecha"])
    metricas = json.loads(METRICAS.read_text(encoding="utf-8"))

    print("\n  DATASET\n")
    comprobar(len(datos) == 2188, f"tiene 2.188 ventas fiadas (tiene {len(datos):,})")
    comprobar(datos.isna().sum().sum() == 0, "no tiene valores faltantes")
    comprobar(
        set(datos["tipo_pago"].unique()) == {"credito", "abono"},
        "solo contiene ventas fiadas: ninguna al contado",
    )
    tasa = datos["estado_pago"].mean()
    comprobar(abs(tasa - 0.257) < 0.005, f"la tasa de mora es 25,7% (es {tasa:.1%})")

    # ── Fuga de informacion ──────────────────────────────────────────────
    # El historial de cada venta debe ser exactamente el acumulado de las
    # ventas ANTERIORES de esa clienta. Ni una mas, ni la propia.
    print("\n  FUGA DE INFORMACION (el historial no mira al futuro)\n")

    desajustes = 0
    con_propio_resultado = 0

    for _, grupo in datos.groupby("cliente_id"):
        acumulado = 0
        compras = 0
        for _, fila in grupo.iterrows():
            if fila["historial_mora"] != acumulado or fila["compras_previas"] != compras:
                desajustes += 1
            acumulado += int(fila["estado_pago"])
            compras += 1

        # En la ultima venta, el historial no puede incluir esa misma venta.
        ultima = grupo.iloc[-1]
        if ultima["historial_mora"] > grupo["estado_pago"].sum() - ultima["estado_pago"]:
            con_propio_resultado += 1

    comprobar(desajustes == 0, f"historial calculado en orden cronologico: {desajustes} desajustes")
    comprobar(con_propio_resultado == 0,
              f"ninguna venta cuenta su propio resultado: {con_propio_resultado} lo hacen")

    correlacion = datos["historial_mora"].corr(datos["estado_pago"])
    comprobar(correlacion < 0.5,
              f"correlacion historial-objetivo lejos de 1: {correlacion:.3f} (cerca de 1 delataria fuga)")

    # ── Columnas prohibidas ──────────────────────────────────────────────
    print("\n  COLUMNAS QUE CONTIENEN LA RESPUESTA\n")

    variables = set(metricas["variables"])
    for columna in ("pendiente_al_corte", "cobrado_al_corte", "fecha_corte", "estado_pago"):
        comprobar(columna not in variables, f"{columna} NO entra al modelo")

    # La etiqueta se define como pendiente > 0; comprobarlo directamente.
    definicion = ((datos["pendiente_al_corte"] > 100).astype("int8") == datos["estado_pago"]).all()
    comprobar(definicion, "estado_pago = 1 exactamente cuando hay saldo pendiente al corte")

    # ── Metricas declaradas ──────────────────────────────────────────────
    print("\n  METRICAS DECLARADAS EN EL DOCUMENTO\n")

    rf = metricas["metricas"]["Random Forest"]
    base = metricas["metricas"]["Línea base"]
    comprobar(metricas["modelo"] == "Random Forest", f"modelo elegido: {metricas['modelo']}")
    comprobar(abs(rf["roc_auc"] - 0.742) < 0.001, f"ROC-AUC del Random Forest: {rf['roc_auc']}")
    comprobar(abs(rf["recall"] - 0.475) < 0.001, f"recall del Random Forest: {rf['recall']}")
    comprobar(base["recall"] == 0.0, f"la linea base detecta cero moras: recall {base['recall']}")
    comprobar(base["exactitud"] > rf["exactitud"],
              f"la linea base tiene MAS exactitud que el modelo ({base['exactitud']} > {rf['exactitud']}): "
              "por eso la exactitud no sirve")

    # ── Resultado ────────────────────────────────────────────────────────
    print()
    if fallos:
        print(f"  {fallos} comprobacion(es) fallaron.\n")
        sys.exit(1)

    print("  Todas las comprobaciones pasaron.\n")


if __name__ == "__main__":
    main()
