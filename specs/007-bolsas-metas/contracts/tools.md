# Contrato de tools: Bolsas flexibles y metas (Hito 7)

Todas exigen el token OAuth (sin él, `/mcp` responde 401). Errores como `isError` en español, sin
montos ni nombres de metas. Porcentajes y montos enteros; un decimal se rechaza sin mostrar el valor.

## `preview_rebalance`

| Parámetro | Notas |
|---|---|
| `strategy` | `proporcional` (por defecto), `desde_una_bolsa`, `manual`. |
| `new_pocket` / `new_percentage` | Para crear (uno de `new_pocket` o `archive_pocket`). |
| `archive_pocket` | Para archivar. |
| `from_pocket` | Con `desde_una_bolsa`: cede (crear) o recibe (archivar). |
| `percentages` | Con `manual`: lista completa `{pocket, percentage}` que suma 100. |
| `month` | Crear: por defecto el siguiente, nunca pasado. Archivar: solo el actual. |

Respuesta: `action`, `strategy`, `months[]` (`month`, `source_month`, `previous[]`, `new[]`), `note`.

## `create_bolsa`

`name`, `behavior` (`consumo` | `acumulable`), `percentage` (no con manual), `strategy`,
`from_pocket`, `percentages`, `group`, `month`, `confirm`, `operation_id` y `preview_token`
(obligatorios con `confirm=true`). Respuesta: `saved`, `pocket` (`name`, `behavior`, `group`),
`rebalance`, `preview_token` (solo vista previa). Errores: nombre repetido, mes pasado, suma ≠ 100,
bolsa inexistente, no alcanza (desde_una_bolsa), sin porcentajes previos (usar manual), sin ficha.

## `archive_bolsa`

`name`, `strategy`, `to_pocket`, `percentages`, `month` (solo el actual), `confirm`,
`operation_id`, `preview_token`. Respuesta: `saved`, `pocket`, `rebalance` (mes actual y futuros
con porcentajes propios), `archived_goals[]`, `preview_token`. Errores: saldo o disponible distinto
de cero (sin montos), mes futuro o pasado, única bolsa activa, proporcional imposible, sin ficha.

## `create_goal`

`pocket`, `name`, `target_amount`, `operation_id`, `target_date` (opcional). Respuesta: `saved`,
`reference` (M-n), `pocket`, `name`, `target_amount`, `target_date`, `status`, `achieved_on`,
`balance`, `percent`, `missing`, `note`. Errores: bolsa de consumo, inexistente o archivada; otra
meta activa en la bolsa; monto no entero o ≤ 0; fecha pasada.

## `get_goal_progress`

`pocket` opcional. Respuesta: `month`, `items[]` (`reference`, `pocket`, `name`, `status`,
`target_amount`, `target_date`, `achieved_on`, `balance`, `percent`, `missing`, `excess`,
`months_considered`, `avg_monthly_net_change`, `projectable`).

## `update_goal`

`goal` (M-n), `operation_id`, `target_amount`, `target_date`, `clear_target_date`, `action`
(`pausar` | `reactivar`). Respuesta como `create_goal`. Errores: meta inexistente, lograda o
archivada; pausar una no activa; reactivar una no pausada o con otra activa; nada que cambiar.

## Cambios en tools anteriores

- `get_allocation_context`: `goals[]` (`pocket`, `target_amount`, `balance`, `percent`).
- `get_bolsa_status`: `goal` (`reference`, `target_amount`, `percent`, `missing`) si hay meta activa.
- `void_transaction`: rechaza movimientos que toquen una bolsa archivada.
- Todas las búsquedas de bolsa por nombre rechazan las archivadas.
