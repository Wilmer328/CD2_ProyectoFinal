"""
Generador del conjunto de datos sintetico de April Collections.

POR QUE ES SINTETICO
La aplicacion lleva pocas semanas en uso real y tiene un puñado de ventas:
insuficiente para entrenar nada. Y aunque hubiera mas, no se usarian: contienen
nombres, DNI y telefonos de clientas que nunca consintieron aparecer en un
trabajo academico.

QUE PRODUCE
Las tablas OPERATIVAS, con la misma forma que tendrian en la base de datos de
la aplicacion: clientes, productos, ventas, venta_items, abonos y
recordatorios. No produce el dataset analitico ni la variable objetivo.

Eso es deliberado. La mora NO se asigna aqui: se simula el comportamiento de
pago —quien paga rapido, quien se atrasa, quien deja saldo— y la etiqueta la
DERIVA despues el ETL a partir de los abonos y las fechas prometidas,
exactamente como habria que hacerlo con datos reales. Si la etiqueta se pusiera
aqui, el modelo aprenderia una regla que alguien escribio, no un patron de los
datos.

COMO FUNCIONA LA SIMULACION
Cada clienta tiene una FIABILIDAD latente, un numero entre 0 y 1 que nunca
aparece en las tablas. De ella dependen cuanto tarda en pagar, en cuantos
abonos y si llega a saldar. El modelo no puede verla; solo vera sus
consecuencias: historial de atrasos, dias que tarda, montos. Aprender a
estimarla a partir de esas huellas es justamente el problema.

REPRODUCIBLE
Semilla fija. Cualquiera del equipo ejecuta esto y obtiene exactamente las
mismas filas, hasta el ultimo centavo.

USO
    python -m datos.generar
    python -m datos.generar --clientas 400 --meses 24 --semilla 42
"""

from __future__ import annotations

import argparse
import csv
import random
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

# ── Parametros por defecto ────────────────────────────────────────────────

SEMILLA = 42
CLIENTAS = 400
MESES = 24
#: Ultimo mes con datos. Fijo y no `hoy`, para que el dataset no cambie segun
#: el dia en que se ejecute el generador.
FIN = date(2026, 8, 31)

SALIDA = Path(__file__).resolve().parent / "procesados" / "crudos"

# ── Catalogo ──────────────────────────────────────────────────────────────
# Las cuatro categorias reales del negocio, mas dos que la dueña ha ido
# añadiendo. Cada una con su rotacion y su rango de precios.

CATEGORIAS = {
    # nombre        peso   costo minimo y maximo en lempiras
    "Joyeria":     (0.32, (120, 900)),
    "Maquillaje":  (0.26, (80, 650)),
    "Perfumes":    (0.18, (250, 1400)),
    "Sandalias":   (0.14, (200, 780)),
    "Bolsos":      (0.07, (300, 1100)),
    "Accesorios":  (0.03, (40, 260)),
}

PRODUCTOS_POR_CATEGORIA = {
    "Joyeria": [
        "Aretes dorados", "Aretes de perla", "Cadena de plata", "Dije de corazon",
        "Pulsera tejida", "Anillo solitario", "Juego de aretes y cadena",
        "Argollas grandes", "Tobillera dorada", "Gargantilla",
    ],
    "Maquillaje": [
        "Base liquida", "Labial mate", "Paleta de sombras", "Rimel volumen",
        "Rubor compacto", "Corrector", "Polvo traslucido", "Delineador",
        "Brillo labial", "Primer facial",
    ],
    "Perfumes": [
        "Perfume floral 100ml", "Perfume citrico 50ml", "Body splash",
        "Set de perfume y crema", "Perfume amaderado", "Colonia infantil",
    ],
    "Sandalias": [
        "Sandalia de tacon", "Sandalia plana", "Sandalia de plataforma",
        "Chancleta decorada", "Sandalia de cuña",
    ],
    "Bolsos": [
        "Bolso de mano", "Cartera pequeña", "Mochila casual", "Bolso de hombro",
    ],
    "Accesorios": [
        "Diadema", "Llavero decorado", "Espejo de bolsillo", "Lazo para cabello",
    ],
}

#: Margen habitual sobre el costo. La dueña usa 30% por defecto y lo ajusta.
MARGEN_MINIMO = 0.22
MARGEN_MAXIMO = 0.55

# ── Nombres ───────────────────────────────────────────────────────────────

NOMBRES = [
    "Ana", "Maria", "Rosa", "Carmen", "Gloria", "Xiomara", "Fanny", "Suyapa",
    "Karla", "Wendy", "Dania", "Yolanda", "Mirna", "Reina", "Blanca", "Iris",
    "Lesly", "Heidy", "Jackeline", "Norma", "Sandra", "Claudia", "Doris",
    "Elsa", "Marleny", "Olga", "Patricia", "Sonia", "Teresa", "Vilma",
    "Yessenia", "Nohemi", "Digna", "Belkis", "Corina", "Emilia",
]

APELLIDOS = [
    "Martinez", "Lopez", "Garcia", "Hernandez", "Rodriguez", "Perez", "Gomez",
    "Flores", "Cruz", "Ramirez", "Reyes", "Zuniga", "Aguilar", "Mejia",
    "Castillo", "Fuentes", "Palacios", "Bonilla", "Velasquez", "Interiano",
    "Ordoñez", "Maradiaga", "Turcios", "Banegas", "Amaya", "Discua",
]

# ── Estacionalidad ────────────────────────────────────────────────────────
# Diciembre y mayo son los meses fuertes: navidad y dia de la madre. Enero y
# febrero son flojos, despues del gasto navideño.

FACTOR_MES = {
    1: 0.70, 2: 0.75, 3: 0.95, 4: 1.00, 5: 1.45, 6: 0.95,
    7: 0.90, 8: 0.95, 9: 0.90, 10: 1.00, 11: 1.15, 12: 1.70,
}


@dataclass
class Clienta:
    """Una clienta y su fiabilidad latente, que nunca se guarda."""

    id: str
    nombre: str
    dni: str | None
    telefono: str | None
    creado_en: date
    fiabilidad: float


def sin_tildes(texto: str) -> str:
    """Quita tildes y eñes, para construir correos y comparar nombres."""
    descompuesto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def nuevo_id(rng: random.Random) -> str:
    """UUID v4 derivado del generador, para que sea reproducible."""
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


def a_centavos(lempiras: float) -> int:
    """El dinero se guarda en centavos enteros, nunca como decimal."""
    return int(round(lempiras * 100))


def elegir_categoria(rng: random.Random) -> str:
    nombres = list(CATEGORIAS)
    pesos = [CATEGORIAS[n][0] for n in nombres]
    return rng.choices(nombres, weights=pesos, k=1)[0]


# ── Generacion de cada tabla ──────────────────────────────────────────────


def generar_categorias(rng: random.Random, inicio: date) -> list[dict]:
    """Las categorias del catalogo, creadas al abrir el negocio."""
    return [
        {
            "id": nuevo_id(rng),
            "nombre": nombre,
            "creado_en": (inicio + timedelta(days=i)).isoformat(),
        }
        for i, nombre in enumerate(CATEGORIAS)
    ]


def generar_productos(rng: random.Random, inicio: date) -> list[dict]:
    """El catalogo. El precio sale del costo mas un margen, como en la app."""
    productos = []

    for categoria, nombres in PRODUCTOS_POR_CATEGORIA.items():
        _, (costo_min, costo_max) = CATEGORIAS[categoria]

        for nombre in nombres:
            costo = rng.uniform(costo_min, costo_max)
            margen = rng.uniform(MARGEN_MINIMO, MARGEN_MAXIMO)
            # Se redondea a la decena: nadie pone un precio de L 347.13.
            precio = round(costo * (1 + margen) / 10) * 10

            productos.append({
                "id": nuevo_id(rng),
                "nombre": nombre,
                "categoria": categoria,
                "costo_centavos": a_centavos(round(costo, 2)),
                "precio_centavos": a_centavos(precio),
                # Existencias actuales. No se simula el historial de stock:
                # la aplicacion tampoco lo guarda.
                "stock": max(0, int(rng.gauss(12, 7))),
                "creado_en": (inicio + timedelta(days=rng.randint(0, 20))).isoformat(),
            })

    return productos


def generar_clientas(rng: random.Random, cuantas: int, inicio: date, fin: date) -> list[Clienta]:
    """
    Las clientas, cada una con su fiabilidad latente.

    La fiabilidad sigue una Beta(5, 2): la mayoria paga razonablemente bien y
    una minoria se atrasa mucho. Es la forma que tiene en un negocio que fia a
    conocidas, no a desconocidos.
    """
    clientas = []
    usados = set()
    dias = (fin - inicio).days

    for _ in range(cuantas):
        # Nombre unico: dos clientas con el mismo nombre confundirian el
        # analisis por clienta.
        for _ in range(50):
            nombre = f"{rng.choice(NOMBRES)} {rng.choice(APELLIDOS)}"
            if nombre not in usados:
                break
        usados.add(nombre)

        # Se dan de alta a lo largo del tiempo, no todas el primer dia.
        alta = inicio + timedelta(days=int(rng.triangular(0, dias, dias * 0.35)))

        # DNI hondureño: 13 digitos. Opcional, como en la aplicacion real.
        dni = None
        if rng.random() < 0.62:
            dni = f"0{rng.randint(1, 8)}0{rng.randint(1, 9)}{rng.randint(1950, 2006)}{rng.randint(10000, 99999)}"

        telefono = None
        if rng.random() < 0.78:
            telefono = f"{rng.choice([3, 8, 9])}{rng.randint(1000000, 9999999)}"

        clientas.append(Clienta(
            id=nuevo_id(rng),
            nombre=nombre,
            dni=dni,
            telefono=telefono,
            creado_en=alta,
            fiabilidad=rng.betavariate(5, 2),
        ))

    return clientas


def elegir_tipo_pago(rng: random.Random, fiabilidad: float) -> str:
    """
    A quien paga mal se le fia menos: la dueña aprende con el tiempo.

    Esta es una de las huellas que dejara la fiabilidad en los datos, y el
    modelo podra aprovecharla.
    """
    if fiabilidad > 0.80:
        pesos = [0.30, 0.25, 0.45]   # contado, abono, credito
    elif fiabilidad > 0.55:
        pesos = [0.38, 0.30, 0.32]
    else:
        pesos = [0.55, 0.32, 0.13]

    return rng.choices(["contado", "abono", "credito"], weights=pesos, k=1)[0]


def generar_ventas(
    rng: random.Random,
    clientas: list[Clienta],
    productos: list[dict],
    inicio: date,
    fin: date,
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """
    Las ventas con sus lineas, sus abonos y sus recordatorios.

    Los abonos son lo importante: de como se reparten en el tiempo saldra
    despues la etiqueta de mora.
    """
    ventas, items, abonos, recordatorios = [], [], [], []

    # Cuantas compras hace cada clienta al mes, segun lo activa que sea.
    for clienta in clientas:
        actividad = rng.betavariate(2, 5) * 1.8 + 0.15

        dia = max(clienta.creado_en, inicio)

        while dia <= fin:
            # La estacionalidad modula la frecuencia de compra.
            probabilidad = actividad * FACTOR_MES[dia.month] / 30
            if rng.random() > probabilidad:
                dia += timedelta(days=1)
                continue

            venta_id = nuevo_id(rng)
            tipo = elegir_tipo_pago(rng, clienta.fiabilidad)

            # ── Lineas ──
            cuantas = rng.choices([1, 2, 3, 4], weights=[0.52, 0.28, 0.14, 0.06], k=1)[0]
            total = 0

            for _ in range(cuantas):
                categoria = elegir_categoria(rng)
                candidatos = [p for p in productos if p["categoria"] == categoria]
                producto = rng.choice(candidatos)
                cantidad = rng.choices([1, 2, 3], weights=[0.80, 0.16, 0.04], k=1)[0]

                items.append({
                    "id": nuevo_id(rng),
                    "venta_id": venta_id,
                    "producto_id": producto["id"],
                    "nombre": producto["nombre"],
                    "precio_centavos": producto["precio_centavos"],
                    "costo_centavos": producto["costo_centavos"],
                    "cantidad": cantidad,
                })

                total += producto["precio_centavos"] * cantidad

            ventas.append({
                "id": venta_id,
                "cliente_id": clienta.id,
                "fecha": dia.isoformat(),
                "tipo_pago": tipo,
                "creado_en": dia.isoformat(),
            })

            # ── Pagos ──
            if tipo == "contado":
                # Se paga entero el mismo dia.
                abonos.append({
                    "id": nuevo_id(rng),
                    "venta_id": venta_id,
                    "monto_centavos": total,
                    "fecha": dia.isoformat(),
                    "creado_en": dia.isoformat(),
                })
                dia += timedelta(days=1)
                continue

            # A credito o con abono inicial: se promete una fecha.
            plazo = rng.choice([8, 15, 15, 21, 30, 30])
            prometida = dia + timedelta(days=plazo)

            # La dueña agenda recordatorio casi siempre, pero no siempre.
            if rng.random() < 0.72:
                recordatorios.append({
                    "id": nuevo_id(rng),
                    "cliente_id": clienta.id,
                    "venta_id": venta_id,
                    "fecha": prometida.isoformat(),
                    "hora": rng.choice(["09:00", "10:00", "14:00", "16:00"]),
                    "nota": None,
                    "estado": "pendiente",
                    "avisado_en": None,
                    "visto": False,
                    "creado_en": dia.isoformat(),
                })

            pendiente = total

            if tipo == "abono":
                # Entrega inicial: entre el 15% y el 60% del total.
                inicial = int(total * rng.uniform(0.15, 0.60))
                if inicial > 0:
                    abonos.append({
                        "id": nuevo_id(rng),
                        "venta_id": venta_id,
                        "monto_centavos": inicial,
                        "fecha": dia.isoformat(),
                        "creado_en": dia.isoformat(),
                    })
                    pendiente -= inicial

            # ── Como termina de pagar ──
            # Dias desde la venta hasta el ultimo pago. La fiabilidad los
            # desplaza en los dos sentidos: quien paga bien salda ANTES de la
            # fecha prometida, quien paga mal despues. Que pueda ser antes es
            # lo que hace realista el conjunto: si el calendario terminara
            # siempre en la fecha prometida o despues, casi toda venta fiada
            # saldria en mora y la etiqueta no distinguiria a nadie.
            desvio = rng.gauss((0.48 - clienta.fiabilidad) * 55, 10)
            dias_hasta_saldar = max(1, int(plazo + desvio))

            # Y algunas no llegan a saldar nunca: dejan saldo colgando.
            salda = rng.random() < (0.45 + clienta.fiabilidad * 0.54)

            cuotas = rng.choices([1, 2, 3, 4], weights=[0.46, 0.31, 0.16, 0.07], k=1)[0]
            # Si no va a saldar, paga solo una parte y deja el resto colgando.
            porcion = 1.0 if salda else rng.uniform(0.15, 0.75)
            a_pagar = int(pendiente * porcion)

            for numero in range(cuotas):
                if a_pagar <= 0:
                    break

                # La ultima cuota liquida lo que quede, para que no sobren
                # centavos por el redondeo.
                ultima = numero == cuotas - 1
                monto = a_pagar if ultima else int(a_pagar / (cuotas - numero))

                if monto <= 0:
                    continue

                # Las cuotas se reparten entre la venta y la fecha real de pago.
                avance = (numero + 1) / cuotas
                fecha_cuota = dia + timedelta(days=int(dias_hasta_saldar * avance))

                if fecha_cuota > fin:
                    break

                abonos.append({
                    "id": nuevo_id(rng),
                    "venta_id": venta_id,
                    "monto_centavos": monto,
                    "fecha": fecha_cuota.isoformat(),
                    "creado_en": fecha_cuota.isoformat(),
                })

                a_pagar -= monto

            dia += timedelta(days=1)

    ventas.sort(key=lambda v: v["fecha"])
    return ventas, items, abonos, recordatorios


# ── Escritura ─────────────────────────────────────────────────────────────


def escribir(nombre: str, filas: list[dict], destino: Path) -> None:
    """Un CSV por tabla, con la forma exacta que tendria en la base."""
    destino.mkdir(parents=True, exist_ok=True)
    ruta = destino / f"{nombre}.csv"

    if not filas:
        ruta.write_text("", encoding="utf-8")
        return

    with ruta.open("w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=list(filas[0]))
        escritor.writeheader()
        escritor.writerows(filas)


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera el dataset sintetico de April Collections.")
    parser.add_argument("--clientas", type=int, default=CLIENTAS)
    parser.add_argument("--meses", type=int, default=MESES)
    parser.add_argument("--semilla", type=int, default=SEMILLA)
    parser.add_argument("--salida", type=Path, default=SALIDA)
    args = parser.parse_args()

    rng = random.Random(args.semilla)

    inicio = FIN - timedelta(days=args.meses * 30)

    categorias = generar_categorias(rng, inicio)
    productos = generar_productos(rng, inicio)
    clientas = generar_clientas(rng, args.clientas, inicio, FIN)
    ventas, items, abonos, recordatorios = generar_ventas(rng, clientas, productos, inicio, FIN)

    filas_clientas = [
        {
            "id": c.id,
            "nombre": c.nombre,
            "dni": c.dni,
            "telefono": c.telefono,
            "creado_en": c.creado_en.isoformat(),
        }
        for c in clientas
    ]

    escribir("categorias", categorias, args.salida)
    escribir("productos", productos, args.salida)
    escribir("clientes", filas_clientas, args.salida)
    escribir("ventas", ventas, args.salida)
    escribir("venta_items", items, args.salida)
    escribir("abonos", abonos, args.salida)
    escribir("recordatorios", recordatorios, args.salida)

    cobrado = sum(a["monto_centavos"] for a in abonos)
    facturado = sum(i["precio_centavos"] * i["cantidad"] for i in items)

    print(f"  semilla          {args.semilla}")
    print(f"  periodo          {inicio} a {FIN}  ({args.meses} meses)")
    print()
    print(f"  categorias       {len(categorias):>7,}")
    print(f"  productos        {len(productos):>7,}")
    print(f"  clientas         {len(clientas):>7,}")
    print(f"  ventas           {len(ventas):>7,}")
    print(f"  lineas de venta  {len(items):>7,}")
    print(f"  abonos           {len(abonos):>7,}")
    print(f"  recordatorios    {len(recordatorios):>7,}")
    print()
    print(f"  facturado        L {facturado / 100:>12,.2f}")
    print(f"  cobrado          L {cobrado / 100:>12,.2f}   ({cobrado / facturado:.1%})")
    print(f"  por cobrar       L {(facturado - cobrado) / 100:>12,.2f}")
    print()
    print(f"  escrito en       {args.salida}")


if __name__ == "__main__":
    main()
