import { useCallback, useEffect, useState } from "react"

import { Movements } from "@/components/movements"
import { Overview } from "@/components/overview"
import { Pockets } from "@/components/pockets"
import { Header, Sidebar, focusRing } from "@/components/shell"
import { DevelopmentPanel, LoadingView, LoginScreen, StateNotice, type ViewState } from "@/components/states"
import { ApiError, api } from "@/lib/api"
import { copy } from "@/lib/copy"
import { labels } from "@/lib/labels"
import { applyTheme, monthFromUrl, readTheme, saveTheme, writeMonthToUrl } from "@/lib/theme"
import type {
  CategoriesResponse,
  FixedResponse,
  HistoryResponse,
  MovementFiltersValue,
  PocketsResponse,
  Screen,
  Summary,
  ThemeMode,
} from "@/lib/types"
import { cn } from "@/lib/utils"

type ScreenData = { key: string } & (
  | { screen: "Resumen"; summary: Summary; history: HistoryResponse; fixed: FixedResponse; categories: CategoriesResponse }
  | { screen: "Bolsas" | "Movimientos"; pockets: PocketsResponse }
)

const DEV = import.meta.env.DEV

/** Estado simulado inicial (?state=), solo en desarrollo (P7). */
function initialViewState(): ViewState {
  if (!DEV) return "normal"
  const value = new URLSearchParams(window.location.search).get("state")
  return value === "loading" || value === "empty" || value === "error" || value === "closed" ? value : "normal"
}

export function PuroDashboard() {
  const [screen, setScreen] = useState<Screen>("Resumen")
  const [theme, setThemeState] = useState<ThemeMode>(readTheme)
  const [currentMonth, setCurrentMonth] = useState<string | null>(null)
  const [month, setMonthState] = useState<string | null>(monthFromUrl)
  const [loggedIn, setLoggedIn] = useState<boolean | null>(null)
  const [state, setState] = useState<ViewState>(initialViewState)
  const [data, setData] = useState<ScreenData | null>(null)
  const [failedKey, setFailedKey] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  // Cada combinación de pantalla, mes e intento es una petición; los datos y el error se asocian a
  // su clave, así una respuesta vieja nunca se muestra en otra pantalla.
  const requestKey = `${screen}|${month}|${attempt}`

  // Tema: clases en el elemento raíz; «Sistema» sigue a matchMedia
  useEffect(() => {
    applyTheme(theme)
    if (theme !== "system" || typeof window.matchMedia !== "function") return
    const media = window.matchMedia("(prefers-color-scheme: dark)")
    const update = () => applyTheme("system")
    media.addEventListener("change", update)
    return () => media.removeEventListener("change", update)
  }, [theme])

  const setTheme = (value: ThemeMode) => {
    saveTheme(value)
    setThemeState(value)
  }

  const setMonth = (value: string) => {
    setMonthState(value)
    writeMonthToUrl(value)
  }

  const handleError = useCallback((error: unknown, key: string) => {
    if (error instanceof ApiError && error.status === 401) {
      setLoggedIn(false)
      setData(null)
    } else {
      setFailedKey(key)
    }
  }, [])

  // Sesión: ¿hay cookie válida? Da el mes actual (para deshabilitar meses futuros)
  useEffect(() => {
    if (loggedIn === false) return
    let alive = true
    api
      .session()
      .then((info) => {
        if (!alive) return
        setCurrentMonth(info.current_month)
        setMonthState((m) => (m && m <= info.current_month ? m : info.current_month))
        setLoggedIn(true)
      })
      .catch((error) => alive && handleError(error, `session|${attempt}`))
    return () => {
      alive = false
    }
  }, [loggedIn, attempt, handleError])

  // Datos de la pantalla activa
  useEffect(() => {
    if (!loggedIn || !month) return
    let alive = true
    const key = requestKey
    const load: Promise<ScreenData> =
      screen === "Resumen"
        ? Promise.all([api.summary(month), api.history(month), api.fixed(month), api.categories(month)]).then(
            ([summary, history, fixed, categories]) => ({ key, screen, summary, history, fixed, categories }),
          )
        : api.pockets(month).then((pockets) => ({ key, screen, pockets }))
    load.then((result) => alive && setData(result)).catch((error) => alive && handleError(error, key))
    return () => {
      alive = false
    }
  }, [loggedIn, month, screen, requestKey, handleError])

  const loadMovements = useCallback(
    (filters: MovementFiltersValue) =>
      api.movements(filters).catch((error) => {
        handleError(error, requestKey)
        return null
      }),
    [handleError, requestKey],
  )

  async function login(password: string): Promise<string | null> {
    try {
      await api.login(password)
      setLoggedIn(null)
      setAttempt((n) => n + 1)
      return null
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) return labels.wrongPassword
      if (error instanceof ApiError && error.status === 429) return labels.tooMany
      return labels.loginFailed
    }
  }

  async function signOut() {
    try {
      await api.logout()
    } catch {
      // la cookie vence sola; igual se vuelve a la pantalla de contraseña
    }
    setData(null)
    setLoggedIn(false)
  }

  if (loggedIn === false) return <LoginScreen onLogin={login} />

  const retry = () => {
    setState("normal")
    setAttempt((n) => n + 1)
  }
  const shownMonth = month ?? currentMonth ?? ""
  const failed = failedKey === requestKey || failedKey === `session|${attempt}`
  const viewState: ViewState = failed ? "error" : state
  const ready = data !== null && data.key === requestKey

  let content
  if (viewState === "loading" || viewState === "empty" || viewState === "error") {
    content = <StateNotice state={viewState} onRetry={retry} />
  } else if (!ready || !currentMonth) {
    content = <LoadingView />
  } else if (data.screen === "Resumen") {
    content = (
      <Overview
        month={data.summary.month}
        closed={data.summary.month_closed || viewState === "closed"}
        summary={data.summary}
        history={data.history}
        fixed={data.fixed}
        categories={data.categories}
      />
    )
  } else if (data.screen === "Bolsas") {
    content = <Pockets data={data.pockets} />
  } else {
    content = (
      <Movements
        key={shownMonth}
        initialMonth={shownMonth}
        maxMonth={currentMonth}
        pockets={data.pockets.items.map((p) => p.name)}
        load={loadMovements}
      />
    )
  }

  return (
    <div className="min-h-dvh overflow-x-hidden bg-background">
      <Header
        month={shownMonth || "2000-01"}
        setMonth={setMonth}
        theme={theme}
        setTheme={setTheme}
        maxMonth={currentMonth ?? shownMonth}
      />
      <Sidebar active={screen} setActive={setScreen} />
      <main className="md:pl-[76px] lg:pl-60">
        <div className="mx-auto flex max-w-[1280px] flex-col gap-4 px-4 pb-[calc(5.5rem+env(safe-area-inset-bottom))] pt-4 sm:px-6 md:pb-8">
          {content}
          {DEV && <DevelopmentPanel state={state} setState={setState} />}
          <div>
            <button
              type="button"
              onClick={signOut}
              className={cn("min-h-11 rounded-lg px-2 text-sm font-medium text-muted-foreground hover:text-foreground", focusRing)}
            >
              {copy.signOut}
            </button>
          </div>
        </div>
      </main>
    </div>
  )
}
