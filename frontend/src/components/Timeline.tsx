import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import * as ep from "@/lib/endpoints"
import type { Problem, VitalReading, VitalSummary } from "@/lib/endpoints"
import { Badge, Dialog } from "@/components/ui"
import { TONE, severityTone, type Tone } from "@/lib/tone"
import { cn } from "@/lib/utils"

interface Ev {
  t: number
  iso: string // UTC calendar date (YYYY-MM-DD); the window END / anchor
  // For derived "span" events (e.g. a trend), the evidence window START — the
  // first contributing reading's day. Point-in-time events leave this undefined
  // and use a narrow ±1d window instead.
  start?: string
  date: Date
  label: string
  tone: Tone
  // Set on problem-anchored points (started/resolved) → click opens that
  // problem's focused sub-timeline instead of the generic date-detail.
  problemId?: number
}

function fmtMonth(d: Date): string {
  return d.toLocaleDateString(undefined, { month: "short", year: "numeric" })
}
function fmtDay(d: Date): string {
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })
}
function fmtDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  })
}
function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10)
}

// Derived from existing data — places the clickable points. The FULL context for a
// point is fetched on click from the backend (timeline/{date}/detail), not from here.
function buildEvents(problems: Problem[], vitals: VitalReading[], summaries: VitalSummary[]): Ev[] {
  const ev: Ev[] = []
  for (const p of problems) {
    if (p.first_seen) {
      const d = new Date(p.first_seen)
      ev.push({ t: +d, iso: isoDate(d), date: d, label: `Started tracking ${p.name}`, tone: "flat", problemId: p.id })
    }
    if (p.status === "resolved" && p.resolved_at) {
      const d = new Date(p.resolved_at)
      ev.push({ t: +d, iso: isoDate(d), date: d, label: `${p.name} resolved`, tone: "down", problemId: p.id })
    }
  }
  const sys = vitals
    .filter((v) => v.vital_type === "bp_systolic")
    .sort((a, b) => +new Date(a.recorded_at) - +new Date(b.recorded_at))
  if (sys.length) {
    const d0 = new Date(sys[0].recorded_at)
    ev.push({
      t: +d0, iso: isoDate(d0), date: d0,
      label: `First blood pressure reading (${Math.round(sys[0].value)} systolic)`, tone: "flat",
    })
    const ss = summaries.find((s) => s.vital_type === "bp_systolic")
    if (ss?.trend === "rising") {
      const last = sys[sys.length - 1]
      const dl = new Date(last.recorded_at)
      const d = ss.delta_pct != null ? ` (+${Math.round(ss.delta_pct * 100)}%)` : ""
      // Trend = a SPAN event: its evidence window is the whole first→last reading
      // period that produced the trend, not a single day around the anchor.
      ev.push({
        t: +dl, iso: isoDate(dl), start: isoDate(d0), date: dl,
        label: `Blood pressure trending upward${d}`, tone: "up",
      })
    }
  }
  return ev.sort((a, b) => a.t - b.t)
}

function Section({ title, count, children }: { title: string; count: number; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-2 flex items-center gap-2">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</h4>
        <span className="text-xs text-muted-foreground">· {count}</span>
      </div>
      {count === 0 ? <p className="text-sm text-muted-foreground">None recorded.</p> : children}
    </div>
  )
}

function structuredSummary(s: Record<string, unknown>): string {
  const parts = Object.entries(s)
    .filter(([, v]) => v != null && v !== "" && typeof v !== "object")
    .map(([k, v]) => `${k}: ${v}`)
  return parts.join(" · ")
}

function DetailModal({ patientId, ev, onClose }: { patientId: number; ev: Ev; onClose: () => void }) {
  const q = useQuery({
    queryKey: ["timeline-detail", patientId, ev.iso, ev.start ?? null],
    queryFn: () => ep.getTimelineDetail(patientId, ev.iso, 1, ev.start),
  })
  const d = q.data
  const subtitle =
    ev.start && ev.start !== ev.iso
      ? `${fmtDay(new Date(ev.start))} – ${fmtDay(ev.date)} · full context`
      : `${fmtDay(ev.date)} · full context`
  return (
    <Dialog open onClose={onClose} title={
      <div className="flex flex-col">
        <span>{ev.label}</span>
        <span className="text-xs font-normal text-muted-foreground">{subtitle}</span>
      </div>
    }>
      {q.isLoading && <p className="text-sm text-muted-foreground">Assembling context…</p>}
      {q.isError && <p className="text-sm text-destructive">Could not load detail.</p>}
      {d && (
        <div className="space-y-5">
          <Section title="What was logged" count={d.entries.length}>
            <ul className="space-y-3">
              {d.entries.map((e) => (
                <li key={e.id} className="rounded-lg border bg-background/50 p-3">
                  <div className="mb-1 flex items-center gap-2">
                    <Badge className="border-border bg-muted/50 text-muted-foreground">{e.type}</Badge>
                    {e.source && <span className="text-xs text-muted-foreground">via {e.source}</span>}
                    <span className="ml-auto text-xs text-muted-foreground">{fmtDateTime(e.created_at)}</span>
                  </div>
                  {e.raw_text ? (
                    <p className="text-sm text-foreground">“{e.raw_text}”</p>
                  ) : (
                    <p className="text-sm text-muted-foreground">{structuredSummary(e.structured) || "—"}</p>
                  )}
                </li>
              ))}
            </ul>
          </Section>

          <Section title="Vitals & symptoms recorded" count={d.vital_readings.length}>
            <ul className="space-y-1.5">
              {d.vital_readings.map((r) => (
                <li key={r.id} className="flex items-center justify-between gap-3 text-sm">
                  <span className="text-foreground">
                    <span className="font-medium">{r.vital_type.replace(/_/g, " ")}</span>{" "}
                    {Math.round(r.value * 10) / 10}
                    {r.unit ? ` ${r.unit}` : ""}
                  </span>
                  <span className="text-xs text-muted-foreground">{fmtDateTime(r.recorded_at)}</span>
                </li>
              ))}
            </ul>
          </Section>

          <Section title="AI observations" count={d.observations.length}>
            <ul className="space-y-2">
              {d.observations.map((o) => (
                <li key={o.id} className="flex gap-2 text-sm">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                  <span className="text-foreground">{o.text}</span>
                </li>
              ))}
            </ul>
          </Section>

          <Section title="Alerts" count={d.alerts.length}>
            <ul className="space-y-1.5">
              {d.alerts.map((a) => {
                const c = TONE[severityTone(a.severity)]
                return (
                  <li key={a.id} className="flex items-center gap-2 text-sm">
                    <span className={cn("rounded px-1.5 py-0.5 text-xs font-semibold", c.chip)}>{a.severity ?? "info"}</span>
                    <span className="text-foreground">{a.message}</span>
                    <span className="ml-auto text-xs text-muted-foreground">{fmtDateTime(a.created_at)}</span>
                  </li>
                )
              })}
            </ul>
          </Section>
        </div>
      )}
    </Dialog>
  )
}

export function Timeline({
  patientId,
  problems,
  vitals,
  summaries,
  onSelectProblem,
}: {
  patientId: number
  problems: Problem[]
  vitals: VitalReading[]
  summaries: VitalSummary[]
  onSelectProblem?: (problemId: number) => void
}) {
  const [selected, setSelected] = useState<Ev | null>(null)
  const events = buildEvents(problems, vitals, summaries)
  if (!events.length) return <p className="text-sm text-muted-foreground">No timeline events yet.</p>
  const handle = (e: Ev) => {
    if (e.problemId != null && onSelectProblem) onSelectProblem(e.problemId)
    else setSelected(e)
  }
  return (
    <>
      <div className="overflow-x-auto pb-1">
        <div className="relative flex min-w-max items-start gap-2 px-1 pt-1">
          <div className="absolute left-3 right-3 top-[30px] h-px bg-border" />
          {events.map((e, i) => (
            <button
              key={i}
              onClick={() => handle(e)}
              className="group relative flex w-36 shrink-0 cursor-pointer flex-col items-center text-center"
            >
              <time className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{fmtMonth(e.date)}</time>
              <span className={cn("my-1.5 h-3.5 w-3.5 rounded-full ring-4 ring-card transition-transform group-hover:scale-125", TONE[e.tone].dot)} />
              <span className="text-xs leading-snug text-foreground group-hover:text-primary">{e.label}</span>
              <span className="mt-1 text-[10px] text-muted-foreground opacity-0 transition group-hover:opacity-100">
                {e.problemId != null ? "view problem" : "click for detail"}
              </span>
            </button>
          ))}
        </div>
      </div>
      {selected && <DetailModal patientId={patientId} ev={selected} onClose={() => setSelected(null)} />}
    </>
  )
}
