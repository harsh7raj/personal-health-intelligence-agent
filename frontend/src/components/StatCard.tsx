import type { ReactNode } from "react"
import { Card } from "@/components/ui"
import { TONE, trendTone } from "@/lib/tone"
import { cn } from "@/lib/utils"

export function StatCard({
  label,
  value,
  sub,
}: {
  label: string
  value: ReactNode
  sub?: ReactNode
}) {
  return (
    <Card className="p-5">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{label}</p>
      <div className="mt-3 flex items-end justify-between gap-2">
        <span className="text-3xl font-bold leading-none tracking-tight text-foreground">{value}</span>
        {sub}
      </div>
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
