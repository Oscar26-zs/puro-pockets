// Cliente de la API del dashboard. Mismo origen (sin CORS); la cookie de sesión es HttpOnly y el
// navegador la envía sola. Nada se guarda en localStorage, sessionStorage ni en la URL.
import type {
  CategoriesResponse,
  FixedResponse,
  HistoryResponse,
  MovementFiltersValue,
  MovementsResponse,
  PocketsResponse,
  SessionInfo,
  Summary,
} from "./types"

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: "same-origin",
    cache: "no-store",
    headers: { Accept: "application/json", ...(init?.headers ?? {}) },
    ...init,
  })
  if (!response.ok) {
    let detail = ""
    try {
      detail = ((await response.json()) as { detail?: string }).detail ?? ""
    } catch {
      detail = ""
    }
    throw new ApiError(response.status, detail)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

const withMonth = (path: string, month: string) => `${path}?${new URLSearchParams({ month })}`

export const api = {
  session: () => request<SessionInfo>("/api/session"),
  login: (password: string) =>
    request<void>("/api/session/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    }),
  logout: () => request<void>("/api/session/logout", { method: "POST" }),
  summary: (month: string) => request<Summary>(withMonth("/api/summary", month)),
  pockets: (month: string) => request<PocketsResponse>(withMonth("/api/pockets", month)),
  categories: (month: string) => request<CategoriesResponse>(withMonth("/api/categories", month)),
  history: (month: string) => request<HistoryResponse>(withMonth("/api/history", month)),
  fixed: (month: string) => request<FixedResponse>(withMonth("/api/fixed", month)),
  movements: (filters: MovementFiltersValue) => {
    const params = new URLSearchParams({
      month: filters.month,
      include_voided: String(filters.includeVoid),
      page: String(filters.page),
    })
    if (filters.type) params.set("type", filters.type)
    if (filters.pocket && filters.type !== "ingreso") params.set("pocket", filters.pocket)
    return request<MovementsResponse>(`/api/movements?${params}`)
  },
}
