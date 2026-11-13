import {
  ArrowLeft,
  ArrowRight,
  Check,
  ChevronDown,
  CreditCard,
  LayoutDashboard,
  Monitor,
  Moon,
  MoreHorizontal,
  PiggyBank,
  Sun,
  Wallet,
} from "lucide-react"
import { useEffect, useId, useRef, useState, type ReactNode } from "react"

import { copy } from "@/lib/copy"
import { formatMonth } from "@/lib/format"
import { labels, shortMonth } from "@/lib/labels"
import { shiftMonth } from "@/lib/theme"
import type { Screen, ThemeMode } from "@/lib/types"
import { capitalize, cn } from "@/lib/utils"

const focusRing =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"

/** Cierra un menú con Escape (devolviendo el foco al botón) o con un clic fuera. */
function useDismiss(
  open: boolean,
  close: () => void,
  panel: React.RefObject<HTMLElement | null>,
  trigger: React.RefObject<HTMLButtonElement | null>,
) {
  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        close()
        trigger.current?.focus()
      }
    }
    const onPointer = (event: PointerEvent) => {
      const target = event.target as Node
      if (!panel.current?.contains(target) && !trigger.current?.contains(target)) close()
    }
    document.addEventListener("keydown", onKey)
    document.addEventListener("pointerdown", onPointer)
    return () => {
      document.removeEventListener("keydown", onKey)
      document.removeEventListener("pointerdown", onPointer)
    }
  }, [open, close, panel, trigger])
}

function MonthPicker({ month, setMonth, maxMonth }: { month: string; setMonth: (v: string) => void; maxMonth: string }) {
  const [open, setOpen] = useState(false)
  const [year, setYear] = useState(Number(month.slice(0, 4)))
  const panel = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const titleId = useId()
  useDismiss(open, () => setOpen(false), panel, trigger)
  const maxYear = Number(maxMonth.slice(0, 4))
  const months = Array.from({ length: 12 }, (_, i) => `${year}-${String(i + 1).padStart(2, "0")}`)
  const label = capitalize(formatMonth(month))

  return (
    <div className="flex w-full items-center justify-between gap-1 md:w-auto md:justify-center">
      <button
        type="button"
        aria-label={labels.previousMonth}
        onClick={() => setMonth(shiftMonth(month, -1))}
        className={cn("grid size-11 shrink-0 place-items-center rounded-full hover:bg-muted", focusRing)}
      >
        <ArrowLeft className="size-5" aria-hidden="true" />
      </button>
      <div className="relative min-w-0">
        <button
          ref={trigger}
          type="button"
          aria-haspopup="dialog"
          aria-expanded={open}
          onClick={() => {
            setYear(Number(month.slice(0, 4)))
            setOpen((v) => !v)
          }}
          className={cn(
            "flex min-h-11 items-center gap-1 rounded-full px-3 text-base font-semibold hover:bg-muted",
            focusRing,
          )}
        >
          <span className="sr-only">{labels.chooseMonth}: </span>
          <span className="hidden min-[400px]:inline">{label}</span>
          <span className="min-[400px]:hidden">{capitalize(shortMonth(month))}</span>
          <ChevronDown className="size-4" aria-hidden="true" />
        </button>
        {open && (
          <div
            ref={panel}
            role="dialog"
            aria-labelledby={titleId}
            className="absolute left-1/2 top-full z-50 mt-2 w-[min(18rem,calc(100vw-2rem))] -translate-x-1/2 rounded-xl border bg-popover p-3 text-popover-foreground shadow-lg"
          >
            <div className="mb-2 flex items-center justify-between">
              <button
                type="button"
                aria-label={labels.previousYear}
                onClick={() => setYear((y) => y - 1)}
                className={cn("grid size-11 place-items-center rounded-full hover:bg-muted", focusRing)}
              >
                <ArrowLeft className="size-4" aria-hidden="true" />
              </button>
              <h2 id={titleId} className="text-sm font-semibold">
                {year}
              </h2>
              <button
                type="button"
                aria-label={labels.nextYear}
                disabled={year >= maxYear}
                onClick={() => setYear((y) => y + 1)}
                className={cn(
                  "grid size-11 place-items-center rounded-full hover:bg-muted disabled:opacity-40",
                  focusRing,
                )}
              >
                <ArrowRight className="size-4" aria-hidden="true" />
              </button>
            </div>
            <div className="grid grid-cols-3 gap-1">
              {months.map((value) => {
                const selected = value === month
                const future = value > maxMonth
                return (
                  <button
                    key={value}
                    type="button"
                    disabled={future}
                    aria-pressed={selected}
                    aria-label={formatMonth(value)}
                    onClick={() => {
                      setMonth(value)
                      setOpen(false)
                      trigger.current?.focus()
                    }}
                    className={cn(
                      "min-h-11 rounded-lg text-sm capitalize hover:bg-muted disabled:cursor-not-allowed disabled:opacity-40",
                      selected && "bg-primary text-primary-foreground hover:bg-primary",
                      focusRing,
                    )}
                  >
                    {shortMonth(value).split(" ")[0]}
                  </button>
                )
              })}
            </div>
          </div>
        )}
      </div>
      <button
        type="button"
        aria-label={labels.nextMonth}
        disabled={month >= maxMonth}
        onClick={() => setMonth(shiftMonth(month, 1))}
        className={cn(
          "grid size-11 shrink-0 place-items-center rounded-full hover:bg-muted disabled:opacity-40",
          focusRing,
        )}
      >
        <ArrowRight className="size-5" aria-hidden="true" />
      </button>
    </div>
  )
}

const themeOptions: { value: ThemeMode; label: string; Icon: typeof Sun }[] = [
  { value: "light", label: copy.light, Icon: Sun },
  { value: "dark", label: copy.dark, Icon: Moon },
  { value: "system", label: copy.system, Icon: Monitor },
]

export function ThemeMenu({ theme, setTheme }: { theme: ThemeMode; setTheme: (v: ThemeMode) => void }) {
  const [open, setOpen] = useState(false)
  const panel = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  useDismiss(open, () => setOpen(false), panel, trigger)
  const current = themeOptions.find((o) => o.value === theme) ?? themeOptions[2]!
  return (
    <div className="relative">
      <button
        ref={trigger}
        type="button"
        aria-haspopup="true"
        aria-expanded={open}
        aria-label={`${copy.theme}: ${current.label}`}
        onClick={() => setOpen((v) => !v)}
        className={cn("grid size-11 place-items-center rounded-full hover:bg-muted", focusRing)}
      >
        <current.Icon className="size-5" aria-hidden="true" />
      </button>
      {open && (
        <div
          ref={panel}
          className="absolute right-0 top-full z-50 mt-2 w-40 rounded-xl border bg-popover p-1 text-popover-foreground shadow-lg"
        >
          {themeOptions.map(({ value, label, Icon }) => (
            <button
              key={value}
              type="button"
              aria-pressed={theme === value}
              onClick={() => {
                setTheme(value)
                setOpen(false)
                trigger.current?.focus()
              }}
              className={cn("flex min-h-11 w-full items-center gap-2 rounded-lg px-3 text-sm hover:bg-muted", focusRing)}
            >
              <Icon className="size-4" aria-hidden="true" />
              <span className="flex-1 text-left">{label}</span>
              {theme === value && <Check className="size-4" aria-hidden="true" />}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export function Header({
  month,
  setMonth,
  theme,
  setTheme,
  maxMonth,
}: {
  month: string
  setMonth: (v: string) => void
  theme: ThemeMode
  setTheme: (v: ThemeMode) => void
  maxMonth: string
}) {
  return (
    <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
      <div className="mx-auto flex max-w-[1280px] flex-col gap-1 px-4 py-2 sm:px-6 md:h-16 md:flex-row md:items-center md:justify-between md:py-0">
        <div className="flex items-center justify-between md:flex-1">
          <div className="flex items-center gap-2">
            <span className="grid size-9 place-items-center rounded-xl bg-primary text-primary-foreground">
              <Wallet className="size-5" aria-hidden="true" />
            </span>
            <span className="text-lg font-semibold">{copy.brand}</span>
          </div>
          <div className="md:hidden">
            <ThemeMenu theme={theme} setTheme={setTheme} />
          </div>
        </div>
        <MonthPicker month={month} setMonth={setMonth} maxMonth={maxMonth} />
        <div className="hidden md:flex md:flex-1 md:justify-end">
          <ThemeMenu theme={theme} setTheme={setTheme} />
        </div>
      </div>
    </header>
  )
}

const navIcons = { Resumen: LayoutDashboard, Bolsas: PiggyBank, Movimientos: CreditCard } as const

export function Sidebar({ active, setActive }: { active: Screen; setActive: (v: Screen) => void }) {
  return (
    <aside className="fixed inset-x-0 bottom-0 z-30 border-t bg-background pb-[env(safe-area-inset-bottom)] md:inset-x-auto md:bottom-0 md:left-0 md:top-16 md:w-[76px] md:border-r md:border-t-0 md:pb-0 lg:w-60">
      <nav aria-label={labels.mainNav} className="flex h-full flex-col">
        <ul className="grid grid-cols-3 md:flex md:flex-col md:gap-1 md:p-3">
          {copy.nav.map((item) => {
            const Icon = navIcons[item]
            const selected = item === active
            return (
              <li key={item}>
                <button
                  type="button"
                  aria-label={item}
                  aria-current={selected ? "page" : undefined}
                  onClick={() => setActive(item)}
                  className={cn(
                    "flex min-h-14 w-full flex-col items-center justify-center gap-0.5 text-xs font-medium md:min-h-11 md:rounded-lg lg:flex-row lg:justify-start lg:gap-3 lg:px-3 lg:text-sm",
                    selected ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-muted hover:text-foreground",
                    focusRing,
                  )}
                >
                  <Icon className="size-5" aria-hidden="true" />
                  <span className="md:sr-only lg:not-sr-only">{item}</span>
                </button>
              </li>
            )
          })}
        </ul>
        <p className="mt-auto hidden px-6 py-4 text-xs text-muted-foreground lg:block">{copy.readOnlyLabel}</p>
      </nav>
    </aside>
  )
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <section className={cn("rounded-xl border bg-card text-card-foreground", className)}>{children}</section>
}

export function CardHeading({ title, detail }: { title: string; detail?: string }) {
  return (
    <div className="flex items-start justify-between gap-3 p-4 pb-2 sm:p-5 sm:pb-2">
      <div className="min-w-0">
        <h2 className="text-base font-semibold">{title}</h2>
        {detail && <p className="text-sm text-muted-foreground">{detail}</p>}
      </div>
      <button
        type="button"
        aria-label={`${labels.moreOptions}: ${title}`}
        className={cn("-mr-2 -mt-2 grid size-11 shrink-0 place-items-center rounded-full text-muted-foreground hover:bg-muted", focusRing)}
      >
        <MoreHorizontal className="size-4" aria-hidden="true" />
      </button>
    </div>
  )
}

export function StatusBadge({ closed }: { closed: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium",
        closed ? "bg-muted text-muted-foreground" : "bg-primary/10 text-primary",
      )}
    >
      <span className={cn("size-1.5 rounded-full", closed ? "bg-muted-foreground" : "bg-primary")} aria-hidden="true" />
      {closed ? copy.monthClosed : copy.monthOpen}
    </span>
  )
}

export { focusRing }
