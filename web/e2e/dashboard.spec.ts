import AxeBuilder from "@axe-core/playwright"
import { expect, test, type Page } from "@playwright/test"

import * as fx from "../src/test/fixtures"

const WIDTHS = [320, 360, 768, 1024, 1280, 1920]
const THEMES = ["light", "dark"] as const
const SCREENS = ["Resumen", "Bolsas", "Movimientos"] as const

/** API simulada con los fixtures; `authenticated=false` deja la pantalla de contraseña. */
async function mockApi(page: Page, authenticated = true) {
  const routes: Record<string, unknown> = {
    "/api/session": { current_month: "2026-11" },
    "/api/summary": fx.summary,
    "/api/history": fx.history,
    "/api/fixed": fx.fixed,
    "/api/categories": fx.categories,
    "/api/pockets": fx.pockets,
    "/api/movements": fx.movements,
  }
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname
    if (!authenticated) return route.fulfill({ status: 401, json: { detail: "Inicia sesión" } })
    return route.fulfill({ status: 200, json: routes[path] ?? {} })
  })
}

async function open(page: Page, theme: (typeof THEMES)[number], width: number) {
  await page.addInitScript((value) => window.localStorage.setItem("pp-theme", value), theme)
  await page.setViewportSize({ width, height: 900 })
  await mockApi(page)
  await page.goto("/")
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Resumen de")
}

async function show(page: Page, screen: (typeof SCREENS)[number]) {
  const nav = page.getByRole("navigation", { name: "Navegación principal" })
  await nav.getByRole("button", { name: screen }).click()
  const heading = { Resumen: "Resumen de", Bolsas: "Tus bolsas", Movimientos: "Movimientos recientes" }[screen]
  await expect(page.getByRole("heading", { level: 1 })).toContainText(heading)
}

async function seriousViolations(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze()
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)
}

for (const theme of THEMES) {
  for (const width of WIDTHS) {
    test(`${theme} ${width}px: sin scroll horizontal, 44 px en la navegación y sin violaciones graves`, async ({ page }) => {
      await open(page, theme, width)
      for (const screen of SCREENS) {
        await show(page, screen)
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
        expect(overflow, `${screen} desborda ${overflow}px`).toBeLessThanOrEqual(0)
        const buttons = page.getByRole("navigation", { name: "Navegación principal" }).getByRole("button")
        for (const button of await buttons.all()) {
          const box = await button.boundingBox()
          expect(box!.height).toBeGreaterThanOrEqual(44)
          expect(box!.width).toBeGreaterThanOrEqual(44)
        }
        expect(await seriousViolations(page), `${screen} en ${theme}`).toEqual([])
      }
      await expect(page.locator("html")).toHaveClass(new RegExp(theme))
    })
  }
}

test("pantalla de contraseña accesible en claro y oscuro", async ({ page }) => {
  await mockApi(page, false)
  for (const theme of THEMES) {
    await page.addInitScript((value) => window.localStorage.setItem("pp-theme", value), theme)
    await page.goto("/")
    await expect(page.getByRole("heading", { name: "Qué dicha verte" })).toBeVisible()
    expect(await seriousViolations(page)).toEqual([])
  }
})

test("producción: sin panel de desarrollo, sin otros orígenes y sin datos en el almacenamiento", async ({ page }) => {
  const foreign: string[] = []
  page.on("request", (request) => {
    if (!request.url().startsWith("http://127.0.0.1:4173")) foreign.push(request.url())
  })
  await open(page, "light", 1280)
  for (const screen of SCREENS) await show(page, screen)
  await expect(page.getByText("Panel de desarrollo")).toHaveCount(0)
  expect(foreign).toEqual([])
  const stored = await page.evaluate(() => ({
    local: Object.keys(window.localStorage),
    session: window.sessionStorage.length,
    search: window.location.search,
  }))
  expect(stored.local).toEqual(["pp-theme"])
  expect(stored.session).toBe(0)
  expect(stored.search === "" || /^\?month=\d{4}-\d{2}$/.test(stored.search)).toBe(true)
})

test("filtros móviles como diálogo con foco y Escape", async ({ page }) => {
  await open(page, "light", 360)
  await show(page, "Movimientos")
  const opener = page.getByRole("button", { name: "Filtros", exact: true })
  await opener.click()
  await expect(opener).toHaveAttribute("aria-expanded", "true")
  const dialog = page.getByRole("dialog", { name: "Filtros" })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByLabel("Tipo")).toBeFocused()
  await page.keyboard.press("Escape")
  await expect(dialog).toHaveCount(0)
  await expect(opener).toBeFocused()
})

test("tema «Sistema» con el sistema en oscuro (excepción del primario, §3) sin violaciones graves", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" })
  await page.addInitScript(() => window.localStorage.setItem("pp-theme", "system"))
  await page.setViewportSize({ width: 1280, height: 900 })
  await mockApi(page)
  await page.goto("/")
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Resumen de")
  await expect(page.locator("html")).toHaveClass(/dark/)
  await expect(page.locator("html")).not.toHaveClass(/light/)
  for (const screen of SCREENS) {
    await show(page, screen)
    expect(await seriousViolations(page), screen).toEqual([])
  }
})

test("capturas de referencia", async ({ page }, info) => {
  test.skip(!process.env.PP_SCREENSHOTS, "solo con PP_SCREENSHOTS=directorio")
  for (const [theme, width] of [["light", 360], ["dark", 1280], ["light", 1280]] as const) {
    await page.addInitScript((value) => window.localStorage.setItem("pp-theme", value), theme)
    await page.setViewportSize({ width, height: 900 })
    await mockApi(page)
    await page.goto("/")
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Resumen de")
    for (const screen of SCREENS) {
      await show(page, screen)
      await page.screenshot({ path: `${process.env.PP_SCREENSHOTS}/${theme}-${width}-${screen}.png`, fullPage: true })
    }
  }
  info.annotations.push({ type: "capturas", description: String(process.env.PP_SCREENSHOTS) })
})
