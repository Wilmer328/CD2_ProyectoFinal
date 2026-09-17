"""
Conexion a la base de datos de Supabase.

Centraliza dos detalles que hacen tropezar a cualquiera que conecte por
primera vez, para que nadie del equipo tenga que descubrirlos por su cuenta.

EL DRIVER
Supabase entrega la cadena como `postgresql://`. SQLAlchemy resuelve ese
prefijo al driver `psycopg2`, que es la version 2 y no esta instalada: el
proyecto usa `psycopg` version 3. Sin marcarlo explicito, la conexion falla
con «No module named 'psycopg2'», que no dice nada sobre la causa real.

EL MODO DE CONEXION
La cadena debe ser la del *Session pooler*, no la directa ni la de
transacciones. La directa exige IPv6, que muchas redes domesticas no tienen.
La de transacciones no mantiene estado entre consultas y rompe cosas que
SQLAlchemy da por sentadas.

LA CREDENCIAL
Vive en `.env`, que esta en `.gitignore` y no se sube nunca. Cada integrante
del equipo tiene el suyo.
"""

from __future__ import annotations

import os
from pathlib import Path

import sqlalchemy as sa
from dotenv import load_dotenv

#: Raiz del repositorio, donde vive el `.env`.
RAIZ = Path(__file__).resolve().parent.parent


def leer_url() -> str:
    """
    Lee `DATABASE_URL` del `.env` y la deja lista para SQLAlchemy.

    :raises RuntimeError: si falta el archivo, falta la variable, o la
        contraseña sigue sin sustituir.
    """
    archivo = RAIZ / ".env"

    if not archivo.exists():
        raise RuntimeError(
            f"No existe {archivo}.\n"
            "Copia .env.ejemplo como .env y pon dentro tu cadena de conexion."
        )

    load_dotenv(archivo)
    url = os.environ.get("DATABASE_URL", "").strip()

    if not url:
        raise RuntimeError(
            "Falta DATABASE_URL en .env.\n"
            "La linea tiene que empezar por 'DATABASE_URL=', no solo la cadena suelta."
        )

    if "[YOUR-PASSWORD]" in url:
        raise RuntimeError(
            "La cadena todavia lleva el marcador [YOUR-PASSWORD].\n"
            "Sustituyelo —corchetes incluidos— por la contraseña de la base."
        )

    # psycopg v3 en lugar del psycopg2 que SQLAlchemy asume por defecto.
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)

    return url


def crear_motor() -> sa.Engine:
    """
    Motor de SQLAlchemy contra la base del proyecto.

    `pool_pre_ping` comprueba que la conexion siga viva antes de usarla: el
    pooler de Supabase cierra las que llevan rato ociosas, y sin esto la
    siguiente consulta falla con un error de red que despista.
    """
    return sa.create_engine(leer_url(), pool_pre_ping=True, future=True)


def contexto_del_negocio(conexion: sa.Connection) -> tuple[str, str]:
    """
    Identificadores a los que cuelgan los datos: la cuenta y el negocio.

    El esquema los exige en cada fila —`owner_id` por trazabilidad y
    `negocio_id` porque es lo que decide el acceso—, y no se inventan: se leen
    de lo que las migraciones ya crearon.

    :returns: (owner_id, negocio_id)
    :raises RuntimeError: si falta el usuario demo o el negocio.
    """
    owner = conexion.execute(
        sa.text("select id from auth.users where lower(email) = 'demo@jsanchez.site'")
    ).scalar()

    if owner is None:
        raise RuntimeError(
            "No existe el usuario demo@jsanchez.site en auth.users.\n"
            "Crealo en Authentication -> Users antes de cargar datos."
        )

    negocio = conexion.execute(
        sa.text("select id from public.negocios where lower(nombre) = 'demostracion'")
    ).scalar()

    if negocio is None:
        raise RuntimeError(
            "No existe el negocio 'Demostracion'.\n"
            "Lo crea la migracion 0006: comprueba que se ejecuto."
        )

    return str(owner), str(negocio)
