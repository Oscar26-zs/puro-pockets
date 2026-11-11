# Contrato de las tools del Hito 8

Todas detrás de OAuth (sin credencial: 401). Errores como `is_error` en español, sin montos, notas
ni nombres de metas. Bolsas por nombre (sin distinguir mayúsculas).

## `preview_transfer`

Entrada: `from_pocket`, `to_pocket`, `amount` (entero, colones), `reason`
(`cubrir_sobregasto` | `reasignacion` | `ajuste`), `note` (opcional, ≤ 140), `transfer_date`
(opcional; solo hoy).

Salida (`TransferResult`, `saved=false`): `date`, `month`, `amount`, `reason`, `note`,
`from_pocket` y `to_pocket` (`pocket`, `behavior`, `balance_kind`, `before`, `after`,
`adjusted_budget_before`, `adjusted_budget_after`; los dos últimos solo en consumo),
`goal_effects` (`reference`, `pocket`, `percent_before`, `percent_after`, `missing_before`,
`missing_after`, `completes`), `warning` y `preview_token`. No guarda nada.

## `transfer_between_bolsas`

Entrada: la de `preview_transfer` más `confirm`, `operation_id` (obligatorio con confirm) y
`preview_token` (obligatorio con confirm).

- Sin `confirm=true`: la misma vista previa.
- Con `confirm=true`: guarda y devuelve `saved=true` y `reference` (`T-n`). Misma clave con el mismo
  contenido → la respuesta original; con otro contenido → error.

## Cambios en tools existentes

- `add_expense`: con sobregasto, `available_pockets` usa los cálculos con transferencias y la
  advertencia guía hacia `preview_transfer` (motivo `cubrir_sobregasto`) con aprobación explícita.
- `get_bolsa_status`: `transfers_in`, `transfers_out`, `adjusted_budget` reales y
  `percent_used_original`.
- `get_summary` y `get_allocation_context`: cada bolsa con `transfers_in`, `transfers_out` y
  `adjusted_budget` (y `% usado` en el resumen).
- `list_transactions`: `type` admite `transferencia`; `pocket` filtra gastos y transferencias; los
  ítems de transferencia traen `from_pocket`, `to_pocket`, `reason` y `note`.
- `void_transaction("T-n")`: error explicando la transferencia inversa (RN-43).
- `archive_bolsa` con saldo: error que indica transferir primero (RN-18).
