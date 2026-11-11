# Data Model: Bolsas flexibles y metas (migración `0006_pockets_goals`)

Esquema completo en `docs/plan-tecnico.md`, sección 17. Aquí solo lo que cambia.

## `pockets`

| Columna | Cambio |
|---|---|
| `archived_at` | Nueva, nula. `CHECK (active = (archived_at IS NULL))`. Las filas existentes quedan activas con NULL. |

Disparadores: sin DELETE (RN-16); no se reactiva; `behavior` no cambia (RN-10).

## `savings_goals` (nueva)

| Columna | Tipo | Reglas |
|---|---|---|
| `id` | BIGINT identidad | Referencia `M-<id>`. |
| `pocket_id` | FK `pockets` | Acumulable y activa (código); no cambia. |
| `name` | TEXT | 1 a 60; no cambia. |
| `target_amount` | BIGINT | > 0, colones (RN-19). |
| `target_date` | DATE nula | Opcional (RN-20); no pasada (código). |
| `status` | TEXT | `activa`, `lograda`, `pausada` (RN-24). |
| `achieved_on` | DATE nula | `(status = 'lograda') = (achieved_on IS NOT NULL)`. |
| `created_on` | DATE | No cambia. |
| `archived_at` | TIMESTAMPTZ nula | Archivada con su bolsa. |

Índice único parcial `ux_savings_goals_active_pocket (pocket_id) WHERE status = 'activa' AND
archived_at IS NULL` (RN-22). Disparadores: sin DELETE; lograda fija (estado, fecha, objetivo);
archivada fija.

## Estados

```
meta:  activa ──(saldo ≥ objetivo)──► lograda (final)
         │  ▲
   pausar│  │reactivar (si no hay otra activa; si el saldo ya alcanza → lograda)
         ▼  │
        pausada
bolsa archivada → todas sus metas con archived_at (sin cambios después)
```
