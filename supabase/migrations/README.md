# Migraciones

Son **las mismas ocho** de la aplicación April Collections, copiadas sin cambios.
Así el proyecto de Supabase de este curso tiene exactamente el esquema de
producción, y el ETL extrae de las mismas tablas, con los mismos nombres y
tipos, que existen en la aplicación real.

Se ejecutan **en orden numérico** desde el SQL Editor de Supabase. Todas son
idempotentes: volver a correr cualquiera no falla ni duplica nada.

| # | Archivo | Qué hace |
|---|---------|----------|
| 0000 | `0000_registro_de_migraciones.sql` | Tabla que registra qué migraciones se aplicaron |
| 0001 | `0001_esquema_inicial.sql` | 8 tablas, índices y la vista de saldos |
| 0002 | `0002_politicas_rls.sql` | RLS, políticas y alta automática del perfil |
| 0003 | `0003_datos_demo.sql` | Datos de demostración: el punto de partida del dataset |
| 0004 | `0004_control_de_acceso.sql` | Lista de correos autorizados |
| 0005 | `0005_kpis.sql` | Vistas de indicadores |
| 0006 | `0006_negocios_y_miembros.sql` | El negocio como unidad de acceso |
| 0007 | `0007_correo_de_la_duenia.sql` | Cambio de correo de la dueña |

## Antes de ejecutarlas

`0003` y `0006` buscan al usuario `demo@jsanchez.site` en `auth.users`. Hay que
**crearlo primero** desde Authentication → Users → Add user, con cualquier
contraseña. Sin ese usuario, `0003` avisa y no siembra nada.

## Lo que no importa aquí

`0004` y `0007` administran quién puede iniciar sesión en la aplicación. En este
proyecto nadie inicia sesión —el ETL entra directo a PostgreSQL—, así que son
inofensivas. Se conservan para que el esquema sea idéntico al real y no haya que
explicar por qué faltan dos.

## Comprobar qué está aplicado

```sql
select * from public.migraciones order by version;
```
