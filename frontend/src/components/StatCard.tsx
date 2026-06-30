import type { ReactNode } from "react"
import { Card } from "@/components/ui"
import { TONE, trendTone } from "@/lib/tone"
import { cn } from "@/lib/utils"

export function StatCard({
  label,
  value,
  sub,
  popover,
}: {
  label: string
  value: ReactNode
  sub?: ReactNode
  /** Optional content revealed on hover (sparkline or short detail). No navigation. */
  popover?: ReactNode
}) {
  return (
    <Card className={cn("relative p-3.5", popover && "group cursor-default")}>
      <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</p>
      <div className="mt-1.5 flex items-end justify-between gap-2">
        <span className="text-2xl font-bold leading-none tracking-tight text-foreground">{value}</span>
        {sub}
      </div>
      {popover && (
        <div className="pointer-events-none absolute left-0 right-0 top-full z-20 mt-2 origin-top scale-95 rounded-lg border bg-card p-3 opacity-0 shadow-xl transition-all duration-150 group-hover:scale-100 group-hover:opacity-100">
          {popover}
        </div>
      )}
    </Card>
  )
}

export function TrendPill({ trend, delta }: { trend?: string | null; delta?: number | null }) {
  const c = TONE[trendTone(trend)]
  const text = delta != null ? `${delta >= 0 ? "+" : ""}${Math.round(delta * 100)}%` : c.label
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold", c.chip)}>
      <span>{c.arrow}</span>
      {text}
    </span>
  )
}
