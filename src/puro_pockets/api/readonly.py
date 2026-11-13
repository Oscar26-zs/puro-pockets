"""Comprobación del rol de la base al arrancar el dashboard (Hito 10).

El dashboard solo lee. Antes de servir, se comprueba con `pg_catalog` (que ve también las tablas sin
permiso, a diferencia de `information_schema`) que el rol de `DASHBOARD_DATABASE_URL`:

- no es superusuario ni puede crear objetos en `public`;
- no puede escribir en ninguna tabla de `public` (INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES,
  TRIGGER) ni usar sus secuencias;
- no puede leer ninguna tabla `oauth_*` (tokens y clientes del MCP).

Si algo falla, la API no arranca. Los mensajes nombran el permiso y la tabla, nunca datos.
"""

from __future__ import annotations

from sqlalchemy import Engine, text

WRITE_PRIVILEGES = ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")


class UnsafeDatabaseRole(RuntimeError):
    """El rol del dashboard tiene más permisos que solo lectura."""


_TABLES = text(
    """
    SELECT c.relname AS name, c.oid AS oid
    FROM pg_catalog.pg_class c
    JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
    ORDER BY c.relname
    """
)
_SEQUENCES = text(
    """
    SELECT c.relname AS name, c.oid AS oid
    FROM pg_catalog.pg_class c
    JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind = 'S'
    ORDER BY c.relname
    """
)


def role_problems(engine: Engine) -> list[str]:
    """Lista de problemas del rol (vacía si es de solo lectura y sin acceso a oauth_*)."""
    problems: list[str] = []
    with engine.connect() as conn:
        role = conn.execute(
            text(
                "SELECT rolsuper, rolcreaterole, rolcreatedb, rolbypassrls FROM pg_roles "
                "WHERE rolname = current_user"
            )
        ).one()
        if role.rolsuper:
            problems.append("el rol es superusuario")
        if role.rolcreaterole or role.rolcreatedb:
            problems.append("el rol puede crear roles o bases")
        if role.rolbypassrls:
            problems.append("el rol salta la seguridad por filas")
        if conn.execute(
            text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
        ).scalar():
            problems.append("el rol puede crear objetos en el esquema public")
        tables = conn.execute(_TABLES).all()
        if not tables:
            problems.append("no hay tablas en public (¿base equivocada?)")
        for table in tables:
            for privilege in WRITE_PRIVILEGES:
                allowed = conn.execute(
                    text("SELECT has_table_privilege(current_user, :oid, :priv)"),
                    {"oid": table.oid, "priv": privilege},
                ).scalar()
                if allowed:
                    problems.append(f"{privilege} en la tabla {table.name}")
            if table.name.startswith("oauth_"):
                readable = conn.execute(
                    text("SELECT has_table_privilege(current_user, :oid, 'SELECT')"),
                    {"oid": table.oid},
                ).scalar()
                if readable:
                    problems.append(f"SELECT en la tabla {table.name}")
        for sequence in conn.execute(_SEQUENCES).all():
            usable = conn.execute(
                text("SELECT has_sequence_privilege(current_user, :oid, 'USAGE,UPDATE')"),
                {"oid": sequence.oid},
            ).scalar()
            if usable:
                problems.append(f"USAGE o UPDATE en la secuencia {sequence.name}")
    return problems


def ensure_read_only(engine: Engine) -> None:
    """Lanza `UnsafeDatabaseRole` si el rol no es de solo lectura (ver el módulo)."""
    problems = role_problems(engine)
    if problems:
        raise UnsafeDatabaseRole(
            "El rol de DASHBOARD_DATABASE_URL no es de solo lectura: "
            + "; ".join(problems)
            + ". Usa el rol de scripts/create_dashboard_role.sql (ver README)."
        )
