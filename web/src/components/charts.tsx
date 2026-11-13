import { useEffect, useState } from "react"
import {
  Area,
  AreaChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"

import { Card, CardHeading } from "@/components/shell"
import { copy } from "@/lib/copy"
import { formatCRC, formatPercent } from "@/lib/format"
import { labels } from "@/lib/labels"
import type { CategoriesResponse, HistoryResponse } from "@/lib/types"

const thousands = (value: number) => `₡${Math.round(value / 1000)}k`
const monthTick = (month: string) =>
  new Intl.DateTimeFormat("es-CR", { month: "short" }).format(new Date(`${month}-15T12:00:00`)).replace(".", "")

function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() =>
    typeof window.matchMedia === "function" ? window.matchMedia(query).matches : false,
  )
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return
    const media = window.matchMedia(query)
    const update = () => setMatches(media.matches)
    media.addEventListener("change", update)
    return () => media.removeEventListener("change", update)
  }, [query])
  return matches
}

const series = [
  { key: "income", label: labels.income, color: "var(--primary)" },
  { key: "spent", label: copy.metrics.spent, color: "var(--chart-3)" },
  { key: "saved", label: copy.metrics.saved, color: "var(--chart-5)" },
] as const

export function HistoryChart({ history }: { history: HistoryResponse }) {
  const compact = useMediaQuery("(max-width: 1023px)")
  const summary = history.months
    .map(
      (m) =>
        `${monthTick(m.month)}: ${labels.income.toLowerCase()} ${formatCRC(m.income)}, ${copy.metrics.spent.toLowerCase()} ${formatCRC(m.spent)}, ${copy.metrics.saved.toLowerCase()} ${m.saved < 0 ? "−" : ""}${formatCRC(m.saved)}`,
    )
    .join("; ")
  return (
    <Card>
      <CardHeading title={copy.history} />
      <div className="flex flex-col gap-3 px-2 pb-4 sm:px-4 sm:pb-5 lg:flex-row lg:items-center">
        <div role="img" aria-label={copy.history} className="h-[220px] min-w-0 flex-1 sm:h-[250px]">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={history.months} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} accessibilityLayer>
              <CartesianGrid vertical={false} stroke="var(--border)" />
              <XAxis
                dataKey="month"
                tickFormatter={monthTick}
                tickLine={false}
                axisLine={false}
                interval={compact ? "preserveStartEnd" : 0}
                tick={{ fontSize: compact ? 10 : 11, fill: "var(--muted-foreground)" }}
              />
              <YAxis
                tickFormatter={thousands}
                tickLine={false}
                axisLine={false}
                width={compact ? 44 : 52}
                tickCount={compact ? 3 : 5}
                tick={{ fontSize: compact ? 10 : 11, fill: "var(--muted-foreground)" }}
              />
              <Tooltip
                formatter={(value, name) => [thousands(Number(value)), String(name)]}
                labelFormatter={(label) => monthTick(String(label))}
                contentStyle={{
                  fontSize: 12,
                  background: "var(--popover)",
                  color: "var(--popover-foreground)",
                  border: "1px solid var(--border)",
                  borderRadius: 8,
                }}
              />
              {series.map((s) => (
                <Area
                  key={s.key}
                  type="monotone"
                  dataKey={s.key}
                  name={s.label}
                  stroke={s.color}
                  fill={s.color}
                  fillOpacity={0.12}
                  strokeWidth={2}
                  isAnimationActive={false}
                />
              ))}
            </AreaChart>
          </ResponsiveContainer>
        </div>
        <p className="sr-only">{summary}</p>
        <ul aria-hidden="true" className="flex flex-wrap gap-x-4 gap-y-1 px-2 text-xs text-muted-foreground lg:w-32 lg:flex-col">
          {series.map((s) => (
            <li key={s.key} className="flex items-center gap-2">
              <span className="size-2.5 rounded-full" style={{ background: s.color }} />
              {s.label}
            </li>
          ))}
        </ul>
      </div>
    </Card>
  )
}

const palette = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)"]

export function CategoryChart({ categories }: { categories: CategoriesResponse }) {
  const items = categories.items
  return (
    <Card>
      <CardHeading title={copy.category} detail={`${formatCRC(categories.total)} ${labels.total}`} />
      {items.length === 0 ? (
        <p className="px-4 pb-4 text-sm text-muted-foreground sm:px-5 sm:pb-5">{labels.noCategories}</p>
      ) : (
        <div className="px-4 pb-4 sm:px-5 sm:pb-5">
          <div role="img" aria-label={copy.category} className="mx-auto aspect-square w-full max-w-[220px]">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart accessibilityLayer>
                <Pie
                  data={items}
                  dataKey="value"
                  nameKey="name"
                  innerRadius="62%"
                  outerRadius="100%"
                  stroke="var(--card)"
                  strokeWidth={2}
                  isAnimationActive={false}
                >
                  {items.map((item, index) => (
                    <Cell key={item.name} fill={palette[index % palette.length]} />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
          </div>
          <ul className="mt-4 flex flex-col gap-2">
            {items.map((item, index) => (
              <li key={item.name} className="flex items-center gap-2 text-sm">
                <span
                  aria-hidden="true"
                  className="size-2.5 shrink-0 rounded-full"
                  style={{ background: palette[index % palette.length] }}
                />
                <span className="min-w-0 flex-1 truncate">{item.name}</span>
                <span className="tabular-nums">{formatCRC(item.value)}</span>
                <span className="w-12 text-right text-xs text-muted-foreground tabular-nums">{formatPercent(item.percent)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  )
}
