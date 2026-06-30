import { useQuery } from "@tanstack/react-query"
import { useAuth } from "@/lib/auth"
import * as ep from "@/lib/endpoints"
import { AlertsPanel } from "@/components/AlertsPanel"
import { StatCard, TrendPill } from "@/components/StatCard"
import { Timeline } from "@/components/Timeline"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui"

function episodesOf(freq: string | null): number {
  const m = freq?.match(/(\d+)/)
  return m ? Number(m[1]) : 0
}

function Bullets({ items }: { items: string[] }) {
  if (!items.length) return <p className="text-sm text-muted-foreground">None.</p>
  return (
    <ul className="space-y-2 text-sm">
      {items.map((t, i) => (
        <li key={i} className="flex gap-2">
          <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
          <span>{t}</span>
        </li>
      ))}
    </ul>
  )
}

export default function DashboardPage() {
  const { patient } = useAuth()
  const pid = patient!.id
  const snap = useQuery({ queryKey: ["snapshot", pid], queryFn: () => ep.getSnapshot(pid) })
  const vs = useQuery({ queryKey: ["vitals-summary", pid], queryFn: () => ep.getVitalsSummary(pid) })
  const problems = useQuery({ queryKey: ["problems", pid], queryFn: () => ep.getProblems(pid) })
  const vitals = useQuery({ queryKey: ["vitals", pid], queryFn: () => ep.listVitals(pid) })

  const summary = vs.data ?? []
  const sysS = summary.find((s) => s.vital_type === "bp_systolic")
  const diaS = summary.find((s) => s.vital_type === "bp_diastolic")
  const weightS = summary.find((s) => s.vital_type === "weight")
  const active = snap.data?.active_problems ?? []
  const top = [...active].sort((a, b) => episodesOf(b.frequency) - episodesOf(a.frequency))[0]
  const bpValue =
    sysS?.latest != null
      ? `${Math.round(sysS.latest)}/${diaS?.latest != null ? Math.round(diaS.latest) : "–"}`
      : "—"

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Today's Snapshot</h1>
        <p className="text-sm text-muted-foreground">A longitudinal view of {patient?.name}'s health.</p>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard label="Active Problems" value={active.length} sub={<span className="text-xs text-muted-foreground">tracked now</span>} />
        <StatCard label="Latest BP" value={bpValue} sub={sysS?.trend ? <TrendPill trend={sysS.trend} delta={sysS.delta_pct} /> : null} />
        <StatCard
          label={top ? `${top.name} episodes` : "Recurring"}
          value={top ? episodesOf(top.frequency) : "—"}
          sub={top?.trend ? <TrendPill trend={top.trend} /> : null}
        />
        <StatCard label="Weight" value={weightS?.latest != null ? `${weightS.latest} kg` : "—"} sub={weightS?.trend ? <TrendPill trend={weightS.trend} delta={weightS.delta_pct} /> : null} />
      </div>

      <AlertsPanel patientId={pid} />

      <div className="grid gap-4 md:grid-cols-3">
        <Card className="md:col-span-2">
          <CardHeader>
            <CardTitle>Health Timeline</CardTitle>
          </CardHeader>
          <CardContent>
            <Timeline problems={problems.data ?? []} vitals={vitals.data ?? []} summaries={summary} />
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>AI Observations</CardTitle>
            </CardHeader>
            <CardContent>
              <Bullets items={snap.data?.observations ?? []} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Suggested Actions</CardTitle>
            </CardHeader>
            <CardContent>
              <Bullets items={snap.data?.suggested_next_actions ?? []} />
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
