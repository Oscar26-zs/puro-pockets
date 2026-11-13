import { ArrowDownLeft, ArrowDownRight, ArrowLeft, ArrowRight, ArrowUpRight, Menu, X } from "lucide-react"
import { useEffect, useId, useRef, useState } from "react"

import { Card, focusRing } from "@/components/shell"
import { copy } from "@/lib/copy"
import { formatDate } from "@/lib/format"
import { labels, movementAmount, movementDescription, movementPocket } from "@/lib/labels"
import type { Movement, MovementFiltersValue, MovementsResponse } from "@/lib/types"
import { cn } from "@/lib/utils"

const control =
  "min-h-11 w-full rounded-lg border bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"

type FilterProps = {
  type: MovementFiltersValue["type"]
  setType: (v: MovementFiltersValue["type"]) => void
  pocket: string
  setPocket: (v: string) => void
  month: string
  setMonth: (v: string) => void
  includeVoid: boolean
  setIncludeVoid: (v: boolean) => void
  open: boolean
  setOpen: (v: boolean) => void
  pockets: string[]
  maxMonth: string
}

function FilterControls(props: FilterProps & { idPrefix: string }) {
  const { idPrefix: id } = props
  return (
    <>
      <div className="flex flex-col gap-1">
        <label htmlFor={`${id}-type`} className="text-xs font-medium text-muted-foreground">
          {copy.type}
        </label>
        <select
          id={`${id}-type`}
          className={control}
          value={props.type}
          onChange={(e) => props.setType(e.target.value as MovementFiltersValue["type"])}
        >
          <option value="">{copy.all}</option>
          <option value="gasto">{labels.types.gasto}</option>
          <option value="ingreso">{labels.types.ingreso}</option>
          <option value="transferencia">{labels.types.transferencia}</option>
        </select>
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor={`${id}-pocket`} className="text-xs font-medium text-muted-foreground">
          {copy.pocket}
        </label>
        <select
          id={`${id}-pocket`}
          className={control}
          value={props.pocket}
          disabled={props.type === "ingreso"}
          onChange={(e) => props.setPocket(e.target.value)}
        >
          <option value="">{copy.all}</option>
          {props.pockets.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </div>
      <div className="flex flex-col gap-1">
        <span aria-hidden="true" className="text-xs font-medium text-muted-foreground">
          {copy.month}
        </span>
        <input
          type="month"
          aria-label={copy.month}
          className={control}
          value={props.month}
          max={props.maxMonth}
          onChange={(e) => e.target.value && props.setMonth(e.target.value)}
        />
      </div>
      <label className="flex min-h-11 items-center gap-2 text-sm lg:self-end">
        <input
          type="checkbox"
          className="size-4 accent-[var(--primary)]"
          checked={props.includeVoid}
          onChange={(e) => props.setIncludeVoid(e.target.checked)}
        />
        {copy.canceled}
      </label>
    </>
  )
}

export function MovementFilters(props: FilterProps) {
  const panelId = useId()
  const titleId = useId()
  const panel = useRef<HTMLDivElement>(null)
  const opener = useRef<HTMLButtonElement>(null)
  const { open, setOpen } = props

  useEffect(() => {
    if (!open) return
    panel.current?.querySelector<HTMLElement>("select, input")?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false)
        opener.current?.focus()
      }
    }
    document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  }, [open, setOpen])

  return (
    <>
      <div className="hidden gap-3 lg:grid lg:grid-cols-[repeat(3,minmax(0,12rem))_auto] lg:items-end">
        <FilterControls {...props} idPrefix="inline" />
      </div>
      <div className="lg:hidden">
        <button
          ref={opener}
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen(!open)}
          className={cn("inline-flex min-h-11 items-center gap-2 rounded-lg border px-4 text-sm font-medium hover:bg-muted", focusRing)}
        >
          <Menu className="size-4" aria-hidden="true" />
          {copy.filters}
        </button>
        {open && (
          <>
            <div className="fixed inset-0 z-40 bg-foreground/20" aria-hidden="true" onClick={() => setOpen(false)} />
            <div
              ref={panel}
              id={panelId}
              role="dialog"
              aria-modal="true"
              aria-labelledby={titleId}
              className="fixed inset-x-0 bottom-0 z-50 flex max-h-[85vh] flex-col gap-3 overflow-y-auto rounded-t-2xl border-t bg-background p-4 pb-[calc(1rem+env(safe-area-inset-bottom))] shadow-xl sm:px-6"
            >
              <div className="flex items-center justify-between">
                <h2 id={titleId} className="text-base font-semibold">
                  {copy.filters}
                </h2>
                <button
                  type="button"
                  aria-label={labels.closeFilters}
                  onClick={() => {
                    setOpen(false)
                    opener.current?.focus()
                  }}
                  className={cn("grid size-11 place-items-center rounded-full hover:bg-muted", focusRing)}
                >
                  <X className="size-4" aria-hidden="true" />
                </button>
              </div>
              <FilterControls {...props} idPrefix="panel" />
              <button
                type="button"
                onClick={() => {
                  setOpen(false)
                  opener.current?.focus()
                }}
                className={cn("min-h-11 rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground", focusRing)}
              >
                {labels.seeResults}
              </button>
            </div>
          </>
        )}
      </div>
    </>
  )
}

function StatusTag({ movement }: { movement: Movement }) {
  if (movement.voided) {
    return <span className="rounded-full border px-2 py-0.5 text-xs font-medium text-foreground">{copy.void}</span>
  }
  if (movement.pending) {
    return <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">{copy.pending}</span>
  }
  return null
}

const typeIcon = { gasto: ArrowUpRight, ingreso: ArrowDownLeft, transferencia: ArrowDownRight } as const

export function MovementList({ items }: { items: Movement[] }) {
  if (items.length === 0) {
    return <Card className="p-6 text-center text-sm text-muted-foreground">{copy.empty}</Card>
  }
  return (
    <>
      <ul className="flex flex-col gap-3 md:hidden">
        {items.map((m) => {
          const Icon = typeIcon[m.type]
          return (
            <li key={m.ref}>
              <Card className="flex items-start gap-3 p-4">
                <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-muted">
                  <Icon className="size-4" aria-hidden="true" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className={cn("break-words text-sm font-medium", m.voided && "line-through")}>{movementDescription(m)}</p>
                  <p className="text-xs text-muted-foreground">
                    {formatDate(m.date)} · {movementPocket(m)} · {m.ref}
                  </p>
                  {m.reason && (
                    <p className="text-xs text-muted-foreground">
                      {copy.reason}: {labels.reasons[m.reason] ?? m.reason}
                    </p>
                  )}
                </div>
                <div className="flex flex-col items-end gap-1">
                  <span className={cn("text-sm font-semibold tabular-nums", m.voided && "line-through")}>{movementAmount(m)}</span>
                  <StatusTag movement={m} />
                </div>
              </Card>
            </li>
          )
        })}
      </ul>
      <Card className="hidden overflow-x-auto md:block">
        <table className="w-full text-sm">
          <thead className="border-b text-left text-xs text-muted-foreground">
            <tr>
              <th scope="col" className="px-4 py-3 font-medium">{copy.date}</th>
              <th scope="col" className="px-4 py-3 font-medium">{copy.description}</th>
              <th scope="col" className="px-4 py-3 font-medium">{copy.pocket}</th>
              <th scope="col" className="px-4 py-3 text-right font-medium">{copy.amount}</th>
              <th scope="col" className="px-4 py-3 font-medium">{copy.status}</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {items.map((m) => (
              <tr key={m.ref} className={cn(m.voided && "text-muted-foreground")}>
                <td className="whitespace-nowrap px-4 py-3">{formatDate(m.date)}</td>
                <td className="px-4 py-3">
                  <span className={cn("font-medium", m.voided && "line-through")}>{movementDescription(m)}</span>
                  <span className="block text-xs text-muted-foreground">
                    {m.ref}
                    {m.reason ? ` · ${copy.reason}: ${labels.reasons[m.reason] ?? m.reason}` : ""}
                  </span>
                </td>
                <td className="px-4 py-3">{movementPocket(m)}</td>
                <td className={cn("whitespace-nowrap px-4 py-3 text-right font-semibold tabular-nums", m.voided && "line-through")}>
                  {movementAmount(m)}
                </td>
                <td className="px-4 py-3">
                  <StatusTag movement={m} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </>
  )
}

export function Movements({
  initialMonth,
  maxMonth,
  pockets,
  load,
}: {
  initialMonth: string
  maxMonth: string
  pockets: string[]
  load: (filters: MovementFiltersValue) => Promise<MovementsResponse | null>
}) {
  const [type, setType] = useState<MovementFiltersValue["type"]>("")
  const [pocket, setPocket] = useState("")
  const [month, setMonth] = useState(initialMonth)
  const [includeVoid, setIncludeVoid] = useState(false)
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState(false)
  const [data, setData] = useState<MovementsResponse | null>(null)

  useEffect(() => {
    let alive = true
    load({ type, pocket, month, includeVoid, page }).then((result) => {
      if (alive) setData(result)
    })
    return () => {
      alive = false
    }
  }, [load, type, pocket, month, includeVoid, page])

  const reset = <T,>(setter: (v: T) => void) => (value: T) => {
    setter(value)
    setPage(1)
  }

  return (
    <div className="flex flex-col gap-4 sm:gap-5">
      <div>
        <h1 className="text-[clamp(1.5rem,5.5vw,2rem)] font-semibold">{copy.movements}</h1>
        <p className="text-sm text-muted-foreground">{labels.movementsDetail}</p>
      </div>
      <MovementFilters
        type={type}
        setType={reset(setType)}
        pocket={pocket}
        setPocket={reset(setPocket)}
        month={month}
        setMonth={reset(setMonth)}
        includeVoid={includeVoid}
        setIncludeVoid={reset(setIncludeVoid)}
        open={open}
        setOpen={setOpen}
        pockets={pockets}
        maxMonth={maxMonth}
      />
      {data === null ? (
        <div role="status" className="h-40 animate-pulse rounded-xl bg-muted">
          <span className="sr-only">{copy.loading}</span>
        </div>
      ) : (
        <MovementList items={data.items} />
      )}
      {data && (page > 1 || data.has_more) && (
        <nav aria-label={labels.page} className="flex items-center justify-between gap-2">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
            className={cn("inline-flex min-h-11 items-center gap-2 rounded-lg border px-4 text-sm hover:bg-muted disabled:opacity-40", focusRing)}
          >
            <ArrowLeft className="size-4" aria-hidden="true" />
            {labels.previousPage}
          </button>
          <span className="text-sm text-muted-foreground">
            {labels.page} {page}
          </span>
          <button
            type="button"
            disabled={!data.has_more}
            onClick={() => setPage((p) => p + 1)}
            className={cn("inline-flex min-h-11 items-center gap-2 rounded-lg border px-4 text-sm hover:bg-muted disabled:opacity-40", focusRing)}
          >
            {labels.nextPage}
            <ArrowRight className="size-4" aria-hidden="true" />
          </button>
        </nav>
      )}
    </div>
  )
}
