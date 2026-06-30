import { useQuery } from "@tanstack/react-query"
import * as ep from "@/lib/endpoints"
import type { ProblemTimelinePoint } from "@/lib/endpoints"
import { Badge, Dialog } from "@/components/ui"
import { TONE, severityTone, trendTone, type Tone } from "@/lib/tone"
import { cn } from "@/lib/utils"

function fmtDay(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })
}

const KIND_TONE: Record<ProblemTimelinePoint["kind"], Tone> = {
  first_seen: "flat",
  episode: "flat",
  reading: "flat",
  trend_change: "up",
  resolved: "down",
}

function statusChip(status: string): string {
  if (status === "resolved") return TONE.down.chip
  if (status === "managed") return TONE.flat.chip
  return TONE.up.chip
}

export function ProblemTimelineModal({
  patientId,
  problemId,
  onClose,
}: {
  patientId: number
  problemId: number
  onClose: () => void
}) {
  const q = useQuery({
    queryKey: ["problem-timeline", patientId, problemId],
    queryFn: () => ep.getProblemTimeline(patientId, problemId),
  })
  const d = q.data
  const pr = d?.problem

  return (
    <Dialog
      open
      onClose={onClose}
      title={
        <div className="flex flex-col">
          <span className="capitalize">{pr?.name ?? "Problem"} timeline</span>
          {pr && (
            <span className="text-xs font-normal text-muted-foreground">
              {pr.first_seen ? fmtDay(pr.first_seen) : "—"}
              {" – "}
              {pr.resolved_at ? fmtDay(pr.resolved_at) : pr.last_seen ? fmtDay(pr.last_seen) : "ongoing"}
              {" · this problem only"}
            </span>
          )}
        </div>
      }
    >
      {q.isLoading && <p className="text-sm text-muted-foreground">Assembling this problem's history…</p>}
      {q.isError && <p className="text-sm text-destructive">Could not load problem timeline.</p>}
      {d && pr && (
        <div className="space-y-4">
          {/* Header facts (current state — NOT a dated event) */}
          <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-background/50 p-3 text-xs">
            <Badge className={cn("border-transparent", statusChip(pr.status))}>{pr.status}</Badge>
            {pr.frequency && <span className="text-foreground">{pr.frequency}</span>}
            {pr.trend && (
              <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-semibold", TONE[trendTone(pr.trend)].chip)}>
                {TONE[trendTone(pr.trend)].arrow} {pr.trend}
              </span>
            )}
            {pr.severity && <span className="text-muted-foreground">latest severity: {pr.severity}</span>}
          </div>

          {d.points.length === 0 ? (
            <p className="text-sm text-muted-foreground">No recorded evidence for this problem yet.</p>
          ) : (
            <ol className="relative ml-2 border-l border-border">
              {d.points.map((p, i) => {
                const c = TONE[p.severity ? severityTone(p.severity) : KIND_TONE[p.kind]]
                return (
                  <li key={i} className="mb-4 ml-5 last:mb-0">
                    <span className={cn("absolute -left-[7px] mt-1 h-3.5 w-3.5 rounded-full ring-4 ring-card", c.dot)} />
                    <div className="flex items-center gap-2">
                      <time className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{fmtDay(p.date)}</time>
                      {p.severity && (
                        <span className={cn("rounded px-1.5 py-0.5 text-[10px] font-semibold", TONE[severityTone(p.severity)].chip)}>
                          {p.severity}
                        </span>
                      )}
                      {p.kind === "trend_change" && (
                        <span className={cn("rounded px-1.5 py-0.5 text-[10px] font-semibold", TONE.up.chip)}>trend</span>
                      )}
                      {p.kind === "resolved" && (
                        <span className={cn("rounded px-1.5 py-0.5 text-[10px] font-semibold", TONE.down.chip)}>resolved</span>
                      )}
                    </div>
                    <p className="text-sm capitalize text-foreground">{p.label}</p>
                    {p.detail && <p className="mt-0.5 text-sm normal-case text-muted-foreground">“{p.detail}”</p>}
                  </li>
                )
              })}
            </ol>
          )}
        </div>
      )}
    </Dialog>
  )
}
