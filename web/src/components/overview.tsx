import { AlertCircle, ArrowDownLeft, ArrowUpRight, CreditCard, PiggyBank, Wallet, X } from "lucide-react"
import { useState } from "react"

import { CategoryChart, HistoryChart } from "@/components/charts"
import { Card, CardHeading, StatusBadge, focusRing } from "@/components/shell"
import { copy } from "@/lib/copy"
import { formatCRC, formatMonth, formatUSD } from "@/lib/format"
import { alertText, alertTone, fixedAmount, fixedDetail, labels } from "@/lib/labels"
import type { Alert, CategoriesResponse, FixedResponse, HistoryResponse, Summary } from "@/lib/types"
import { capitalize, cn } from "@/lib/utils"

const signed = (value: number) => `${value < 0 ? "−" : ""}${formatCRC(value)}`

export function AlertPanel({ monthClosed, alerts }: { monthClosed: boolean; alerts: Alert[] }) {
  const [dismissed, setDismissed] = useState<string[]>([])
  const items = alerts.map((alert) => ({ alert, text: alertText(alert) })).filter((a) => !dismissed.includes(a.text))
  return (
    <Card>
      <div className="flex items-center justify-between gap-2 p-4 pb-2 sm:p-5 sm:pb-2">
        <h2 className="text-base font-semibold">{copy.alerts}</h2>
        {!monthClosed && items.length > 0 && (
          <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">{items.length}</span>
        )}
      </div>
      {monthClosed ? (
        <p className="px-4 pb-4 text-sm text-muted-foreground sm:px-5 sm:pb-5">{copy.readOnly}</p>
      ) : items.length === 0 ? (
        <p className="px-4 pb-4 text-sm text-muted-foreground sm:px-5 sm:pb-5">{labels.allClear}</p>
      ) : (
        <ul className="divide-y px-4 pb-2 sm:px-5">
          {items.map(({ alert, text }) => {
            const tone = alertTone(alert)
            return (
              <li key={text} className="flex items-center gap-3 py-2">
                <AlertCircle
                  aria-hidden="true"
                  className={cn("size-4 shrink-0", tone === "danger" ? "text-destructive" : tone === "warning" ? "text-foreground" : "text-primary")}
                />
                <span className="min-w-0 flex-1 text-sm">{text}</span>
                <button
                  type="button"
                  aria-label={`${labels.dismiss}: ${text}`}
                  onClick={() => setDismissed((d) => [...d, text])}
                  className={cn("-mr-2 grid size-11 shrink-0 place-items-center rounded-full text-muted-foreground hover:bg-muted", focusRing)}
                >
                  <X className="size-4" aria-hidden="true" />
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </Card>
  )
}

export function MetricGrid({ summary }: { summary: Summary }) {
  const metricItems = [
    { label: copy.metrics.income, value: summary.income, Icon: ArrowDownLeft },
    { label: copy.metrics.spent, value: summary.spent, Icon: ArrowUpRight },
    { label: copy.metrics.available, value: summary.available, Icon: Wallet },
    { label: copy.metrics.saved, value: summary.saved, Icon: PiggyBank },
  ]
  return (
    <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
      {metricItems.map(({ label, value, Icon }) => (
        <Card key={label} className="p-4 sm:p-5">
          <div className="flex items-center justify-between gap-2 text-sm text-muted-foreground">
            <span className="min-w-0">{label}</span>
            <Icon className="size-4 shrink-0" aria-hidden="true" />
          </div>
          <p className="mt-2 break-words text-[clamp(1rem,4.3vw,1.5rem)] font-semibold tabular-nums">{signed(value)}</p>
        </Card>
      ))}
    </div>
  )
}

export function Unassigned({ summary }: { summary: Summary }) {
  const data = summary.unassigned
  return (
    <Card>
      <CardHeading title={copy.metrics.unassigned} detail={copy.currencyNote} />
      <dl className="grid grid-cols-2 divide-x px-4 pb-4 sm:px-5 sm:pb-5">
        <div className="pr-3">
          <dt className="text-xs text-muted-foreground">CRC · {data.crc_count}</dt>
          <dd className="text-lg font-semibold tabular-nums">{formatCRC(data.crc_total)}</dd>
        </div>
        <div className="pl-3">
          <dt className="text-xs text-muted-foreground">USD · {data.usd_count}</dt>
          <dd className="text-lg font-semibold tabular-nums">{formatUSD(Number(data.usd_total))}</dd>
        </div>
      </dl>
    </Card>
  )
}

const fixedStatus = {
  paid: { text: copy.paid, className: "text-primary" },
  pending: { text: copy.pending, className: "text-muted-foreground" },
  overdue: { text: copy.late, className: "text-destructive" },
} as const

export function FixedExpenses({ fixed }: { fixed: FixedResponse }) {
  return (
    <Card>
      <CardHeading title={copy.fixed} />
      {fixed.items.length === 0 ? (
        <p className="px-4 pb-4 text-sm text-muted-foreground sm:px-5 sm:pb-5">{labels.noFixed}</p>
      ) : (
        <ul className="divide-y px-4 pb-2 sm:px-5">
          {fixed.items.map((item) => (
            <li key={item.reference} className="flex items-center gap-3 py-3">
              <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-muted">
                <CreditCard className="size-4" aria-hidden="true" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{item.name}</p>
                <p className="text-xs text-muted-foreground">{fixedDetail(item)}</p>
              </div>
              <div className="text-right">
                <p className="text-sm font-medium tabular-nums">{fixedAmount(item)}</p>
                <p className={cn("text-xs font-medium", fixedStatus[item.status].className)}>{fixedStatus[item.status].text}</p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

export function Overview({
  month,
  closed,
  summary,
  history,
  fixed,
  categories,
}: {
  month: string
  closed: boolean
  summary: Summary
  history: HistoryResponse
  fixed: FixedResponse
  categories: CategoriesResponse
}) {
  return (
    <div className="flex flex-col gap-4 sm:gap-5 lg:gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-[clamp(1.5rem,5.5vw,2rem)] font-semibold">
          {labels.overview} {capitalize(formatMonth(month))}
        </h1>
        <StatusBadge closed={closed} />
      </div>
      <AlertPanel key={month} monthClosed={closed} alerts={summary.alerts} />
      <MetricGrid summary={summary} />
      <div className="grid gap-4 sm:gap-5 lg:grid-cols-12 lg:gap-6">
        <div className="flex min-w-0 flex-col gap-4 sm:gap-5 lg:col-span-8 lg:gap-6">
          <HistoryChart history={history} />
          <FixedExpenses fixed={fixed} />
        </div>
        <div className="flex min-w-0 flex-col gap-4 sm:gap-5 lg:col-span-4 lg:gap-6">
          <Unassigned summary={summary} />
          <CategoryChart categories={categories} />
        </div>
      </div>
    </div>
  )
}
