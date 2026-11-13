import { act, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"

import { MovementList } from "@/components/movements"
import { AlertPanel, FixedExpenses, MetricGrid, Overview, Unassigned } from "@/components/overview"
import { PocketCard, ProgressBar } from "@/components/pockets"
import { PuroDashboard } from "@/components/puro-dashboard"
import { StatusBadge, ThemeMenu } from "@/components/shell"
import { LoginScreen, StateNotice } from "@/components/states"
import { copy } from "@/lib/copy"
import { formatCRC, formatDate, formatMonth, formatPercent, formatUSD } from "@/lib/format"
import { alertText } from "@/lib/labels"
import { THEME_KEY, applyTheme, readTheme, saveTheme } from "@/lib/theme"
import * as fx from "@/test/fixtures"

const pockets = fx.pockets.items

describe("formatos (dashboard.md §9)", () => {
  it("da las salidas exactas de la tabla", () => {
    expect(formatCRC(540000)).toBe("₡540.000")
    expect(formatCRC(-4500)).toBe("₡4.500")
    expect(formatUSD(12.99)).toBe("US$ 12,99")
    expect(formatPercent(82)).toBe("82 %")
    expect(formatDate("2026-11-09")).toMatch(/^9 nov\.?$/)
    expect(formatMonth("2026-11")).toBe("noviembre de 2026")
  })

  it("arma los avisos con las plantillas de §11", () => {
    expect(alertText({ kind: "close_pending", month: "2026-10" })).toBe("Falta cerrar octubre")
    expect(alertText({ kind: "overspent", pocket: "Gustos", amount: 4500 })).toBe(
      "Gustos superó el presupuesto en ₡4.500",
    )
    expect(alertText({ kind: "unassigned", count: 1, crc_total: 0, usd_count: 1, usd_total: "25.00" })).toBe(
      "1 extra sin asignar · US$ 25,00",
    )
    expect(alertText({ kind: "high_usage", pocket: "Necesidades", percent: 82 })).toBe("Necesidades: uso alto (82 %)")
  })
})

describe("avisos", () => {
  it("muestra, descarta y queda al día", async () => {
    const user = userEvent.setup()
    render(<AlertPanel monthClosed={false} alerts={fx.summary.alerts} />)
    const list = screen.getByRole("list")
    expect(within(list).getAllByRole("listitem")).toHaveLength(4)
    for (const button of screen.getAllByRole("button", { name: /Descartar aviso/ })) await user.click(button)
    expect(screen.getByText("Todo está al día.")).toBeInTheDocument()
  })

  it("en un mes cerrado los reemplaza el aviso de solo lectura", () => {
    render(<AlertPanel monthClosed alerts={fx.summary.alerts} />)
    expect(screen.getByText(copy.readOnly)).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Descartar/ })).not.toBeInTheDocument()
  })
})

describe("barras de progreso", () => {
  it("limita el ancho y aria-valuenow a 100 y dice el valor real", () => {
    render(<ProgressBar label="Gustos" value={104} tone="danger" />)
    const bar = screen.getByRole("progressbar", { name: "Gustos" })
    expect(bar).toHaveAttribute("aria-valuenow", "100")
    expect(bar).toHaveAttribute("aria-valuemax", "100")
    expect(bar).toHaveAttribute("aria-valuetext", "104 %")
    expect((bar.firstChild as HTMLElement).style.width).toBe("100%")
  })

  it("bolsa de consumo con sobregasto y uso alto", () => {
    const { rerender } = render(<PocketCard pocket={pockets[1]!} />)
    expect(screen.getByText(copy.danger)).toBeInTheDocument()
    expect(screen.getByText("104 %")).toBeInTheDocument()
    expect(screen.getByText("−₡4.500")).toBeInTheDocument()
    expect(screen.getByText(copy.original)).toBeInTheDocument()
    expect(screen.getByText(copy.adjusted)).toBeInTheDocument()
    rerender(<PocketCard pocket={pockets[0]!} />)
    expect(screen.getByText(copy.warning)).toBeInTheDocument()
  })
})

describe("tarjetas de meta", () => {
  it("muestra avance, faltante y la fecha estimada que da la API", () => {
    render(<PocketCard pocket={pockets[2]!} />)
    expect(screen.getByText("Viaje")).toBeInTheDocument()
    expect(screen.getByText("₡20.000")).toBeInTheDocument()
    expect(screen.getByText("diciembre de 2026")).toBeInTheDocument()
    expect(screen.getByRole("progressbar", { name: /Avance de la meta/ })).toHaveAttribute("aria-valuenow", "96")
  })

  it("sin proyección dice «Sin estimación»", () => {
    render(<PocketCard pocket={pockets[3]!} />)
    expect(screen.getByText(copy.noEstimate)).toBeInTheDocument()
  })
})

describe("resumen", () => {
  it("métricas en orden y sin recalcular", () => {
    render(<MetricGrid summary={fx.summary} />)
    const values = ["₡540.000", "₡310.000", "₡230.000", "₡90.000"]
    for (const value of values) expect(screen.getByText(value)).toBeInTheDocument()
    const labels = screen.getAllByText(/Ingresos del mes|Gastado|Disponible|Ahorrado/).map((n) => n.textContent)
    expect(labels).toEqual(["Ingresos del mes", "Gastado", "Disponible", "Ahorrado"])
  })

  it("sin asignar por moneda y gastos fijos con estado", () => {
    render(
      <>
        <Unassigned summary={fx.summary} />
        <FixedExpenses fixed={fx.fixed} />
      </>,
    )
    expect(screen.getByText("US$ 25,00")).toBeInTheDocument()
    expect(screen.getByText(copy.currencyNote)).toBeInTheDocument()
    expect(screen.getByText("Vence el día 15")).toBeInTheDocument()
    expect(screen.getByText("Venció el día 5")).toBeInTheDocument()
    expect(screen.getByText("G-41")).toBeInTheDocument()
    expect(screen.getByText(copy.late)).toBeInTheDocument()
  })

  it("mes cerrado: insignia y aviso de solo lectura", () => {
    render(
      <Overview
        month="2026-10"
        closed
        summary={{ ...fx.summary, month: "2026-10", month_closed: true }}
        history={fx.history}
        fixed={fx.fixed}
        categories={fx.categories}
      />,
    )
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Resumen de Octubre de 2026")
    expect(screen.getByText(copy.monthClosed)).toBeInTheDocument()
    expect(screen.getByText(copy.readOnly)).toBeInTheDocument()
    expect(screen.getByText("₡310.000 en total")).toBeInTheDocument()
  })
})

describe("movimientos", () => {
  it("marca anulados y pendientes, y pone el signo", () => {
    render(<MovementList items={fx.movements.items} />)
    const table = screen.getByRole("table")
    expect(within(table).getByText(copy.void)).toBeInTheDocument()
    expect(within(table).getByText(copy.pending)).toBeInTheDocument()
    expect(within(table).getByText("−₡18.500")).toBeInTheDocument()
    expect(within(table).getByText("+₡7.500")).toBeInTheDocument()
    expect(within(table).getByText("+US$ 25,00")).toBeInTheDocument()
    expect(within(table).getByText("Necesidades → Gustos")).toBeInTheDocument()
    expect(within(table).getByText("Necesidades · Gustos")).toBeInTheDocument()
    expect(within(table).getByText("Salario")).toBeInTheDocument()
  })

  it("vacío", () => {
    render(<MovementList items={[]} />)
    expect(screen.getByText(copy.empty)).toBeInTheDocument()
  })
})

describe("estados", () => {
  it("carga, vacío y error con reintentar", async () => {
    const retry = vi.fn()
    const { rerender } = render(<StateNotice state="loading" onRetry={retry} />)
    expect(screen.getByRole("status")).toHaveTextContent(copy.loading)
    rerender(<StateNotice state="empty" onRetry={retry} />)
    expect(screen.getByText(copy.empty)).toBeInTheDocument()
    rerender(<StateNotice state="error" onRetry={retry} />)
    expect(screen.getByRole("alert")).toHaveTextContent(copy.error)
    await userEvent.click(screen.getByRole("button", { name: copy.retry }))
    expect(retry).toHaveBeenCalledOnce()
  })

  it("insignia de mes abierto", () => {
    render(<StatusBadge closed={false} />)
    expect(screen.getByText(copy.monthOpen)).toBeInTheDocument()
  })

  it("inicio de sesión muestra el error y limpia la contraseña", async () => {
    const onLogin = vi.fn().mockResolvedValue("Contraseña incorrecta.")
    render(<LoginScreen onLogin={onLogin} />)
    const input = screen.getByLabelText(copy.password)
    await userEvent.type(input, "mala")
    await userEvent.click(screen.getByRole("button", { name: copy.enter }))
    expect(onLogin).toHaveBeenCalledWith("mala")
    expect(await screen.findByRole("alert")).toHaveTextContent("Contraseña incorrecta.")
    expect(input).toHaveValue("")
    expect(screen.queryByText(copy.noLogin)).not.toBeInTheDocument()
  })
})

describe("selector de tema", () => {
  beforeEach(() => {
    window.localStorage.clear()
    document.documentElement.className = ""
  })

  it("ofrece Claro, Oscuro y Sistema con aria-pressed", async () => {
    const setTheme = vi.fn()
    render(<ThemeMenu theme="system" setTheme={setTheme} />)
    const trigger = screen.getByRole("button", { name: "Tema: Sistema" })
    await userEvent.click(trigger)
    expect(trigger).toHaveAttribute("aria-expanded", "true")
    expect(screen.getByRole("button", { name: "Sistema" })).toHaveAttribute("aria-pressed", "true")
    await userEvent.click(screen.getByRole("button", { name: "Oscuro" }))
    expect(setTheme).toHaveBeenCalledWith("dark")
  })

  it("Escape cierra y devuelve el foco", async () => {
    render(<ThemeMenu theme="light" setTheme={() => {}} />)
    const trigger = screen.getByRole("button", { name: "Tema: Claro" })
    await userEvent.click(trigger)
    await userEvent.keyboard("{Escape}")
    expect(trigger).toHaveAttribute("aria-expanded", "false")
    expect(trigger).toHaveFocus()
  })

  it("aplica las clases y guarda solo la preferencia", () => {
    applyTheme("dark")
    expect(document.documentElement).toHaveClass("dark")
    applyTheme("light")
    expect(document.documentElement).toHaveClass("light")
    expect(document.documentElement).not.toHaveClass("dark")
    saveTheme("dark")
    expect(readTheme()).toBe("dark")
    expect(Object.keys(window.localStorage)).toEqual([THEME_KEY])
  })
})

describe("aplicación con la API simulada", () => {
  const routes: Record<string, unknown> = {
    "/api/summary": fx.summary,
    "/api/history": fx.history,
    "/api/fixed": fx.fixed,
    "/api/categories": fx.categories,
    "/api/pockets": fx.pockets,
    "/api/movements": fx.movements,
  }
  let authenticated = false

  beforeEach(() => {
    authenticated = false
    window.localStorage.clear()
    window.sessionStorage.clear()
    window.history.replaceState(null, "", "/")
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = new URL(String(input), "http://localhost")
        const json = (status: number, body: unknown) =>
          new Response(status === 204 ? null : JSON.stringify(body), { status })
        if (url.pathname === "/api/session/login") {
          const { password } = JSON.parse(String(init?.body)) as { password: string }
          if (password !== "correcta") return json(401, { detail: "Contraseña incorrecta." })
          authenticated = true
          return json(204, null)
        }
        if (!authenticated) return json(401, { detail: "Inicia sesión" })
        if (url.pathname === "/api/session") return json(200, { current_month: "2026-11" })
        return json(200, routes[url.pathname])
      }),
    )
  })

  afterEach(() => vi.unstubAllGlobals())

  it("pide la contraseña, entra y muestra el resumen sin guardar datos en el navegador", async () => {
    const user = userEvent.setup()
    render(<PuroDashboard />)
    const input = await screen.findByLabelText(copy.password)
    await user.type(input, "mala")
    await user.click(screen.getByRole("button", { name: copy.enter }))
    expect(await screen.findByRole("alert")).toHaveTextContent("Contraseña incorrecta.")
    await user.type(screen.getByLabelText(copy.password), "correcta")
    await user.click(screen.getByRole("button", { name: copy.enter }))
    expect(await screen.findByText("Resumen de Noviembre de 2026")).toBeInTheDocument()
    expect(screen.getByText("₡540.000")).toBeInTheDocument()
    expect(Object.keys(window.localStorage).filter((k) => k !== THEME_KEY)).toEqual([])
    expect(window.sessionStorage.length).toBe(0)
    expect(window.location.search).toBe("")
  })

  it("navega a bolsas y movimientos; el mes es lo único en la URL", async () => {
    authenticated = true
    const user = userEvent.setup()
    render(<PuroDashboard />)
    await screen.findByText("Resumen de Noviembre de 2026")
    const nav = screen.getByRole("navigation", { name: "Navegación principal" })
    await user.click(within(nav).getByRole("button", { name: "Bolsas" }))
    expect(await screen.findByRole("heading", { name: copy.pockets })).toBeInTheDocument()
    expect(within(nav).getByRole("button", { name: "Bolsas" })).toHaveAttribute("aria-current", "page")
    await user.click(within(nav).getByRole("button", { name: "Movimientos" }))
    expect(await screen.findByText("Supermercado", { selector: "td span" })).toBeInTheDocument()
    await act(async () => {
      await user.click(screen.getByRole("button", { name: "Mes anterior" }))
    })
    await waitFor(() => expect(window.location.search).toBe("?month=2026-10"))
    expect(screen.getByRole("button", { name: "Mes siguiente" })).toBeEnabled()
  })
})
