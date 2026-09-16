-- April Collections — politicas de seguridad a nivel de fila (RLS)
--
-- Esta migracion es la barrera de seguridad real del sistema. Todo lo demas
-- —el guard del cliente, ocultar botones— es comodidad de interfaz: se salta
-- desactivando JavaScript. Postgres evalua estas politicas en el servidor, en
-- cada consulta, contra el JWT que emitio Supabase Auth.
--
-- Sin RLS activo, la anon key permitiria a cualquiera leer la base entera. Por
-- eso se habilita en TODAS las tablas, incluidas las que no tienen owner_id.
--
-- IDEMPOTENTE: cada politica y el disparador se borran antes de crearse, y la
-- funcion usa OR REPLACE. PostgreSQL no admite CREATE POLICY IF NOT EXISTS, de
-- ahi el DROP previo en lugar de una guarda mas corta.
--
-- REQUIERE 0000 y 0001 ejecutados antes.

-- ── Habilitar RLS ─────────────────────────────────────────────────────────
-- Al habilitarlo sin politicas, la tabla queda cerrada por completo. Las
-- politicas de abajo abren solo lo justo.
alter table public.perfiles       enable row level security;
alter table public.categorias     enable row level security;
alter table public.clientes       enable row level security;
alter table public.productos      enable row level security;
alter table public.ventas         enable row level security;
alter table public.venta_items    enable row level security;
alter table public.abonos         enable row level security;
alter table public.recordatorios  enable row level security;

-- ── Perfil ────────────────────────────────────────────────────────────────
-- Cada quien ve y edita el suyo. No hay politica de borrado: el perfil
-- desaparece con la cuenta, por la clave foranea en cascada.
drop policy if exists "perfil propio: leer" on public.perfiles;
create policy "perfil propio: leer"
  on public.perfiles for select
  using (auth.uid() = id);

drop policy if exists "perfil propio: crear" on public.perfiles;
create policy "perfil propio: crear"
  on public.perfiles for insert
  with check (auth.uid() = id);

drop policy if exists "perfil propio: actualizar" on public.perfiles;
create policy "perfil propio: actualizar"
  on public.perfiles for update
  using (auth.uid() = id)
  with check (auth.uid() = id);

-- ── Tablas con owner_id ───────────────────────────────────────────────────
-- Mismo patron para las cuatro. Se escriben una por una y no con un bucle
-- porque las politicas deben poder leerse tal cual estan en la base.
--
-- USING filtra lo que se puede leer o afectar; WITH CHECK valida lo que se
-- intenta escribir. Hacen falta las dos: sin WITH CHECK, alguien podria
-- insertar una fila con el owner_id de otra persona.

drop policy if exists "categorias propias" on public.categorias;
create policy "categorias propias"
  on public.categorias for all
  using (auth.uid() = owner_id)
  with check (auth.uid() = owner_id);

drop policy if exists "clientes propios" on public.clientes;
create policy "clientes propios"
  on public.clientes for all
  using (auth.uid() = owner_id)
  with check (auth.uid() = owner_id);

drop policy if exists "productos propios" on public.productos;
create policy "productos propios"
  on public.productos for all
  using (auth.uid() = owner_id)
  with check (auth.uid() = owner_id);

drop policy if exists "ventas propias" on public.ventas;
create policy "ventas propias"
  on public.ventas for all
  using (auth.uid() = owner_id)
  with check (auth.uid() = owner_id);

drop policy if exists "recordatorios propios" on public.recordatorios;
create policy "recordatorios propios"
  on public.recordatorios for all
  using (auth.uid() = owner_id)
  with check (auth.uid() = owner_id);

-- ── Tablas hijas ──────────────────────────────────────────────────────────
-- venta_items y abonos no llevan owner_id: pertenecen a una venta, y la venta
-- ya tiene dueno. Duplicar la columna abriria la posibilidad de que una linea
-- acabara con un dueno distinto al de su venta.
--
-- El precio de esta decision es que cada consulta comprueba la pertenencia con
-- un EXISTS sobre ventas. El indice de la clave primaria lo resuelve, y se
-- prefiere pagar eso antes que arriesgar datos incoherentes.

drop policy if exists "lineas de ventas propias" on public.venta_items;
create policy "lineas de ventas propias"
  on public.venta_items for all
  using (
    exists (
      select 1 from public.ventas v
      where v.id = venta_items.venta_id and v.owner_id = auth.uid()
    )
  )
  with check (
    exists (
      select 1 from public.ventas v
      where v.id = venta_items.venta_id and v.owner_id = auth.uid()
    )
  );

drop policy if exists "abonos de ventas propias" on public.abonos;
create policy "abonos de ventas propias"
  on public.abonos for all
  using (
    exists (
      select 1 from public.ventas v
      where v.id = abonos.venta_id and v.owner_id = auth.uid()
    )
  )
  with check (
    exists (
      select 1 from public.ventas v
      where v.id = abonos.venta_id and v.owner_id = auth.uid()
    )
  );

-- ── Vista ─────────────────────────────────────────────────────────────────
-- Las vistas no tienen RLS propio: heredan el de sus tablas. Se declara con
-- security_invoker para que se evalue con los permisos de quien consulta y no
-- con los de quien la creo, que es el comportamiento por defecto y aqui seria
-- una fuga: cualquiera veria los saldos de todas las usuarias.
alter view public.ventas_con_saldo set (security_invoker = on);

-- ── Alta automatica del perfil ────────────────────────────────────────────
-- Crea el perfil en cuanto alguien se registra, para que la aplicacion no
-- tenga que acordarse de hacerlo despues del primer inicio de sesion.
create or replace function public.crear_perfil_al_registrarse()
returns trigger
language plpgsql
security definer
-- search_path fijo: sin esto, un search_path manipulado podria hacer que la
-- funcion, que corre con permisos elevados, apunte a otras tablas.
set search_path = public
as $$
begin
  insert into public.perfiles (id, correo, nombre)
  values (
    new.id,
    new.email,
    coalesce(new.raw_user_meta_data ->> 'full_name', new.raw_user_meta_data ->> 'name')
  )
  on conflict (id) do nothing;

  return new;
end;
$$;

drop trigger if exists al_crearse_usuario on auth.users;

create trigger al_crearse_usuario
  after insert on auth.users
  for each row
  execute function public.crear_perfil_al_registrarse();

-- ── Registro ──────────────────────────────────────────────────────────────
select public.registrar_migracion('0002', 'politicas_rls');
