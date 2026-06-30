import type { Problem, VitalReading, VitalSummary } from "@/lib/endpoints"
import { TONE, type Tone } from "@/lib/tone"
import { cn } from "@/lib/utils"

interface Ev {
  t: number
  date: Date
  label: string
  tone: Tone
}

function fmt(d: Date): string {
  return d.toLocaleDateString(undefined, { month: "short", year: "numeric" })
}

// Derived purely from existing data — no new backend logic.
function buildEvents(problems: Problem[], vitals: VitalReading[], summaries: VitalSummary[]): Ev[] {
  const ev: Ev[] = []
  for (const p of problems) {
    if (p.first_seen)
      ev.push({ t: +new Date(p.first_seen), date: new Date(p.first_seen), label: `Started tracking ${p.name}`, tone: "flat" })
    if (p.status === "resolved" && p.resolved_at)
      ev.push({ t: +new Date(p.resolved_at), date: new Date(p.resolved_at), label: `${p.name} resolved`, tone: "down" })
  }
  const sys = vitals
    .filter((v) => v.vital_type === "bp_systolic")
    .sort((a, b) => +new Date(a.recorded_at) - +new Date(b.recorded_at))
  if (sys.length) {
    ev.push({
      t: +new Date(sys[0].recorded_at), date: new Date(sys[0].recorded_at),
      label: `First blood pressure reading (${Math.round(sys[0].value)} systolic)`, tone: "flat",
    })
    const ss = summaries.find((s) => s.vital_type === "bp_systolic")
    if (ss?.trend === "rising") {
      const last = sys[sys.length - 1]
      const d = ss.delta_pct != null ? ` (+${Math.round(ss.delta_pct * 100)}%)` : ""
      ev.push({
        t: +new Date(last.recorded_at), date: new Date(last.recorded_at),
        label: `Blood pressure trending upward${d}`, tone: "up",
      })
    }
  }
  return ev.sort((a, b) => a.t - b.t)
}

export function Timeline({
  problems,
  vitals,
  summaries,
}: {
  problems: Problem[]
  vitals: VitalReading[]
  summaries: VitalSummary[]
}) {
  const events = buildEvents(problems, vitals, summaries)
  if (!events.length) return <p className="text-sm text-muted-foreground">No timeline events yet.</p>
  return (
    <ol className="relative ml-2 border-l border-border">
      {events.map((e, i) => (
        <li key={i} className="mb-5 ml-5 last:mb-0">
          <span className={cn("absolute -left-[7px] mt-1 h-3.5 w-3.5 rounded-full ring-4 ring-card", TONE[e.tone].dot)} />
          <time className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{fmt(e.date)}</time>
          <p className="text-sm text-foreground">{e.label}</p>
        </li>
      ))}
    </ol>
  )
}
