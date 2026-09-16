-- April Collections — cambio del correo de la dueña del negocio
--
-- QUE PROBLEMA RESUELVE
-- La cuenta autorizada para la dueña era un correo personal. Pasa a ser una
-- cuenta propia del negocio, aprilcollections2026@gmail.com.
--
-- POR QUE NO SE EDITA 0004 Y YA
-- 0004 ya se ejecuto: el correo viejo esta dentro de accesos_autorizados, y su
-- insert es `on conflict do nothing`, asi que volver a ejecutarlo no cambiaria
-- nada. Ademas, una migracion aplicada es un hecho registrado; corregirla en
-- silencio borra el rastro de que esto cambio y cuando. 0004 se actualiza para
-- que una instalacion desde cero salga bien, y este archivo arregla la base que
-- ya existe. Las dos rutas terminan en el mismo estado.
--
-- IDEMPOTENTE. REQUIERE 0004 ejecutado antes.

do $$
declare
  correo_viejo constant text := 'daysigomez230@gmail.com';
  correo_nuevo constant text := 'aprilcollections2026@gmail.com';

  tenia_cuenta boolean;
  era_miembro  int;
begin
  -- Primero se autoriza el nuevo. Si algo fallara despues, el peor caso es que
  -- haya dos correos autorizados, no que no haya ninguno.
  insert into public.accesos_autorizados (correo, motivo)
  values (correo_nuevo, 'Dueña del negocio')
  on conflict (correo) do nothing;

  -- ¿Llego a usarse el correo viejo? El disparador de 0004 solo actua al crear
  -- la cuenta, asi que quitar la autorizacion no cierra una sesion abierta ni
  -- borra nada: dejaria una cuenta viva que ya no deberia existir. Se avisa en
  -- vez de arreglarlo por cuenta propia, porque borrar una cuenta con datos
  -- dentro no es algo que deba pasar sin que alguien lo decida.
  select exists (select 1 from auth.users where lower(email) = correo_viejo)
  into tenia_cuenta;

  if tenia_cuenta then
    select count(*) into era_miembro
    from public.miembros m
    join auth.users u on u.id = m.usuario_id
    where lower(u.email) = correo_viejo;

    raise warning 'La cuenta % ya existe en auth.users (membresias: %).', correo_viejo, era_miembro;
    raise warning 'Se deja su autorizacion intacta para no dejar una cuenta huerfana.';
    raise warning 'Revisala en Authentication -> Users y borrala a mano si no debe seguir.';
  else
    delete from public.accesos_autorizados where correo = correo_viejo;
    raise notice 'Autorizacion de % retirada: nunca se uso.', correo_viejo;
  end if;

  raise notice 'Autorizada la dueña como %.', correo_nuevo;
end $$;

-- ── Registro ──────────────────────────────────────────────────────────────
select public.registrar_migracion('0007', 'correo_de_la_duenia');
