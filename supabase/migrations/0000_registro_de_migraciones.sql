-- April Collections — registro de migraciones
--
-- Deja constancia EN LA BASE de qué migraciones se han aplicado y cuándo.
--
-- POR QUE HACE FALTA
-- Los archivos de supabase/migrations/ dicen lo que DEBERIA estar aplicado.
-- Esta tabla dice lo que REALMENTE se aplicó. Sin ella, la única forma de
-- saber si una migración corrió es inspeccionar el esquema a mano y deducirlo,
-- y eso se vuelve imposible en cuanto hay más de un entorno.
--
-- Todas las migraciones de este proyecto son idempotentes: volver a
-- ejecutarlas no rompe nada ni duplica datos. El registro no sirve para
-- impedir que se repitan, sino para saber qué hay puesto y desde cuándo.
--
-- ESTE ARCHIVO SE EJECUTA PRIMERO, antes que 0001.

create table if not exists public.migraciones (
  version      text primary key,
  nombre       text not null,
  aplicada_en  timestamptz not null default now()
);

comment on table public.migraciones is
  'Migraciones aplicadas a esta base. Se administra desde el SQL Editor; sin permisos para los roles de la API.';

-- Sin permisos para anon ni authenticated: la aplicación no tiene por qué
-- conocer el estado del esquema, y exponerlo daría pistas de la estructura
-- interna a cualquiera con la clave pública.
alter table public.migraciones enable row level security;

/**
 * Anota que una migración quedó aplicada.
 *
 * Si ya estaba registrada, actualiza la fecha en lugar de fallar: al volver a
 * ejecutar una migración idempotente, lo interesante es cuándo se aplicó por
 * última vez.
 */
create or replace function public.registrar_migracion(p_version text, p_nombre text)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.migraciones (version, nombre)
  values (p_version, p_nombre)
  on conflict (version) do update set aplicada_en = now();

  raise notice 'Migracion % (%) registrada.', p_version, p_nombre;
end;
$$;

select public.registrar_migracion('0000', 'registro_de_migraciones');

-- Para ver el estado en cualquier momento:
--   select * from public.migraciones order by version;
