// Datos de ejemplo de docs/dashboard.md §15 (data/mock.ts), con la forma de la API. SOLO para
// pruebas: ningún archivo de la aplicación importa este módulo (scripts/check-bundle.mjs lo
// comprueba en la compilación). No son datos reales.
import type {
  CategoriesResponse,
  FixedResponse,
  HistoryResponse,
  MovementsResponse,
  PocketsResponse,
  Summary,
} from "../lib/types"

export const FIXTURE_MARKER = "Suscripción de video"

export const summary: Summary = {
  month: "2026-11",
  current_month: "2026-11",
  month_closed: false,
  income: 540000,
  extra_income: 40000,
  spent: 310000,
  available: 230000,
  saved: 90000,
  saved_breakdown: { base: 90000, extra: 0, transfers_in: 0, transfers_out: 0, closure_surplus: 0 },
  unassigned: { count: 1, total_crc: 13000, crc_count: 0, crc_total: 0, usd_count: 1, usd_total: "25.00" },
  closure_adjustments: [],
  pending_closure: [{ month: "2026-10", has_movements: true }],
  alerts: [
    { kind: "close_pending", month: "2026-10" },
    { kind: "overspent", pocket: "Gustos", amount: 4500 },
    { kind: "high_usage", pocket: "Necesidades", percent: 82 },
    { kind: "unassigned", count: 1, crc_total: 0, usd_count: 1, usd_total: "25.00" },
  ],
}

export const pockets: PocketsResponse = {
  month: "2026-11",
  month_closed: false,
  items: [
    { name: "Necesidades", kind: "consumo", assigned: 250000, received: 0, sent: 7500, adjusted: 242500, spent: 198000, available: 44500, used: 82, used_original: 79, balance: null, negative: false, alert: "warning", goal: null },
    { name: "Gustos", kind: "consumo", assigned: 100000, received: 7500, sent: 0, adjusted: 107500, spent: 112000, available: -4500, used: 104, used_original: 112, balance: null, negative: true, alert: "danger", goal: null },
    {
      name: "Ahorro", kind: "acumulable", assigned: 150000, received: 0, sent: 0, adjusted: 150000, spent: 0, available: null, used: null, used_original: null, balance: 480000, negative: false, alert: null,
      goal: { reference: "M-1", name: "Viaje", status: "activa", target: 500000, balance: 480000, progress: 96, remaining: 20000, excess: 0, monthly_average: 60000, projectable: true, estimated_month: "2026-12" },
    },
    {
      name: "Emergencias", kind: "acumulable", assigned: 0, received: 0, sent: 0, adjusted: 0, spent: 0, available: null, used: null, used_original: null, balance: 150000, negative: false, alert: null,
      goal: { reference: "M-2", name: "Fondo de emergencia", status: "activa", target: 300000, balance: 150000, progress: 50, remaining: 150000, excess: 0, monthly_average: 25000, projectable: false, estimated_month: null },
    },
    { name: "Hogar", kind: "acumulable", assigned: 0, received: 0, sent: 0, adjusted: 0, spent: 0, available: null, used: null, used_original: null, balance: 0, negative: false, alert: null, goal: null },
  ],
}

export const categories: CategoriesResponse = {
  month: "2026-11",
  total: 310000,
  items: [
    { name: "Alimentación", value: 95000, count: 6, percent: 30 },
    { name: "Vivienda", value: 80000, count: 1, percent: 25 },
    { name: "Salidas", value: 52000, count: 3, percent: 16 },
    { name: "Ropa", value: 35000, count: 1, percent: 11 },
    { name: "Suscripciones", value: 25000, count: 2, percent: 8 },
    { name: "Transporte", value: 23000, count: 4, percent: 7 },
  ],
}

export const history: HistoryResponse = {
  months: [
    { month: "2026-06", income: 500000, spent: 430000, saved: 70000 },
    { month: "2026-07", income: 500000, spent: 455000, saved: 45000 },
    { month: "2026-08", income: 520000, spent: 410000, saved: 110000 },
    { month: "2026-09", income: 500000, spent: 470000, saved: 30000 },
    { month: "2026-10", income: 520000, spent: 440000, saved: 80000 },
    { month: "2026-11", income: 540000, spent: 310000, saved: 90000 },
  ],
}

export const fixed: FixedResponse = {
  month: "2026-11",
  pending_count: 3,
  overdue_count: 1,
  items: [
    { reference: "F-1", name: "Alquiler", currency: "CRC", amount: "80000", amount_crc: 80000, status: "paid", due_date: null, expense_reference: "G-41" },
    { reference: "F-2", name: "Internet", currency: "CRC", amount: "18000", amount_crc: 18000, status: "pending", due_date: "2026-11-15", expense_reference: null },
    { reference: "F-3", name: FIXTURE_MARKER, currency: "USD", amount: "12.99", amount_crc: null, status: "pending", due_date: "2026-11-20", expense_reference: null },
    { reference: "F-4", name: "Seguro", currency: "CRC", amount: "22000", amount_crc: 22000, status: "overdue", due_date: "2026-11-05", expense_reference: null },
  ],
}

const base = { kind: null, month: "2026-11", category: null, from_pocket: null, to_pocket: null, voided: false, void_reason: null, pending: false, reason: null, note: null, recurring: null } as const

export const movements: MovementsResponse = {
  page: 1,
  page_size: 10,
  has_more: false,
  items: [
    { ...base, ref: "G-52", type: "gasto", date: "2026-11-11", description: "Supermercado", pocket: "Necesidades", currency: "CRC", original_amount: "18500", amount_crc: 18500 },
    { ...base, ref: "T-3", type: "transferencia", date: "2026-11-10", description: null, pocket: null, from_pocket: "Necesidades", to_pocket: "Gustos", currency: "CRC", original_amount: "7500", amount_crc: 7500, reason: "cubrir_sobregasto" },
    { ...base, ref: "G-51", type: "gasto", date: "2026-11-10", description: "Salida con amigos", pocket: "Gustos", currency: "CRC", original_amount: "12000", amount_crc: 12000 },
    { ...base, ref: "I-9", type: "ingreso", kind: "extra", date: "2026-11-09", description: "Extra en dólares", pocket: null, currency: "USD", original_amount: "25.00", amount_crc: 13000, pending: true },
    { ...base, ref: "G-49", type: "gasto", date: "2026-11-08", description: "Ropa", pocket: "Gustos", currency: "CRC", original_amount: "35000", amount_crc: 35000, voided: true, void_reason: "duplicado" },
    { ...base, ref: "I-8", type: "ingreso", kind: "base", date: "2026-11-01", description: null, pocket: null, currency: "CRC", original_amount: "500000", amount_crc: 500000 },
  ],
}
