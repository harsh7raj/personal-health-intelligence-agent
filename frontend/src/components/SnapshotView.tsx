import type { ReactNode } from "react"
import type { Snapshot } from "@/lib/endpoints"
import { Badge, Card, CardContent, CardHeader, CardTitle } from "@/components/ui"
import { cn } from "@/lib/utils"

export function trendClass(trend: string | null): string {
  if (trend === "rising" || trend === "increasing") return "border-amber-400 text-amber-600"
  if (trend === "falling") return "border-blue-400 text-blue-600"
  return "border-muted-foreground/30 text-muted-foreground"
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">{title}</CardTitle>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  )
}

function BulletList({ items }: { items: string[] }) {
  if (items.length === 0) return <p className="text-sm text-muted-foreground">Nothing recorded.</p>
  return (
    <ul className="space-y-1 text-sm">
      {items.map((t, i) => (
        <li key={i} className="flex gap-2">
          <span className="text-muted-foreground">•</span>
          <span>{t}</span>
        </li>
      ))}
    </ul>
  )
}

export function SnapshotView({ data }: { data: Snapshot }) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Section title="Active Problems">
        {data.active_problems.length === 0 ? (
          <p className="text-sm text-muted-foreground">None.</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {data.active_problems.map((p, i) => (
              <li key={i} className="flex items-center justify-between gap-2">
                <span>
                  {p.name}
                  {p.frequency ? ` · ${p.frequency}` : ""}
                </span>
                {p.trend && <Badge className={cn(trendClass(p.trend))}>{p.trend}</Badge>}
              </li>
            ))}
          </ul>
        )}
      </Section>
      <Section title="Recent Changes">
        <BulletList items={data.recent_changes} />
      </Section>
      <Section title="AI Observations">
        <BulletList items={data.observations} />
      </Section>
      <Section title="Missing Information">
        <BulletList items={data.missing_information} />
      </Section>
      <Section title="Suggested Next Actions">
        <BulletList items={data.suggested_next_actions} />
      </Section>
    </div>
  )
}
