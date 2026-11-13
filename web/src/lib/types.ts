// Tipos de la API del dashboard (specs/010-dashboard/plan.md, "Contrato de la API").
// Los valores llegan calculados por el servidor; el frontend solo los da formato.

export type ThemeMode = "light" | "dark" | "system"
export type Screen = "Resumen" | "Bolsas" | "Movimientos"
export type Currency = "CRC" | "USD"

export interface SessionInfo {
  current_month: string
}

export interface PendingClosure {
  month: string
  has_movements: boolean
}

export interface Alert {
  kind: "close_pending" | "overspent" | "high_usage" | "unassigned"
  month?: string | null
  pocket?: string | null
  amount?: number | null
  percent?: number | null
  count?: number | null
  crc_total?: number | null
  usd_count?: number | null
  usd_total?: string | null
}

export interface Unassigned {
  count: number
  total_crc: number
  crc_count: number
  crc_total: number
  usd_count: number
  usd_total: string
}

export interface Summary {
  month: string
  current_month: string
  month_closed: boolean
  income: number
  extra_income: number
  spent: number
  available: number
  saved: number
  saved_breakdown: {
    base: number
    extra: number
    transfers_in: number
    transfers_out: number
    closure_surplus: number
  }
  unassigned: Unassigned
  closure_adjustments: { pocket: string; kind: string; amount: number }[]
  pending_closure: PendingClosure[]
  alerts: Alert[]
}

export interface Goal {
  reference: string
  name: string
  status: "activa" | "lograda" | "pausada"
  target: number
  balance: number
  progress: number
  remaining: number
  excess: number
  monthly_average: number | null
  projectable: boolean
  estimated_month: string | null
}

export interface Pocket {
  name: string
  kind: "consumo" | "acumulable"
  assigned: number
  received: number
  sent: number
  adjusted: number
  spent: number
  available: number | null
  used: number | null
  used_original: number | null
  balance: number | null
  negative: boolean
  alert: "warning" | "danger" | null
  goal: Goal | null
}

export interface PocketsResponse {
  month: string
  month_closed: boolean
  items: Pocket[]
}

export interface Movement {
  ref: string
  type: "gasto" | "ingreso" | "transferencia"
  kind: string | null
  date: string
  month: string
  description: string | null
  pocket: string | null
  from_pocket: string | null
  to_pocket: string | null
  category: string | null
  currency: Currency
  original_amount: string
  amount_crc: number
  voided: boolean
  void_reason: string | null
  pending: boolean
  reason: string | null
  note: string | null
  recurring: string | null
}

export interface MovementsResponse {
  items: Movement[]
  page: number
  page_size: number
  has_more: boolean
}

export interface CategoriesResponse {
  month: string
  total: number
  items: { name: string; value: number; count: number; percent: number }[]
}

export interface HistoryResponse {
  months: { month: string; income: number; spent: number; saved: number }[]
}

export interface FixedItem {
  reference: string
  name: string
  currency: Currency
  amount: string
  amount_crc: number | null
  status: "paid" | "pending" | "overdue"
  due_date: string | null
  expense_reference: string | null
}

export interface FixedResponse {
  month: string
  pending_count: number
  overdue_count: number
  items: FixedItem[]
}

export interface MovementFiltersValue {
  type: "" | Movement["type"]
  pocket: string
  month: string
  includeVoid: boolean
  page: number
}
