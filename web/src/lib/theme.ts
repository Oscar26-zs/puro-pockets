// Tema claro, oscuro o del sistema. Es lo ÚNICO que se guarda en el navegador (localStorage).
import type { ThemeMode } from "./types"

export const THEME_KEY = "pp-theme"

export function readTheme(): ThemeMode {
  try {
    const value = window.localStorage.getItem(THEME_KEY)
    return value === "light" || value === "dark" || value === "system" ? value : "system"
  } catch {
    return "system"
  }
}

export function saveTheme(theme: ThemeMode): void {
  try {
    window.localStorage.setItem(THEME_KEY, theme)
  } catch {
    // almacenamiento bloqueado: el tema vale solo para esta visita
  }
}

export function systemPrefersDark(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-color-scheme: dark)").matches
}

/** Aplica las clases `light` y `dark` al elemento raíz (dashboard.md §3). */
export function applyTheme(theme: ThemeMode, root: HTMLElement = document.documentElement): void {
  const dark = theme === "dark" || (theme === "system" && systemPrefersDark())
  root.classList.toggle("light", theme === "light")
  root.classList.toggle("dark", dark)
  root.style.colorScheme = dark ? "dark" : "light"
}

/** Mes AAAA-MM de la URL (?month=). Es el único dato que va en la URL. */
export function monthFromUrl(): string | null {
  const value = new URLSearchParams(window.location.search).get("month")
  return value && /^\d{4}-(0[1-9]|1[0-2])$/.test(value) ? value : null
}

export function writeMonthToUrl(month: string): void {
  const url = new URL(window.location.href)
  url.search = new URLSearchParams({ month }).toString()
  window.history.replaceState(null, "", url)
}

/** Suma (o resta) meses a AAAA-MM, sin fechas locales. */
export function shiftMonth(month: string, delta: number): string {
  const [year, mon] = month.split("-").map(Number) as [number, number]
  const index = year * 12 + (mon - 1) + delta
  return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, "0")}`
}
