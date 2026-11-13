-- Rol de SOLO LECTURA para el dashboard de Puro Pockets (Hito 10).
--
-- Crea (o deja al día) el rol `puro_dashboard`: puede conectarse y leer las tablas de negocio que
-- el dashboard muestra. No puede escribir, no puede crear objetos y NO puede leer las tablas
-- oauth_* (tokens y clientes del MCP), idempotency_keys (respuestas guardadas) ni alembic_version.
-- La API del dashboard comprueba todo esto al arrancar y se niega a servir si el rol tiene más.
--
-- Este archivo NO contiene contraseñas. Después de ejecutarlo, fija la del rol tú mismo:
--     \password puro_dashboard
--
-- Uso (en el homelab, con la base levantada; se conecta con el rol propietario):
--     docker compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
--         < scripts/create_dashboard_role.sql
--     docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\password puro_dashboard"'
--
-- Es idempotente: se puede volver a ejecutar (por ejemplo, tras una migración que agregue una
-- tabla de negocio nueva, que entonces se agrega a la lista de GRANT SELECT de abajo).

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'puro_dashboard') THEN
        CREATE ROLE puro_dashboard LOGIN;
    END IF;
END
$$;

ALTER ROLE puro_dashboard
    LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;

-- Cada transacción del rol es de solo lectura (defensa adicional a los permisos)
ALTER ROLE puro_dashboard SET default_transaction_read_only = on;

DO $$
BEGIN
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO puro_dashboard', current_database());
END
$$;

-- Empezar de cero: nada en el esquema, ninguna tabla, ninguna secuencia
REVOKE ALL ON SCHEMA public FROM puro_dashboard;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM puro_dashboard;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM puro_dashboard;
GRANT USAGE ON SCHEMA public TO puro_dashboard;

-- Solo lectura de las tablas de negocio que el dashboard consulta (sin oauth_*, sin
-- idempotency_keys, sin alembic_version)
GRANT SELECT ON
    pockets,
    savings_goals,
    categories,
    budget_month_allocations,
    incomes,
    income_allocations,
    expenses,
    recurring_expenses,
    recurring_expense_amounts,
    transfers,
    month_closures,
    closure_adjustments
TO puro_dashboard;

COMMIT;
