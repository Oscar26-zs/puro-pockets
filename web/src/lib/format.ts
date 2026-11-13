// Funciones literales de lib/format.ts según docs/dashboard.md §9.
export const formatCRC = (value: number) => `₡${Math.abs(value).toLocaleString("en-US", { maximumFractionDigits: 0 }).replaceAll(",", ".")}`
export const formatUSD = (value: number) => `US$ ${Math.abs(value).toLocaleString("es-CR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
export const formatPercent = (value: number) => `${new Intl.NumberFormat("es-CR", { maximumFractionDigits: 0 }).format(value)} %`
export const formatDate = (value: string) => new Intl.DateTimeFormat("es-CR", { day: "numeric", month: "short" }).format(new Date(`${value}T12:00:00`))
export const formatMonth = (value: string) => new Intl.DateTimeFormat("es-CR", { month: "long", year: "numeric" }).format(new Date(`${value}-15T12:00:00`))
