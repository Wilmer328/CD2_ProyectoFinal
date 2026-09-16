-- April Collections — indicadores del negocio
--
-- Los cuatro numeros que la duena mira cada dia —ventas del mes, por cobrar,
-- ganancia y cobrado hoy— se calculaban recorriendo todas las ventas en el
-- navegador. Aqui se definen como vistas, para que el calculo viva en un solo
-- sitio y sea el mismo lo consulte quien lo consulte.
--
-- IDEMPOTENTE: todas usan CREATE OR REPLACE VIEW. Volver a ejecutar este guion
-- redefine las vistas sin tocar un solo dato.
--
-- Todas heredan las politicas RLS de sus tablas y se declaran con
-- security_invoker, asi que cada usuaria solo ve sus propios numeros. Sin eso,
-- una vista se evalua con los permisos de quien la creo y estos indicadores
-- mostrarian el negocio de todo el mundo.
--
-- REQUIERE 0000, 0001 y 0002 ejecutados antes.

-- ── Ventas, ganancia y margen por mes ─────────────────────────────────────
-- Alimenta las tarjetas del resumen. El mes se calcula con date_trunc sobre la
-- fecha de calendario, sin zona horaria de por medio: es la misma decision que
-- src/domain/dates.js, y evita que una venta del dia 1 cuente en el mes
-- anterior.
create or replace view public.kpi_ventas_por_mes as
select
  s.owner_id,
  date_trunc('month', s.fecha)::date              as mes,
  count(*)                                        as numero_ventas,
  sum(s.total_centavos)                           as vendido_centavos,
  sum(s.ganancia_centavos)                        as ganancia_centavos,
  -- Margen sobre lo vendido. Se protege la division: un mes sin ventas daria
  -- division por cero, no margen cero.
  case
    when sum(s.total_centavos) > 0
      then round(sum(s.ganancia_centavos)::numeric * 100 / sum(s.total_centavos), 1)
    else 0
  end                                             as margen_porcentaje
from public.ventas_con_saldo s
group by s.owner_id, date_trunc('month', s.fecha);

alter view public.kpi_ventas_por_mes set (security_invoker = on);

comment on view public.kpi_ventas_por_mes is
  'Ventas, ganancia y margen agrupados por mes. Alimenta las tarjetas del resumen.';

-- ── Deuda pendiente por clienta ───────────────────────────────────────────
-- Solo aparecen las que deben algo: una clienta al dia no es un pendiente y
-- ensuciaria el recuento de deudores.
create or replace view public.kpi_deuda_por_cliente as
select
  s.owner_id,
  c.id                            as cliente_id,
  c.nombre,
  c.dni,
  count(*)                        as ventas_con_deuda,
  sum(s.pendiente_centavos)       as debe_centavos,
  min(s.fecha)                    as deuda_mas_antigua
from public.ventas_con_saldo s
join public.clientes c on c.id = s.cliente_id
where s.pendiente_centavos > 0
group by s.owner_id, c.id, c.nombre, c.dni;

alter view public.kpi_deuda_por_cliente set (security_invoker = on);

comment on view public.kpi_deuda_por_cliente is
  'Cuanto debe cada clienta y desde cuando. Solo incluye las que tienen saldo.';

-- ── Cobrado por dia ───────────────────────────────────────────────────────
-- Se mide por la fecha del abono, no por la de la venta: lo que importa es
-- cuando entro el dinero.
create or replace view public.kpi_cobrado_por_dia as
select
  v.owner_id,
  a.fecha,
  count(*)                    as numero_abonos,
  sum(a.monto_centavos)       as cobrado_centavos
from public.abonos a
join public.ventas v on v.id = a.venta_id
group by v.owner_id, a.fecha;

alter view public.kpi_cobrado_por_dia set (security_invoker = on);

comment on view public.kpi_cobrado_por_dia is
  'Dinero recibido cada dia, contado por la fecha del abono y no la de la venta.';

-- ── Existencias que requieren atencion ────────────────────────────────────
-- El umbral de 5 unidades es el mismo que usa src/domain/inventory.js. Esta
-- duplicado a proposito: la base tiene que poder responder sin depender de que
-- la aplicacion le pase el valor.
create or replace view public.kpi_stock_bajo as
select
  p.owner_id,
  p.id  as producto_id,
  p.nombre,
  p.categoria,
  p.stock,
  case when p.stock = 0 then 'agotado' else 'bajo' end as nivel
from public.productos p
where p.stock <= 5;

alter view public.kpi_stock_bajo set (security_invoker = on);

comment on view public.kpi_stock_bajo is
  'Productos agotados o por agotarse. El umbral coincide con UMBRAL_STOCK_BAJO del dominio.';

-- ── Registro ──────────────────────────────────────────────────────────────
select public.registrar_migracion('0005', 'kpis');
