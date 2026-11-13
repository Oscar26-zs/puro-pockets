import { Card } from "@/components/shell"
import { copy } from "@/lib/copy"
import { formatCRC, formatMonth, formatPercent } from "@/lib/format"
import { labels } from "@/lib/labels"
import type { Pocket, PocketsResponse } from "@/lib/types"
import { cn } from "@/lib/utils"

const signed = (value: number) => `${value < 0 ? "−" : ""}${formatCRC(value)}`

/** Barra con `role="progressbar"`. El ancho se limita a 100 %; `aria-valuenow` también (§13 de
 * dashboard.md lo marcaba pendiente) y el valor real va en `aria-valuetext`. */
export function ProgressBar({ label, value, tone }: { label: string; value: number; tone?: "warning" | "danger" | null }) {
  const width = Math.max(0, Math.min(value, 100))
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={width}
      aria-valuetext={formatPercent(value)}
      className="h-2 w-full overflow-hidden rounded bg-muted"
    >
      <div
        className={cn("h-full rounded", tone === "danger" ? "bg-destructive" : tone === "warning" ? "bg-foreground/70" : "bg-primary")}
        style={{ width: `${width}%` }}
      />
    </div>
  )
}

function Row({ label, value, strong, danger }: { label: string; value: string; strong?: boolean; danger?: boolean }) {
  return (
    <div className={cn("flex items-baseline justify-between gap-3 text-sm", danger && "text-destructive")}>
      <dt className={danger ? undefined : "text-muted-foreground"}>{label}</dt>
      <dd className={cn("tabular-nums", strong && "font-semibold")}>{value}</dd>
    </div>
  )
}

function AlertBadge({ alert }: { alert: Pocket["alert"] }) {
  if (!alert) return null
  return (
    <span
      className={cn(
        "rounded-full px-2 py-0.5 text-xs font-medium",
        alert === "danger" ? "border border-destructive text-destructive" : "bg-muted text-foreground",
      )}
    >
      {alert === "danger" ? copy.danger : copy.warning}
    </span>
  )
}

export function PocketCard({ pocket }: { pocket: Pocket }) {
  const goal = pocket.goal
  return (
    <Card className="flex flex-col gap-4 p-4 sm:p-5">
      <div className="flex items-start justify-between gap-2">
        <h2 className="text-base font-semibold">{pocket.name}</h2>
        <AlertBadge alert={pocket.alert} />
      </div>
      {pocket.kind === "consumo" ? (
        <>
          <div className="flex flex-col gap-2">
            <ProgressBar label={`${pocket.name}: ${copy.used}`} value={pocket.used ?? 0} tone={pocket.alert} />
            <p className="text-sm">
              <span className={cn("font-semibold", pocket.alert === "danger" && "text-destructive")}>
                {formatPercent(pocket.used ?? 0)}
              </span>{" "}
              <span className="text-muted-foreground">{copy.used}</span>
            </p>
          </div>
          <dl className="flex flex-col gap-1.5">
            <Row label={copy.original} value={formatCRC(pocket.assigned)} />
            {pocket.received > 0 && <Row label={copy.received} value={`+${formatCRC(pocket.received)}`} />}
            {pocket.sent > 0 && <Row label={copy.sent} value={`−${formatCRC(pocket.sent)}`} />}
            <Row label={copy.adjusted} value={formatCRC(pocket.adjusted)} />
            <Row label={copy.metrics.spent} value={formatCRC(pocket.spent)} />
            <Row label={copy.metrics.available} value={signed(pocket.available ?? 0)} strong danger={pocket.negative} />
          </dl>
        </>
      ) : (
        <>
          <dl>
            <Row label={copy.balance} value={signed(pocket.balance ?? 0)} strong danger={pocket.negative} />
          </dl>
          {goal && (
            <div className="flex flex-col gap-2 border-t pt-4">
              <p className="text-sm">
                <span className="text-muted-foreground">{copy.goal}:</span> <span className="font-medium">{goal.name}</span>
              </p>
              <ProgressBar label={`${copy.progress}: ${goal.name}`} value={goal.progress} />
              <dl className="flex flex-col gap-1.5">
                <Row label={copy.progress} value={`${formatPercent(goal.progress)} · ${formatCRC(goal.target)}`} />
                {goal.remaining > 0 ? (
                  <>
                    <Row label={copy.remaining} value={formatCRC(goal.remaining)} />
                    <Row
                      label={copy.estimate}
                      value={goal.estimated_month ? formatMonth(goal.estimated_month) : copy.noEstimate}
                    />
                  </>
                ) : (
                  <Row label={copy.estimate} value={labels.reached} />
                )}
              </dl>
            </div>
          )}
        </>
      )}
    </Card>
  )
}

export function Pockets({ data }: { data: PocketsResponse }) {
  return (
    <div className="flex flex-col gap-4 sm:gap-5">
      <div>
        <h1 className="text-[clamp(1.5rem,5.5vw,2rem)] font-semibold">{copy.pockets}</h1>
        <p className="text-sm text-muted-foreground">{labels.pocketsDetail}</p>
      </div>
      {data.items.length === 0 ? (
        <Card className="p-6 text-center text-sm text-muted-foreground">{labels.noPockets}</Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {data.items.map((pocket) => (
            <PocketCard key={pocket.name} pocket={pocket} />
          ))}
        </div>
      )}
    </div>
  )
}
