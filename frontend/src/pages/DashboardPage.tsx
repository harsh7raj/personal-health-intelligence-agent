import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { X } from "lucide-react"
import { useAuth } from "@/lib/auth"
import * as ep from "@/lib/endpoints"
import type { Problem, VitalReading } from "@/lib/endpoints"
import { AlertsPanel } from "@/components/AlertsPanel"
import { StatCard, TrendPill } from "@/components/StatCard"
import { Sparkline } from "@/components/Sparkline"
import { Timeline } from "@/components/Timeline"
import { ProblemTimelineModal } from "@/components/ProblemTimelineModal"
import { TONE, severityTone, trendTone } from "@/lib/tone"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui"
import { cn } from "@/lib/utils"

function episodesOf(freq: string | null): number {
  const m = freq?.match(/(\d+)/)
  return m ? Number(m[1]) : 0
}

function seriesOf(vitals: VitalReading[], type: string, n = 12): number[] {
  return vitals
    .filter((v) => v.vital_type === type)
    .sort((a, b) => +new Date(a.recorded_at) - +new Date(b.recorded_at))
    .slice(-n)
    .map((v) => v.value)
}

function SparkPopover({ title, values, stroke, caption }: { title: string; values: number[]; stroke: string; caption?: string }) {
  if (values.length < 2) return <p className="text-xs text-muted-foreground">Not enough readings yet.</p>
  return (
    <div>
      <p className="mb-1 text-xs font-medium text-muted-foreground">{title}</p>
      <Sparkline values={values} stroke={stroke} />
      {caption && <p className="mt-1 text-xs text-muted-foreground">{caption}</p>}
    </div>
  )
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

function SuggestedActionsCard({ pid }: { pid: number }) {
  const qc = useQueryClient()
  const actions = useQuery({ queryKey: ["suggested-actions", pid], queryFn: () => ep.listSuggestedActions(pid) })
  const dismiss = useMutation({
    mutationFn: (actionId: number) => ep.dismissSuggestedAction(pid, actionId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["suggested-actions", pid] })
      qc.invalidateQueries({ queryKey: ["snapshot", pid] })
    },
  })
  const items = actions.data ?? []
  return (
    <Card>
      <CardHeader>
        <CardTitle>Suggested Actions</CardTitle>
      </CardHeader>
      <CardContent>
        {!items.length ? (
          <p className="text-sm text-muted-foreground">None.</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {items.map((a) => (
              <li key={a.id} className="flex items-start gap-2">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                <span className="flex-1">{a.text}</span>
                <button
                  onClick={() => dismiss.mutate(a.id)}
                  disabled={dismiss.isPending}
                  className="rounded p-0.5 text-muted-foreground transition hover:bg-accent hover:text-foreground"
                  aria-label={`Dismiss: ${a.text}`}
                  title="Dismiss"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

function ProblemsCard({ problems, onSelect }: { problems: Problem[]; onSelect: (id: number) => void }) {
  const order = (s: string) => (s === "resolved" ? 1 : 0)
  const sorted = [...problems].sort((a, b) => order(a.status) - order(b.status))
  return (
    <Card>
      <CardHeader>
        <CardTitle>Tracked Problems</CardTitle>
      </CardHeader>
      <CardContent>
        {sorted.length === 0 ? (
          <p className="text-sm text-muted-foreground">None tracked.</p>
        ) : (
          <ul className="space-y-1.5">
            {sorted.map((p) => {
              const c = TONE[p.severity ? severityTone(p.severity) : trendTone(p.trend)]
              return (
                <li key={p.id}>
                  <button
                    onClick={() => onSelect(p.id)}
                    className="flex w-full items-center gap-2.5 rounded-lg border border-border px-3 py-2 text-left text-sm transition hover:bg-accent"
                  >
                    <span className={cn("h-2 w-2 shrink-0 rounded-full", c.dot)} />
                    <span className="flex-1 capitalize text-foreground">{p.name}</span>
                    {p.frequency && <span className="text-xs text-muted-foreground">{p.frequency}</span>}
                    <span
                      className={cn(
                        "rounded-full px-2 py-0.5 text-[10px] font-semibold",
                        p.status === "resolved" ? TONE.down.chip : p.status === "managed" ? TONE.flat.chip : TONE.up.chip,
                      )}
                    >
                      {p.status}
                    </span>
                    <span className="text-muted-foreground" aria-hidden>›</span>
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

export default function DashboardPage() {
  const { patient } = useAuth()
  const pid = patient!.id
  const [problemId, setProblemId] = useState<number | null>(null)
  const snap = useQuery({ queryKey: ["snapshot", pid, 10], queryFn: () => ep.getSnapshot(pid, 10) })
  const vs = useQuery({ queryKey: ["vitals-summary", pid], queryFn: () => ep.getVitalsSummary(pid) })
  const problems = useQuery({ queryKey: ["problems", pid], queryFn: () => ep.getProblems(pid) })
  const vitals = useQuery({ queryKey: ["vitals", pid], queryFn: () => ep.listVitals(pid) })

  const summary = vs.data ?? []
  const allVitals = vitals.data ?? []
  const sysS = summary.find((s) => s.vital_type === "bp_systolic")
  const diaS = summary.find((s) => s.vital_type === "bp_diastolic")
  const weightS = summary.find((s) => s.vital_type === "weight")
  const active = snap.data?.active_problems ?? []
  const top = [...active].sort((a, b) => episodesOf(b.frequency) - episodesOf(a.frequency))[0]
  const bpValue =
    sysS?.latest != null
      ? `${Math.round(sysS.latest)}/${diaS?.latest != null ? Math.round(diaS.latest) : "–"}`
      : "—"

  const sysSeries = seriesOf(allVitals, "bp_systolic")
  const weightSeries = seriesOf(allVitals, "weight")

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Today's Snapshot</h1>
        <p className="text-sm text-muted-foreground">A longitudinal view of {patient?.name}'s health.</p>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard
          label="Active Problems"
          value={active.length}
          sub={<span className="text-xs text-muted-foreground">tracked now</span>}
          popover={
            active.length ? (
              <div>
                <p className="mb-1.5 text-xs font-medium text-muted-foreground">Currently tracking</p>
                <ul className="space-y-1 text-xs text-foreground">
                  {active.slice(0, 6).map((p, i) => (
                    <li key={i} className="flex items-center justify-between gap-2">
                      <span>{p.name}</span>
                      {p.trend && <span className="text-muted-foreground">{p.trend}</span>}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null
          }
        />
        <StatCard
          label="Latest BP"
          value={bpValue}
          sub={sysS?.trend ? <TrendPill trend={sysS.trend} delta={sysS.delta_pct} /> : null}
          popover={
            <SparkPopover
              title={`Last ${sysSeries.length} systolic readings`}
              values={sysSeries}
              stroke={TONE[trendTone(sysS?.trend)].stroke}
              caption={sysS?.latest != null ? `Latest ${Math.round(sysS.latest)} mmHg` : undefined}
            />
          }
        />
        <StatCard
          label={top ? `${top.name} episodes` : "Recurring"}
          value={top ? episodesOf(top.frequency) : "—"}
          sub={top?.trend ? <TrendPill trend={top.trend} /> : null}
          popover={
            top ? (
              <div className="text-xs">
                <p className="mb-1 font-medium text-muted-foreground">{top.name}</p>
                {top.frequency && <p className="text-foreground">{top.frequency}</p>}
                {top.severity && <p className="text-muted-foreground">Severity: {top.severity}</p>}
                {top.trend && <p className="text-muted-foreground">Trend: {top.trend}</p>}
              </div>
            ) : null
          }
        />
        <StatCard
          label="Weight"
          value={weightS?.latest != null ? `${weightS.latest} kg` : "—"}
          sub={weightS?.trend ? <TrendPill trend={weightS.trend} delta={weightS.delta_pct} /> : null}
          popover={
            <SparkPopover
              title={`Last ${weightSeries.length} weight readings`}
              values={weightSeries}
              stroke={TONE[trendTone(weightS?.trend)].stroke}
              caption={weightS?.latest != null ? `Latest ${weightS.latest} kg` : undefined}
            />
          }
        />
      </div>

      <AlertsPanel patientId={pid} />

      <div className="grid gap-4 md:grid-cols-2">
        <ProblemsCard problems={problems.data ?? []} onSelect={setProblemId} />
        <SuggestedActionsCard pid={pid} />
      </div>

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
          <CardTitle>Health Timeline</CardTitle>
        </CardHeader>
        <CardContent>
          <Timeline
            patientId={pid}
            problems={problems.data ?? []}
            vitals={allVitals}
            summaries={summary}
            onSelectProblem={setProblemId}
          />
        </CardContent>
      </Card>

      {problemId != null && (
        <ProblemTimelineModal patientId={pid} problemId={problemId} onClose={() => setProblemId(null)} />
      )}
    </div>
  )
}
