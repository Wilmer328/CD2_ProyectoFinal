-- April Collections — negocios y membresías
--
-- QUE PROBLEMA RESUELVE
-- Hasta ahora los datos colgaban de la PERSONA: cada fila llevaba owner_id y
-- las politicas RLS preguntaban «¿esta fila es tuya?». Eso es el modelo de un
-- servicio con muchos negocios independientes, y April Collections no es eso:
-- es UN negocio al que acceden varias personas.
--
-- La consecuencia era real y no cosmetica: si la duena registraba una venta y
-- su hijo entraba con otra cuenta a ayudarla, no la veia. Estaban trabajando
-- sobre dos negocios paralelos sin saberlo.
--
-- Ahora los datos cuelgan del NEGOCIO, y las personas pertenecen a el con un
-- rol. La pregunta de RLS pasa a ser «¿eres miembro de este negocio, y tu rol
-- te permite esto?».
--
-- NO CONVIERTE ESTO EN UNA APLICACION MULTIEMPRESA. Habra exactamente dos
-- negocios, creados aqui: el real y el de demostracion. No hay registro ni
-- pantalla para crear mas; las membresias se administran desde el panel.
--
-- SOBRE owner_id
-- La columna se conserva, y pasa a significar «quien creo esta fila». NO se
-- renombra en esta migracion a proposito: mezclar un renombrado cosmetico con
-- un cambio de autorizacion significa que un fallo en el primero comprometa el
-- segundo. Queda anotado como deuda.
--
-- IDEMPOTENTE. REQUIERE 0000 a 0005 ejecutados antes.

do $$
begin
  -- ┌────────────────────────────────────────────────────────────────────┐
  -- │  CAMBIA ESTE CORREO SI LA CUENTA DEMO ES OTRA                      │
  -- └────────────────────────────────────────────────────────────────────┘
  perform set_config('app.correo_demo', 'demo@jsanchez.site', false);
end $$;

-- ── Negocios ──────────────────────────────────────────────────────────────
create table if not exists public.negocios (
  id         uuid primary key default gen_random_uuid(),
  nombre     text not null check (length(trim(nombre)) > 0),
  creado_en  timestamptz not null default now()
);

-- El nombre identifica al negocio y no puede repetirse: la migracion lo usa
-- para encontrarlo al volver a ejecutarse.
create unique index if not exists negocios_nombre_idx on public.negocios (lower(nombre));

comment on table public.negocios is
  'Negocios que administra la aplicacion. Hay dos: el real y el de demostracion.';

-- ── Membresías ────────────────────────────────────────────────────────────
create table if not exists public.miembros (
  negocio_id  uuid not null references public.negocios (id) on delete cascade,
  usuario_id  uuid not null references auth.users (id) on delete cascade,
  rol         text not null check (rol in ('propietaria', 'administrador', 'lector')),
  creado_en   timestamptz not null default now(),
  primary key (negocio_id, usuario_id)
);

create index if not exists miembros_usuario_idx on public.miembros (usuario_id);

comment on table public.miembros is
  'Quien accede a cada negocio y con que permiso. Se administra desde el panel de Supabase, no desde la aplicacion.';

-- ── Funciones de autorizacion ─────────────────────────────────────────────
-- Van como SECURITY DEFINER para saltarse RLS al consultar `miembros`. Si una
-- politica sobre `miembros` consultara `miembros`, Postgres entraria en
-- recursion infinita. Esta es la forma estandar de evitarlo.

create or replace function public.negocios_del_usuario()
returns setof uuid
language sql
stable
security definer
set search_path = public
as $$
  select negocio_id from public.miembros where usuario_id = auth.uid();
$$;

comment on function public.negocios_del_usuario is
  'Negocios a los que pertenece quien consulta. La usan todas las politicas de lectura.';

create or replace function public.negocios_que_puede_escribir()
returns setof uuid
language sql
stable
security definer
set search_path = public
as $$
  select negocio_id
  from public.miembros
  where usuario_id = auth.uid()
    -- El rol 'lector' queda fuera: puede consultar, no modificar. La
    -- restriccion se evalua en el servidor, asi que no se salta manipulando
    -- el navegador.
    and rol in ('propietaria', 'administrador');
$$;

comment on function public.negocios_que_puede_escribir is
  'Negocios donde el rol permite escribir. Excluye a los lectores.';

-- ── Columna negocio_id en las tablas del negocio ──────────────────────────
alter table public.categorias    add column if not exists negocio_id uuid references public.negocios (id) on delete cascade;
alter table public.clientes      add column if not exists negocio_id uuid references public.negocios (id) on delete cascade;
alter table public.productos     add column if not exists negocio_id uuid references public.negocios (id) on delete cascade;
alter table public.ventas        add column if not exists negocio_id uuid references public.negocios (id) on delete cascade;
alter table public.recordatorios add column if not exists negocio_id uuid references public.negocios (id) on delete cascade;

create index if not exists categorias_negocio_idx    on public.categorias (negocio_id);
create index if not exists clientes_negocio_idx      on public.clientes (negocio_id);
create index if not exists productos_negocio_idx     on public.productos (negocio_id);
create index if not exists ventas_negocio_fecha_idx  on public.ventas (negocio_id, fecha desc);
create index if not exists recordatorios_negocio_idx on public.recordatorios (negocio_id, fecha) where estado = 'pendiente';

comment on column public.ventas.owner_id is
  'Quien registro la fila. Ya no decide el acceso: eso lo hace negocio_id.';

-- ── Creacion de los dos negocios y reparto de los datos existentes ───────
do $$
declare
  correo_demo constant text := current_setting('app.correo_demo', true);
  id_april uuid;
  id_demo  uuid;
  usuario_demo uuid;
  movidas int;
begin
  -- Los negocios, si no existen ya.
  insert into public.negocios (nombre) values ('April Collections')
  on conflict (lower(nombre)) do nothing;

  insert into public.negocios (nombre) values ('Demostracion')
  on conflict (lower(nombre)) do nothing;

  select id into id_april from public.negocios where lower(nombre) = 'april collections';
  select id into id_demo  from public.negocios where lower(nombre) = 'demostracion';

  select id into usuario_demo from auth.users where lower(email) = lower(correo_demo);

  -- Reparto: lo que creo la cuenta demo va al negocio de demostracion; todo lo
  -- demas, al negocio real. Solo se tocan las filas sin asignar, de modo que
  -- volver a ejecutar esto no mueve nada de sitio.
  update public.categorias    set negocio_id = case when owner_id = usuario_demo then id_demo else id_april end where negocio_id is null;
  update public.clientes      set negocio_id = case when owner_id = usuario_demo then id_demo else id_april end where negocio_id is null;
  update public.productos     set negocio_id = case when owner_id = usuario_demo then id_demo else id_april end where negocio_id is null;
  update public.ventas        set negocio_id = case when owner_id = usuario_demo then id_demo else id_april end where negocio_id is null;
  update public.recordatorios set negocio_id = case when owner_id = usuario_demo then id_demo else id_april end where negocio_id is null;

  -- Membresias: todo el que ya tenia datos pasa a ser administrador del
  -- negocio donde estaban. Sin esto, al activar las politicas nuevas nadie
  -- veria nada y la aplicacion quedaria vacia para todos.
  insert into public.miembros (negocio_id, usuario_id, rol)
  select distinct
    case when u.id = usuario_demo then id_demo else id_april end,
    u.id,
    'administrador'
  from auth.users u
  where exists (select 1 from public.clientes   c where c.owner_id = u.id)
     or exists (select 1 from public.productos  p where p.owner_id = u.id)
     or exists (select 1 from public.ventas     v where v.owner_id = u.id)
  on conflict (negocio_id, usuario_id) do nothing;

  get diagnostics movidas = row_count;

  raise notice 'Negocios listos. Membresias creadas en esta ejecucion: %.', movidas;
  raise notice 'April Collections: %  ·  Demostracion: %', id_april, id_demo;
end $$;

-- Ya no puede haber filas sin negocio.
do $$
begin
  alter table public.categorias    alter column negocio_id set not null;
  alter table public.clientes      alter column negocio_id set not null;
  alter table public.productos     alter column negocio_id set not null;
  alter table public.ventas        alter column negocio_id set not null;
  alter table public.recordatorios alter column negocio_id set not null;
exception
  when not_null_violation then
    raise exception 'Quedan filas sin negocio asignado. Revisa el reparto antes de continuar.';
end $$;

-- ── Politicas ─────────────────────────────────────────────────────────────
-- Se separan lectura y escritura: un lector consulta pero no modifica.

alter table public.negocios enable row level security;
alter table public.miembros enable row level security;

drop policy if exists "negocios propios" on public.negocios;
create policy "negocios propios"
  on public.negocios for select
  using (id in (select public.negocios_del_usuario()));

-- Cada quien ve las membresias de sus negocios: es lo que permite mostrar
-- quien mas tiene acceso. Nadie las modifica desde la aplicacion.
drop policy if exists "miembros de mis negocios" on public.miembros;
create policy "miembros de mis negocios"
  on public.miembros for select
  using (negocio_id in (select public.negocios_del_usuario()));

-- Las cinco tablas del negocio siguen el mismo patron.
do $$
declare
  t text;
begin
  foreach t in array array['categorias', 'clientes', 'productos', 'ventas', 'recordatorios']
  loop
    -- Fuera las politicas del modelo anterior, basadas en owner_id.
    execute format('drop policy if exists %I on public.%I', t || ' propias', t);
    execute format('drop policy if exists %I on public.%I', t || ' propios', t);
    execute format('drop policy if exists "leer %s del negocio" on public.%I', t, t);
    execute format('drop policy if exists "escribir %s del negocio" on public.%I', t, t);

    execute format($f$
      create policy "leer %1$s del negocio"
        on public.%1$I for select
        using (negocio_id in (select public.negocios_del_usuario()))
    $f$, t);

    execute format($f$
      create policy "escribir %1$s del negocio"
        on public.%1$I for all
        using (negocio_id in (select public.negocios_que_puede_escribir()))
        with check (negocio_id in (select public.negocios_que_puede_escribir()))
    $f$, t);
  end loop;
end $$;

-- Las tablas hijas pasan a comprobar la pertenencia a traves de su venta.
drop policy if exists "lineas de ventas propias" on public.venta_items;
drop policy if exists "leer lineas del negocio" on public.venta_items;
create policy "leer lineas del negocio"
  on public.venta_items for select
  using (exists (
    select 1 from public.ventas v
    where v.id = venta_items.venta_id
      and v.negocio_id in (select public.negocios_del_usuario())
  ));

drop policy if exists "escribir lineas del negocio" on public.venta_items;
create policy "escribir lineas del negocio"
  on public.venta_items for all
  using (exists (
    select 1 from public.ventas v
    where v.id = venta_items.venta_id
      and v.negocio_id in (select public.negocios_que_puede_escribir())
  ))
  with check (exists (
    select 1 from public.ventas v
    where v.id = venta_items.venta_id
      and v.negocio_id in (select public.negocios_que_puede_escribir())
  ));

drop policy if exists "abonos de ventas propias" on public.abonos;
drop policy if exists "leer abonos del negocio" on public.abonos;
create policy "leer abonos del negocio"
  on public.abonos for select
  using (exists (
    select 1 from public.ventas v
    where v.id = abonos.venta_id
      and v.negocio_id in (select public.negocios_del_usuario())
  ));

drop policy if exists "escribir abonos del negocio" on public.abonos;
create policy "escribir abonos del negocio"
  on public.abonos for all
  using (exists (
    select 1 from public.ventas v
    where v.id = abonos.venta_id
      and v.negocio_id in (select public.negocios_que_puede_escribir())
  ))
  with check (exists (
    select 1 from public.ventas v
    where v.id = abonos.venta_id
      and v.negocio_id in (select public.negocios_que_puede_escribir())
  ));

-- ── Indicadores ───────────────────────────────────────────────────────────
-- Se reagrupan por negocio: antes cada persona veia su propio total, que era
-- justo el problema que esta migracion corrige.
--
-- Se BORRAN antes de recrearlas, y no se usa CREATE OR REPLACE VIEW, porque
-- esa forma solo admite anadir columnas al final: no puede renombrar ni
-- reordenar las que ya existen. Aqui owner_id pasa a ser negocio_id en la
-- misma posicion, y Postgres lo rechaza con
--   "cannot change name of view column owner_id to negocio_id".
--
-- El orden del borrado va de la que depende a la de la que depende: las cuatro
-- vistas de KPI leen de ventas_con_saldo.
drop view if exists public.kpi_ventas_por_mes;
drop view if exists public.kpi_deuda_por_cliente;
drop view if exists public.kpi_cobrado_por_dia;
drop view if exists public.kpi_stock_bajo;
drop view if exists public.ventas_con_saldo;

create view public.ventas_con_saldo as
select
  v.id,
  v.negocio_id,
  v.owner_id,
  v.cliente_id,
  v.fecha,
  v.tipo_pago,
  coalesce(t.total_centavos, 0)                                 as total_centavos,
  coalesce(a.cobrado_centavos, 0)                               as cobrado_centavos,
  greatest(coalesce(t.total_centavos, 0) - coalesce(a.cobrado_centavos, 0), 0)
                                                                as pendiente_centavos,
  coalesce(t.total_centavos, 0) - coalesce(t.costo_centavos, 0) as ganancia_centavos
from public.ventas v
left join (
  select venta_id,
         sum(precio_centavos * cantidad) as total_centavos,
         sum(costo_centavos  * cantidad) as costo_centavos
  from public.venta_items
  group by venta_id
) t on t.venta_id = v.id
left join (
  select venta_id, sum(monto_centavos) as cobrado_centavos
  from public.abonos
  group by venta_id
) a on a.venta_id = v.id;

alter view public.ventas_con_saldo set (security_invoker = on);

create view public.kpi_ventas_por_mes as
select
  s.negocio_id,
  date_trunc('month', s.fecha)::date as mes,
  count(*)                           as numero_ventas,
  sum(s.total_centavos)              as vendido_centavos,
  sum(s.ganancia_centavos)           as ganancia_centavos,
  case
    when sum(s.total_centavos) > 0
      then round(sum(s.ganancia_centavos)::numeric * 100 / sum(s.total_centavos), 1)
    else 0
  end                                as margen_porcentaje
from public.ventas_con_saldo s
group by s.negocio_id, date_trunc('month', s.fecha);

alter view public.kpi_ventas_por_mes set (security_invoker = on);

create view public.kpi_deuda_por_cliente as
select
  s.negocio_id,
  c.id                      as cliente_id,
  c.nombre,
  c.dni,
  count(*)                  as ventas_con_deuda,
  sum(s.pendiente_centavos) as debe_centavos,
  min(s.fecha)              as deuda_mas_antigua
from public.ventas_con_saldo s
join public.clientes c on c.id = s.cliente_id
where s.pendiente_centavos > 0
group by s.negocio_id, c.id, c.nombre, c.dni;

alter view public.kpi_deuda_por_cliente set (security_invoker = on);

create view public.kpi_cobrado_por_dia as
select
  v.negocio_id,
  a.fecha,
  count(*)              as numero_abonos,
  sum(a.monto_centavos) as cobrado_centavos
from public.abonos a
join public.ventas v on v.id = a.venta_id
group by v.negocio_id, a.fecha;

alter view public.kpi_cobrado_por_dia set (security_invoker = on);

create view public.kpi_stock_bajo as
select
  p.negocio_id,
  p.id as producto_id,
  p.nombre,
  p.categoria,
  p.stock,
  case when p.stock = 0 then 'agotado' else 'bajo' end as nivel
from public.productos p
where p.stock <= 5;

alter view public.kpi_stock_bajo set (security_invoker = on);

-- ── Registro ──────────────────────────────────────────────────────────────
select public.registrar_migracion('0006', 'negocios_y_miembros');
