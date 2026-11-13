// Textos visibles que docs/dashboard.md usa pero que no están en copy.ts (§11: escritos en el
// componente) y los nuevos de este hito. copy.ts se conserva literal.
import { formatCRC, formatMonth, formatPercent, formatUSD } from "./format"
import type { Alert, FixedItem, Movement } from "./types"

export const labels = {
  allClear: "Todo está al día.",
  overview: "Resumen de",
  pocketsDetail: "Distribución y avance de tus objetivos",
  movementsDetail: "Los 10 registros más recientes",
  seeResults: "Ver resultados",
  mainNav: "Navegación principal",
  previousMonth: "Mes anterior",
  nextMonth: "Mes siguiente",
  previousYear: "Año anterior",
  nextYear: "Año siguiente",
  chooseMonth: "Elegir mes",
  moreOptions: "Más opciones",
  dismiss: "Descartar aviso",
  total: "en total",
  income: "Ingresos",
  closeFilters: "Cerrar filtros",
  previousPage: "Más recientes",
  nextPage: "Anteriores",
  page: "Página",
  noPockets: "No hay bolsas para mostrar.",
  noCategories: "Sin gastos en este mes.",
  noFixed: "Sin gastos fijos este mes.",
  wrongPassword: "Contraseña incorrecta.",
  tooMany: "Demasiados intentos. Espera unos minutos.",
  loginFailed: "No se pudo iniciar sesión.",
  reached: "Meta lograda",
  types: { gasto: "Gasto", ingreso: "Ingreso", transferencia: "Transferencia" },
  reasons: {
    cubrir_sobregasto: "Cubrir sobregasto",
    reasignacion: "Reasignación",
    ajuste: "Ajuste",
    cierre_de_mes: "Cierre de mes",
  } as Record<string, string>,
  incomeKinds: {
    base: "Salario",
    extra: "Ingreso extra",
    saldo_inicial: "Saldo inicial",
  } as Record<string, string>,
} as const

const plural = (count: number, one: string, many: string) => (count === 1 ? one : many)

/** Texto de un aviso, con las plantillas de docs/dashboard.md §11. */
export function alertText(alert: Alert): string {
  switch (alert.kind) {
    case "close_pending":
      return `Falta cerrar ${formatMonth(alert.month ?? "").split(" de ")[0]}`
    case "overspent":
      return alert.amount && alert.amount > 0
        ? `${alert.pocket} superó el presupuesto en ${formatCRC(alert.amount)}`
        : `${alert.pocket}: sobregasto`
    case "high_usage":
      return `${alert.pocket}: uso alto (${formatPercent(alert.percent ?? 0)})`
    case "unassigned": {
      const count = alert.count ?? 0
      const parts: string[] = []
      if (alert.crc_total) parts.push(formatCRC(alert.crc_total))
      if (alert.usd_count) parts.push(formatUSD(Number(alert.usd_total ?? "0")))
      const head = `${count} ${plural(count, "extra", "extras")} sin asignar`
      return parts.length ? `${head} · ${parts.join(" + ")}` : head
    }
  }
}

export const alertTone = (alert: Alert) =>
  alert.kind === "overspent" ? "danger" : alert.kind === "high_usage" ? "warning" : "info"

/** Monto de un movimiento con signo (+ si entra, − si sale), dashboard.md §9. */
export function movementAmount(movement: Movement): string {
  const value =
    movement.currency === "USD" ? formatUSD(Number(movement.original_amount)) : formatCRC(movement.amount_crc)
  return `${movement.type === "gasto" ? "−" : "+"}${value}`
}

export function movementDescription(movement: Movement): string {
  if (movement.type === "transferencia") return `${movement.from_pocket} → ${movement.to_pocket}`
  if (movement.type === "ingreso") {
    if (movement.kind === "extra" && movement.description) return movement.description
    return labels.incomeKinds[movement.kind ?? ""] ?? labels.types.ingreso
  }
  return movement.description || movement.category || labels.types.gasto
}

export function movementPocket(movement: Movement): string {
  if (movement.type === "transferencia") return `${movement.from_pocket} · ${movement.to_pocket}`
  if (movement.type === "ingreso") return movement.pending ? "Sin asignar" : labels.income
  return movement.pocket ?? ""
}

export function fixedDetail(item: FixedItem): string {
  if (item.status === "paid") return item.expense_reference ?? ""
  const day = Number((item.due_date ?? "").slice(8, 10))
  return item.status === "overdue" ? `Venció el día ${day}` : `Vence el día ${day}`
}

export function fixedAmount(item: FixedItem): string {
  return item.currency === "USD" ? formatUSD(Number(item.amount)) : formatCRC(item.amount_crc ?? 0)
}

/** Etiqueta abreviada del mes ("nov 2026") para pantallas de menos de 400 px. */
export const shortMonth = (month: string) =>
  new Intl.DateTimeFormat("es-CR", { month: "short", year: "numeric" })
    .format(new Date(`${month}-15T12:00:00`))
    .replace(".", "")
    .replace(" de ", " ")
