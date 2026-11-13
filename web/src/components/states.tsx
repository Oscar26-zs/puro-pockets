import { AlertCircle, CircleHelp, Wallet } from "lucide-react"
import { useId, useState, type FormEvent } from "react"

import { Card, focusRing } from "@/components/shell"
import { copy } from "@/lib/copy"

import { cn } from "@/lib/utils"

export type ViewState = "normal" | "loading" | "empty" | "error" | "closed"

export function LoadingView() {
  return (
    <div role="status" className="flex animate-pulse flex-col gap-4 sm:gap-5 lg:gap-6">
      <span className="sr-only">{copy.loading}</span>
      <div className="h-8 w-56 rounded-lg bg-muted" />
      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="h-24 rounded-xl bg-muted" />
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-12">
        <div className="h-64 rounded-xl bg-muted lg:col-span-8" />
        <div className="h-64 rounded-xl bg-muted lg:col-span-4" />
      </div>
    </div>
  )
}

export function StateNotice({ state, onRetry }: { state: ViewState; onRetry: () => void }) {
  if (state === "loading") return <LoadingView />
  if (state === "empty") {
    return (
      <Card className="flex flex-col items-center gap-3 p-8 text-center">
        <CircleHelp className="size-6 text-muted-foreground" aria-hidden="true" />
        <p className="text-sm text-muted-foreground">{copy.empty}</p>
      </Card>
    )
  }
  if (state === "error") {
    return (
      <Card className="flex flex-col items-center gap-3 p-8 text-center" >
        <AlertCircle className="size-6 text-destructive" aria-hidden="true" />
        <p role="alert" className="text-sm">{copy.error}</p>
        <button
          type="button"
          onClick={onRetry}
          className={cn("min-h-11 rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground", focusRing)}
        >
          {copy.retry}
        </button>
      </Card>
    )
  }
  return null
}

const states: { value: ViewState; label: string }[] = [
  { value: "normal", label: copy.standard },
  { value: "loading", label: copy.loadingState },
  { value: "empty", label: copy.emptyState },
  { value: "error", label: copy.errorState },
  { value: "closed", label: copy.closedMonth },
]

/** Solo en la compilación de desarrollo (decisión P7 del Hito 10). */
export function DevelopmentPanel({ state, setState }: { state: ViewState; setState: (v: ViewState) => void }) {
  return (
    <details className="rounded-xl border p-4">
      <summary className={cn("min-h-11 cursor-pointer content-center text-sm font-medium", focusRing)}>{copy.development}</summary>
      <p className="mt-3 text-xs text-muted-foreground">{copy.state}</p>
      <div className="mt-2 flex flex-wrap gap-2">
        {states.map((s) => (
          <button
            key={s.value}
            type="button"
            aria-pressed={state === s.value}
            onClick={() => setState(s.value)}
            className={cn(
              "min-h-11 rounded-lg border px-3 text-sm hover:bg-muted",
              state === s.value && "border-primary bg-primary/10 text-primary",
              focusRing,
            )}
          >
            {s.label}
          </button>
        ))}
      </div>
    </details>
  )
}

export function LoginScreen({ onLogin }: { onLogin: (password: string) => Promise<string | null> }) {
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const inputId = useId()
  const errorId = useId()

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!password || busy) return
    setBusy(true)
    const problem = await onLogin(password)
    setBusy(false)
    setPassword("")
    setError(problem)
  }

  return (
    <main className="grid min-h-dvh place-items-center bg-background px-4">
      <Card className="w-full max-w-sm p-6">
        <form onSubmit={submit} className="flex flex-col gap-4">
          <div className="flex items-center gap-2">
            <span className="grid size-9 place-items-center rounded-xl bg-primary text-primary-foreground">
              <Wallet className="size-5" aria-hidden="true" />
            </span>
            <span className="text-lg font-semibold">{copy.brand}</span>
          </div>
          <div>
            <h1 className="text-2xl font-semibold">{copy.loginTitle}</h1>
            <p className="text-sm text-muted-foreground">{copy.loginDescription}</p>
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor={inputId} className="text-sm font-medium">
              {copy.password}
            </label>
            <input
              id={inputId}
              type="password"
              autoComplete="current-password"
              required
              value={password}
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? errorId : undefined}
              onChange={(e) => setPassword(e.target.value)}
              className="min-h-11 rounded-lg border bg-background px-3 text-base focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>
          {error && (
            <p id={errorId} role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={busy}
            className={cn("min-h-11 rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-60", focusRing)}
          >
            {copy.enter}
          </button>
          <p className="text-center text-xs text-muted-foreground">{copy.subtitle}</p>
        </form>
      </Card>
    </main>
  )
}

