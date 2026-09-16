-- April Collections — datos de demostración
--
-- Siembra un negocio ficticio completo para la cuenta demo, de modo que quien
-- entre a evaluar el producto vea la aplicación funcionando y no una pantalla
-- vacía.
--
-- ANTES DE EJECUTAR:
--   1. Supabase -> Authentication -> Providers: activa "Email".
--   2. Supabase -> Authentication -> Users -> Add user -> Create new user.
--      Marca "Auto Confirm User".
--   3. Cambia el correo de la línea señalada más abajo por el que creaste.
--
-- Todos los nombres, teléfonos y documentos son INVENTADOS. No corresponden a
-- ninguna persona real: los datos de las clientas reales del negocio no deben
-- salir nunca de la cuenta de su dueña.
--
-- El guion es idempotente: borra los datos demo anteriores antes de sembrar,
-- así se puede volver a ejecutar cuantas veces haga falta.

do $$
declare
  -- ┌──────────────────────────────────────────────────────────────────────┐
  -- │  CAMBIA ESTE CORREO POR EL DE TU CUENTA DEMO                         │
  -- └──────────────────────────────────────────────────────────────────────┘
 correo_demo constant text := 'demo@jsanchez.site';

  duenio uuid;

  -- Clientas
  maria_1 uuid; karla uuid; ana uuid; maria_2 uuid; sofia uuid; doris uuid;

  -- Productos
  aretes uuid; collar uuid; pulsera uuid; labial uuid; base uuid;
  paleta uuid; tacon uuid; planas uuid; floral uuid; citrico uuid;

  -- Ventas
  venta_pagada uuid; venta_abonada uuid; venta_credito uuid;
  venta_vieja uuid; venta_mes_pasado uuid; venta_libre uuid;
begin
  select id into duenio from auth.users where email = correo_demo;

  if duenio is null then
    raise exception
      'No existe ningun usuario con el correo %. Crealo primero en Authentication -> Users y vuelve a ejecutar este guion.',
      correo_demo;
  end if;

  -- Limpieza: las claves foráneas en cascada se llevan items, abonos y
  -- recordatorios asociados.
  delete from public.ventas        where owner_id = duenio;
  delete from public.recordatorios where owner_id = duenio;
  delete from public.clientes      where owner_id = duenio;
  delete from public.productos     where owner_id = duenio;
  delete from public.categorias    where owner_id = duenio;

  -- ── Categorías ─────────────────────────────────────────────────────────
  insert into public.categorias (owner_id, nombre) values
    (duenio, 'Joyería'),
    (duenio, 'Maquillaje'),
    (duenio, 'Sandalias'),
    (duenio, 'Perfumes'),
    (duenio, 'Otro');

  -- ── Clientas ───────────────────────────────────────────────────────────
  -- Dos se llaman igual a propósito: es el caso que motivó añadir el DNI, y
  -- deja demostrar en vivo cómo el buscador las distingue.
  insert into public.clientes (owner_id, nombre, dni, telefono) values
    (duenio, 'María Fernanda López', '0801199512345', '9988-1122') returning id into maria_1;
  insert into public.clientes (owner_id, nombre, dni, telefono) values
    (duenio, 'María Fernanda López', '0703199834567', '8899-7788') returning id into maria_2;
  insert into public.clientes (owner_id, nombre, dni, telefono) values
    (duenio, 'Karla Yamileth Cruz', '0501200023456', '9877-3344') returning id into karla;
  insert into public.clientes (owner_id, nombre, dni, telefono) values
    (duenio, 'Sofía Alejandra Mejía', '0801200134568', '9765-4321') returning id into sofia;
  -- Sin DNI: registradas con prisa en medio de una venta.
  insert into public.clientes (owner_id, nombre, dni, telefono) values
    (duenio, 'Ana Gabriela Munguía', null, '3312-5566') returning id into ana;
  insert into public.clientes (owner_id, nombre, dni, telefono) values
    (duenio, 'Doris Elena Zelaya', null, null) returning id into doris;

  -- ── Productos ──────────────────────────────────────────────────────────
  -- Importes en centavos: 25000 son 250.00 lempiras.
  insert into public.productos (owner_id, nombre, categoria, costo_centavos, precio_centavos, stock) values
    (duenio, 'Aretes dorados',        'Joyería',    15000, 25000, 12) returning id into aretes;
  insert into public.productos (owner_id, nombre, categoria, costo_centavos, precio_centavos, stock) values
    (duenio, 'Collar de perlas',      'Joyería',    28000, 45000,  5) returning id into collar;
  -- Agotado: deja demostrar que no se puede vender sin existencias.
  insert into public.productos (owner_id, nombre, categoria, costo_centavos, precio_centavos, stock) values
    (duenio, 'Pulsera de acero',      'Joyería',     9000, 18000,  0) returning id into pulsera;
  insert into public.productos (owner_id, nombre, categoria, costo_centavos, precio_centavos, stock) values
    (duenio, 'Labial mate',           'Maquillaje',  7500, 15000, 20) returning id into labial;
  insert into public.productos (owner_id, nombre, categoria, costo_centavos, precio_centavos, stock) values
    (duenio, 'Base líquida',          'Maquillaje', 22000, 38000,  8) returning id into base;
  -- Stock bajo: el indicador del catálogo se pone en ámbar.
  insert into public.productos (owner_id, nombre, categoria, costo_centavos, precio_centavos, stock) values
    (duenio, 'Paleta de sombras',     'Maquillaje', 35000, 59000,  3) returning id into paleta;
  insert into public.productos (owner_id, nombre, categoria, costo_centavos, precio_centavos, stock) values
    (duenio, 'Sandalias de tacón',    'Sandalias',  45000, 75000,  6) returning id into tacon;
  insert into public.productos (owner_id, nombre, categoria, costo_centavos, precio_centavos, stock) values
    (duenio, 'Sandalias planas',      'Sandalias',  30000, 52000, 10) returning id into planas;
  insert into public.productos (owner_id, nombre, categoria, costo_centavos, precio_centavos, stock) values
    (duenio, 'Perfume floral',        'Perfumes',   60000, 95000,  4) returning id into floral;
  insert into public.productos (owner_id, nombre, categoria, costo_centavos, precio_centavos, stock) values
    (duenio, 'Perfume cítrico',       'Perfumes',   55000, 89000,  7) returning id into citrico;

  -- ── Ventas ─────────────────────────────────────────────────────────────
  -- Las fechas son relativas a hoy para que la demostración siempre se vea
  -- actual, sin tener que volver a sembrar cada mes.

  -- 1. Al contado, saldada el mismo día.
  insert into public.ventas (owner_id, cliente_id, fecha, tipo_pago)
    values (duenio, maria_1, current_date - 3, 'contado') returning id into venta_pagada;
  insert into public.venta_items (venta_id, producto_id, nombre, precio_centavos, costo_centavos, cantidad) values
    (venta_pagada, aretes, 'Aretes dorados', 25000, 15000, 2),
    (venta_pagada, labial, 'Labial mate',    15000,  7500, 1);
  insert into public.abonos (venta_id, monto_centavos, fecha)
    values (venta_pagada, 65000, current_date - 3);

  -- 2. Con abono inicial y saldo pendiente. Es el caso central del negocio.
  insert into public.ventas (owner_id, cliente_id, fecha, tipo_pago)
    values (duenio, karla, current_date - 10, 'abono') returning id into venta_abonada;
  insert into public.venta_items (venta_id, producto_id, nombre, precio_centavos, costo_centavos, cantidad) values
    (venta_abonada, floral, 'Perfume floral',     95000, 60000, 1),
    (venta_abonada, tacon,  'Sandalias de tacón', 75000, 45000, 1);
  -- Total 170000; abonó 60000 al inicio y 40000 después. Debe 70000.
  insert into public.abonos (venta_id, monto_centavos, fecha) values
    (venta_abonada, 60000, current_date - 10),
    (venta_abonada, 40000, current_date - 4);

  -- 3. Totalmente a crédito, sin abonar nada todavía.
  insert into public.ventas (owner_id, cliente_id, fecha, tipo_pago)
    values (duenio, ana, current_date - 6, 'credito') returning id into venta_credito;
  insert into public.venta_items (venta_id, producto_id, nombre, precio_centavos, costo_centavos, cantidad) values
    (venta_credito, paleta, 'Paleta de sombras', 59000, 35000, 1),
    (venta_credito, base,   'Base líquida',      38000, 22000, 2);

  -- 4. Venta antigua con deuda arrastrada: alimenta el aviso de cobro vencido.
  insert into public.ventas (owner_id, cliente_id, fecha, tipo_pago)
    values (duenio, doris, current_date - 25, 'abono') returning id into venta_vieja;
  insert into public.venta_items (venta_id, producto_id, nombre, precio_centavos, costo_centavos, cantidad) values
    (venta_vieja, collar, 'Collar de perlas', 45000, 28000, 1);
  insert into public.abonos (venta_id, monto_centavos, fecha)
    values (venta_vieja, 15000, current_date - 25);

  -- 5. Del mes pasado, para que el filtro de meses del resumen tenga qué mostrar.
  insert into public.ventas (owner_id, cliente_id, fecha, tipo_pago)
    values (duenio, sofia, current_date - 40, 'contado') returning id into venta_mes_pasado;
  insert into public.venta_items (venta_id, producto_id, nombre, precio_centavos, costo_centavos, cantidad) values
    (venta_mes_pasado, citrico, 'Perfume cítrico',  89000, 55000, 1),
    (venta_mes_pasado, planas,  'Sandalias planas', 52000, 30000, 1);
  insert into public.abonos (venta_id, monto_centavos, fecha)
    values (venta_mes_pasado, 141000, current_date - 40);

  -- 6. Producto libre, de los que no están en el catálogo.
  insert into public.ventas (owner_id, cliente_id, fecha, tipo_pago)
    values (duenio, maria_2, current_date - 1, 'contado') returning id into venta_libre;
  insert into public.venta_items (venta_id, producto_id, nombre, precio_centavos, costo_centavos, cantidad)
    values (venta_libre, null, 'Bolso encargado', 120000, 80000, 1);
  insert into public.abonos (venta_id, monto_centavos, fecha)
    values (venta_libre, 120000, current_date - 1);

  -- ── Recordatorios de cobro ─────────────────────────────────────────────
  -- Cubren los tres estados y los tres momentos, para que la pantalla se vea
  -- completa y se pueda demostrar el aviso sin esperar.

  -- Vencido: la fecha prometida ya pasó y sigue sin cobrarse.
  insert into public.recordatorios (owner_id, cliente_id, venta_id, fecha, hora, nota, estado) values
    (duenio, doris, venta_vieja, current_date - 5, '09:00',
     'Dijo que pasaba el lunes por la tarde', 'pendiente');

  -- Para hoy, dentro de un rato: dispara el aviso durante la demostración.
  -- La zona se escribe explícita porque el servidor de Supabase corre en UTC;
  -- con localtime a secas el recordatorio quedaría seis horas corrido.
  insert into public.recordatorios (owner_id, cliente_id, venta_id, fecha, hora, nota, estado) values
    (duenio, karla, venta_abonada,
     (now() at time zone 'America/Tegucigalpa')::date,
     ((now() at time zone 'America/Tegucigalpa') + interval '20 minutes')::time,
     'Le queda el último abono', 'pendiente');

  -- Futuro.
  insert into public.recordatorios (owner_id, cliente_id, venta_id, fecha, hora, nota, estado) values
    (duenio, ana, venta_credito, current_date + 3, '10:30',
     'Cobra el día 15, dijo que ese día paga todo', 'pendiente');

  -- Ya cobrado y descartado, para que se vean los tres estados en el filtro.
  insert into public.recordatorios (owner_id, cliente_id, venta_id, fecha, hora, nota, estado) values
    (duenio, maria_1, null, current_date - 8, '09:00', 'Ya pagó completo', 'completado'),
    (duenio, sofia,   null, current_date - 12, '14:00', 'Se equivocó de fecha', 'descartado');

  raise notice 'Datos demo sembrados para % (%).', correo_demo, duenio;
end $$;

-- ── Registro ──────────────────────────────────────────────────────────────
select public.registrar_migracion('0003', 'datos_demo');
