import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Check, ClipboardList } from "lucide-react"
import * as ep from "@/lib/endpoints"
import type { CalendarDay, DoseSlot } from "@/lib/endpoints"
import { Card, CardContent } from "@/components/ui"
import { cn } from "@/lib/utils"

// Distinct per-medication colors, indexed by the backend's stable color_index so each
// medication keeps the same color across the legend and every slot in the grid.
const MED_COLORS = [
  { dot: "bg-rose-500", chip: "bg-rose-100 text-rose-700" },
  { dot: "bg-sky-500", chip: "bg-sky-100 text-sky-700" },
  { dot: "bg-emerald-500", chip: "bg-emerald-100 text-emerald-700" },
  { dot: "bg-amber-500", chip: "bg-amber-100 text-amber-700" },
  { dot: "bg-violet-500", chip: "bg-violet-100 text-violet-700" },
  { dot: "bg-cyan-500", chip: "bg-cyan-100 text-cyan-700" },
  { dot: "bg-fuchsia-500", chip: "bg-fuchsia-100 text-fuchsia-700" },
  { dot: "bg-lime-500", chip: "bg-lime-100 text-lime-700" },
  { dot: "bg-orange-500", chip: "bg-orange-100 text-orange-700" },
  { dot: "bg-teal-500", chip: "bg-teal-100 text-teal-700" },
]
const colorFor = (i: number) => MED_COLORS[i % MED_COLORS.length]

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
// Monday-based weekday index (0=Mon … 6=Sun) for a yyyy-mm-dd string.
const mondayIndex = (iso: string) => (new Date(iso + "T00:00:00").getDay() + 6) % 7

export function MedicationCalendar({ patientId }: { patientId: number }) {
  const qc = useQueryClient()
  const q = useQuery({
    queryKey: ["med-calendar", patientId],
    queryFn: () => ep.getMedCalendar(patientId),
  })
  const colorIndex = new Map<number, number>()
  q.data?.groups.forEach((g) => g.medications.forEach((m) => colorIndex.set(m.id, m.color_index)))

  const toggle = useMutation({
    mutationFn: (s: DoseSlot & { date: string }) => {
      const slot = { scheduled_date: s.date, scheduled_time: s.time }
      return s.taken
        ? ep.unmarkDose(patientId, s.medication_id, slot)
        : ep.markDoseTaken(patientId, s.medication_id, slot)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["med-calendar", patientId] }),
  })

  if (q.isLoading) return <p className="text-sm text-muted-foreground">Loading dose tracker…</p>
  if (q.isError || !q.data) return null
  const d = q.data
  if (d.medication_count === 0)
    return <p className="text-sm text-muted-foreground">Add a medication to see your dose schedule.</p>

  // Pad the 14-day window out to whole Mon–Sun weeks for a real calendar grid.
  const lead = mondayIndex(d.days[0].date)
  const cells: (CalendarDay | null)[] = [
    ...Array(lead).fill(null),
    ...d.days,
    ...Array((7 - ((lead + d.days.length) % 7)) % 7).fill(null),
  ]

  return (
    <Card>
      <CardContent className="space-y-4 pt-5">
        {/* Legend: medications grouped by purpose, color-coded. */}
        <div className="flex flex-wrap gap-x-5 gap-y-2">
          {d.groups.map((g) => (
            <div key={g.purpose} className="min-w-0">
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                {g.purpose}
              </p>
              <div className="flex flex-wrap gap-1.5">
                {g.medications.map((m) => (
                  <span
                    key={m.id}
                    title={m.dose ?? undefined}
                    className={cn(
                      "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium",
                      colorFor(m.color_index).chip,
                    )}
                  >
                    <span className={cn("h-2 w-2 rounded-full", colorFor(m.color_index).dot)} />
                    {m.name}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Calendar grid. */}
        <div className="overflow-x-auto">
          <div className="min-w-[760px]">
            <div className="grid grid-cols-7 text-center text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              {WEEKDAYS.map((w) => (
                <div key={w} className="pb-1">
                  {w}
                </div>
              ))}
            </div>
            <div className="grid grid-cols-7 gap-px overflow-hidden rounded-lg bg-border">
              {cells.map((day, i) =>
                day ? (
                  <DayCell
                    key={day.date}
                    day={day}
                    colorIndex={colorIndex}
                    onToggle={(s) => toggle.mutate({ ...s, date: day.date })}
                    pending={toggle.isPending}
                  />
                ) : (
                  <div key={`b${i}`} className="min-h-[120px] bg-muted/30" />
                ),
              )}
            </div>
          </div>
        </div>

        <div className="flex items-start gap-2 text-xs text-muted-foreground">
          <ClipboardList className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <p>{d.disclaimer}</p>
        </div>
      </CardContent>
    </Card>
  )
}

function DayCell({
  day,
  colorIndex,
  onToggle,
  pending,
}: {
  day: CalendarDay
  colorIndex: Map<number, number>
  onToggle: (s: DoseSlot) => void
  pending: boolean
}) {
  const dayNum = Number(day.date.slice(8, 10))
  const takenCount = day.slots.filter((s) => s.taken).length
  return (
    <div
      className={cn(
        "min-h-[120px] bg-card p-1.5",
        day.is_today && "ring-2 ring-inset ring-primary",
        day.is_future && "bg-card/60",
      )}
    >
      <div className="mb-1 flex items-center justify-between">
        <span
          className={cn(
            "flex h-5 min-w-5 items-center justify-center rounded-full px-1 text-xs font-semibold",
            day.is_today ? "bg-primary text-primary-foreground" : "text-foreground",
          )}
        >
          {dayNum}
        </span>
        {day.slots.length > 0 && !day.is_future && (
          <span className="text-[10px] tabular-nums text-muted-foreground">
            {takenCount}/{day.slots.length}
          </span>
        )}
      </div>
      <ul className="space-y-0.5">
        {day.slots.map((s, i) => {
          const c = colorFor(colorIndex.get(s.medication_id) ?? 0)
          const title = [s.name, s.dose, s.timing].filter(Boolean).join(" · ")
          if (!s.markable) {
            return (
              <li
                key={i}
                title={title}
                className="flex items-center gap-1 rounded px-1 py-0.5 text-[11px] text-muted-foreground"
              >
                <span className={cn("h-2 w-2 shrink-0 rounded-full opacity-60", c.dot)} />
                <span className="tabular-nums">{s.time}</span>
                <span className="truncate">{s.name}</span>
              </li>
            )
          }
          return (
            <li key={i}>
              <button
                type="button"
                disabled={pending}
                onClick={() => onToggle(s)}
                aria-pressed={s.taken}
                title={`${title}${s.taken ? " — taken (click to undo)" : " — click to mark taken"}`}
                className={cn(
                  "flex w-full items-center gap-1 rounded px-1 py-0.5 text-left text-[11px] transition-colors hover:bg-muted disabled:opacity-50",
                  s.taken && "bg-emerald-50",
                )}
              >
                <span className={cn("h-2 w-2 shrink-0 rounded-full", c.dot)} />
                <span className="tabular-nums text-muted-foreground">{s.time}</span>
                <span className={cn("min-w-0 flex-1 truncate", s.taken && "text-muted-foreground line-through")}>
                  {s.name}
                </span>
                <span
                  className={cn(
                    "flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full border",
                    s.taken
                      ? "border-emerald-500 bg-emerald-500 text-white"
                      : "border-slate-300 text-transparent",
                  )}
                >
                  <Check className="h-2.5 w-2.5" strokeWidth={3} />
                </span>
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
