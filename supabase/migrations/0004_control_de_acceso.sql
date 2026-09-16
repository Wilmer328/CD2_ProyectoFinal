-- April Collections — control de acceso por lista de autorizados
--
-- PROBLEMA QUE RESUELVE
-- Con el proveedor de Google activo, cualquier persona con cuenta de Google
-- podia registrarse. No veia datos ajenos —las politicas RLS lo impiden— pero
-- si se creaba una cuenta que nadie habia autorizado. April Collections es la
-- herramienta privada de un negocio familiar: no tiene registro publico.
--
-- POR QUE EN LA BASE Y NO EN LA APLICACION
-- Un filtro en el navegador se salta desactivando JavaScript o llamando a la
-- API directamente. Este disparador se ejecuta dentro de Postgres, en la misma
-- transaccion que crea el usuario, asi que no hay forma de rodearlo desde
-- fuera.

-- ── Lista de autorizados ──────────────────────────────────────────────────
create table if not exists public.accesos_autorizados (
  correo      text primary key,
  motivo      text not null,
  creado_en   timestamptz not null default now()
);

comment on table public.accesos_autorizados is
  'Correos que pueden crear cuenta. Sin RLS ni permisos para los roles de la API: solo se administra desde el panel de Supabase.';

-- Deliberadamente NO se conceden permisos a anon ni a authenticated. La lista
-- solo se consulta desde el disparador, que corre con permisos elevados. Si la
-- aplicacion pudiera leerla, expondria los correos autorizados a cualquiera
-- con la clave publica.
alter table public.accesos_autorizados enable row level security;

-- ── Disparador de control ─────────────────────────────────────────────────
create or replace function public.exigir_acceso_autorizado()
returns trigger
language plpgsql
security definer
-- search_path fijo: sin esto, un search_path manipulado podria desviar la
-- consulta a otra tabla, y esta funcion corre con permisos elevados.
set search_path = public
as $$
begin
  if not exists (
    select 1 from public.accesos_autorizados
    where lower(correo) = lower(new.email)
  ) then
    raise exception
      'Esta cuenta no tiene acceso a April Collections. Contacta al administrador.'
      using errcode = 'insufficient_privilege';
  end if;

  return new;
end;
$$;

-- BEFORE INSERT: rechaza antes de crear la fila, de modo que no queda ni
-- rastro del intento. Se ejecuta antes del disparador que crea el perfil.
drop trigger if exists al_registrarse_exigir_acceso on auth.users;

create trigger al_registrarse_exigir_acceso
  before insert on auth.users
  for each row
  execute function public.exigir_acceso_autorizado();

-- ── Autorizados iniciales ─────────────────────────────────────────────────
-- Las dos personas que administran el negocio.
--
-- Se versionan por decision explicita del autor, para que la instalacion sea
-- reproducible: quien clone el repositorio y ejecute las migraciones obtiene
-- el mismo control de acceso sin pasos manuales.
--
-- La contrapartida asumida es que este repositorio es publico, asi que estos
-- correos quedan visibles. Para agregar correos sin versionarlos, se hace
-- desde el SQL Editor con un insert igual que este.
--
-- La comparacion del disparador usa lower(), asi que las mayusculas del correo
-- no afectan al acceso.
insert into public.accesos_autorizados (correo, motivo) values
  ('wilmer415sanchez@gmail.com', 'Autor del proyecto'),
  ('aprilcollections2026@gmail.com', 'Dueña del negocio'),
  ('jova889@gmail.com',          'Profesor del curso')
on conflict (correo) do nothing;

-- ── Revision de cuentas ya existentes ─────────────────────────────────────
-- El disparador solo actua sobre altas nuevas: las cuentas creadas antes de
-- esta migracion siguen existiendo. Este aviso las lista para poder revisarlas
-- y borrarlas desde Authentication -> Users si no deberian estar.
do $$
declare
  intrusas text;
begin
  select string_agg(u.email, ', ')
  into intrusas
  from auth.users u
  where not exists (
    select 1 from public.accesos_autorizados a
    where lower(a.correo) = lower(u.email)
  );

  if intrusas is null then
    raise notice 'Todas las cuentas existentes estan autorizadas.';
  else
    raise notice 'CUENTAS EXISTENTES NO AUTORIZADAS: %. Revisalas en Authentication -> Users.', intrusas;
  end if;
end $$;

-- ── Registro ──────────────────────────────────────────────────────────────
select public.registrar_migracion('0004', 'control_de_acceso');
