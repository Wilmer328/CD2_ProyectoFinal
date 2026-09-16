-- April Collections — esquema inicial
--
-- Convenciones que se aplican en todo el esquema:
--
--   * El dinero se guarda en CENTAVOS ENTEROS (bigint), nunca en numeric ni
--     float. Es la misma decision que src/domain/money.js: con decimales, un
--     total repartido en abonos parciales acumula error y una deuda saldada
--     queda con fracciones pendientes.
--
--   * Toda tabla del negocio lleva owner_id apuntando a auth.users. Es lo que
--     permite que las politicas RLS separen los datos de cada usuaria sin
--     escribir un solo filtro en el cliente.
--
--   * Las fechas de calendario (la fecha de una venta, el dia de un cobro) van
--     como date, no como timestamptz: "el 1 de agosto" no tiene hora ni zona.
--     Guardarlas con zona reintroduce el error que corrigio src/domain/dates.js.
--
--   * Las marcas de tiempo de auditoria si son timestamptz, porque ahi el
--     instante exacto si importa.
--
--   * Todo el guion es IDEMPOTENTE: volver a ejecutarlo no falla ni duplica
--     nada. Las tablas e indices usan IF NOT EXISTS y la vista OR REPLACE.
--     Una migracion que solo se puede correr una vez obliga a recordar si ya
--     se corrio, y recordar no es una garantia.
--
-- REQUIERE haber ejecutado antes 0000_registro_de_migraciones.sql.

-- ── Perfil ────────────────────────────────────────────────────────────────
-- Extiende auth.users con lo que la aplicacion necesita mostrar. Supabase no
-- permite anadir columnas a auth.users, de ahi esta tabla.
create table if not exists public.perfiles (
  id          uuid primary key references auth.users (id) on delete cascade,
  correo      text not null,
  nombre      text,
  creado_en   timestamptz not null default now()
);

comment on table public.perfiles is
  'Datos de presentacion del usuario autenticado. Uno por cuenta.';

-- ── Categorias del catalogo ───────────────────────────────────────────────
-- Las administra la usuaria, no vienen fijas en el codigo.
create table if not exists public.categorias (
  id          uuid primary key default gen_random_uuid(),
  owner_id    uuid not null references auth.users (id) on delete cascade,
  nombre      text not null check (length(trim(nombre)) between 1 and 24),
  creado_en   timestamptz not null default now()
);

-- No puede haber dos categorias con el mismo nombre para la misma usuaria.
-- Se compara en minusculas para que "Joyeria" y "joyeria" no convivan como
-- rubros distintos, igual que hace src/domain/categories.js.
create unique index if not exists categorias_owner_nombre_idx
  on public.categorias (owner_id, lower(nombre));

-- ── Clientas ──────────────────────────────────────────────────────────────
create table if not exists public.clientes (
  id          uuid primary key default gen_random_uuid(),
  owner_id    uuid not null references auth.users (id) on delete cascade,
  nombre      text not null check (length(trim(nombre)) > 0),
  -- El DNI hondureno tiene 13 digitos. Es opcional: la usuaria registra
  -- clientas en medio de una venta y no siempre tiene el documento a la vista.
  dni         text check (dni is null or dni ~ '^[0-9]{13}$'),
  telefono    text,
  creado_en   timestamptz not null default now()
);

-- Unico cuando se informa. El indice parcial deja pasar varios NULL, que es lo
-- que se quiere: muchas clientas sin DNI conviven sin chocar entre si.
create unique index if not exists clientes_owner_dni_idx
  on public.clientes (owner_id, dni)
  where dni is not null;

create index if not exists clientes_owner_idx on public.clientes (owner_id);

-- ── Productos ─────────────────────────────────────────────────────────────
create table if not exists public.productos (
  id               uuid primary key default gen_random_uuid(),
  owner_id         uuid not null references auth.users (id) on delete cascade,
  nombre           text not null check (length(trim(nombre)) > 0),
  categoria        text not null,
  costo_centavos   bigint not null default 0 check (costo_centavos >= 0),
  precio_centavos  bigint not null default 0 check (precio_centavos >= 0),
  -- El stock nunca puede quedar negativo: si el sistema dice -3 unidades, el
  -- dato es falso y deja de servir para nada.
  stock            integer not null default 0 check (stock >= 0),
  creado_en        timestamptz not null default now()
);

create index if not exists productos_owner_idx on public.productos (owner_id);

-- ── Ventas ────────────────────────────────────────────────────────────────
-- El total NO se guarda: es la suma de las lineas y se calcula. Guardarlo
-- abriria la puerta a que quedara desincronizado con sus propias lineas.
create table if not exists public.ventas (
  id          uuid primary key default gen_random_uuid(),
  owner_id    uuid not null references auth.users (id) on delete cascade,
  cliente_id  uuid not null references public.clientes (id) on delete restrict,
  fecha       date not null,
  tipo_pago   text not null check (tipo_pago in ('contado', 'abono', 'credito')),
  creado_en   timestamptz not null default now()
);

create index if not exists ventas_owner_fecha_idx on public.ventas (owner_id, fecha desc);
create index if not exists ventas_cliente_idx on public.ventas (cliente_id);

-- ── Lineas de venta ───────────────────────────────────────────────────────
create table if not exists public.venta_items (
  id               uuid primary key default gen_random_uuid(),
  venta_id         uuid not null references public.ventas (id) on delete cascade,
  -- Puede ser nulo: la usuaria vende cosas que no estan en el catalogo.
  producto_id      uuid references public.productos (id) on delete set null,
  -- Nombre, precio y costo se copian al momento de vender a proposito: son el
  -- valor HISTORICO. Si manana sube el costo del producto, la ganancia de las
  -- ventas viejas no debe cambiar.
  nombre           text not null check (length(trim(nombre)) > 0),
  precio_centavos  bigint not null check (precio_centavos >= 0),
  costo_centavos   bigint not null default 0 check (costo_centavos >= 0),
  cantidad         integer not null check (cantidad >= 1)
);

create index if not exists venta_items_venta_idx on public.venta_items (venta_id);

-- ── Abonos ────────────────────────────────────────────────────────────────
create table if not exists public.abonos (
  id              uuid primary key default gen_random_uuid(),
  venta_id        uuid not null references public.ventas (id) on delete cascade,
  monto_centavos  bigint not null check (monto_centavos > 0),
  fecha           date not null,
  creado_en       timestamptz not null default now()
);

create index if not exists abonos_venta_idx on public.abonos (venta_id);

-- ── Recordatorios de cobro ────────────────────────────────────────────────
create table if not exists public.recordatorios (
  id          uuid primary key default gen_random_uuid(),
  owner_id    uuid not null references auth.users (id) on delete cascade,
  cliente_id  uuid not null references public.clientes (id) on delete cascade,
  venta_id    uuid references public.ventas (id) on delete cascade,
  fecha       date not null,
  hora        time not null default '09:00',
  nota        text,
  estado      text not null default 'pendiente'
              check (estado in ('pendiente', 'completado', 'descartado')),
  -- Cuando se lanzo el ultimo aviso y si la usuaria ya lo atendio. Con esto el
  -- aviso insiste hasta ser visto en lugar de perderse.
  avisado_en  timestamptz,
  visto       boolean not null default false,
  creado_en   timestamptz not null default now()
);

create index if not exists recordatorios_owner_fecha_idx
  on public.recordatorios (owner_id, fecha)
  where estado = 'pendiente';

-- ── Vista de saldos ───────────────────────────────────────────────────────
-- Calcula total, cobrado y pendiente de cada venta en un solo lugar. Evita
-- repetir el mismo calculo en cada consulta, que es justo el problema que
-- tenia la version anterior de la aplicacion: el saldo pendiente estaba
-- duplicado en siete sitios.
create or replace view public.ventas_con_saldo as
select
  v.id,
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

comment on view public.ventas_con_saldo is
  'Total, cobrado, pendiente y ganancia de cada venta. El pendiente nunca es negativo: no se manejan saldos a favor.';

-- ── Registro ──────────────────────────────────────────────────────────────
select public.registrar_migracion('0001', 'esquema_inicial');
