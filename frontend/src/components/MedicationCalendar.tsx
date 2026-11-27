import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Check, ClipboardList } from "lucide-react"
import { api } from "@/lib/api"
import * as ep from "@/lib/endpoints"
import type { DoseSlot } from "@/lib/endpoints"
import { Card, CardContent } from "@/components/ui"
import { cn } from "@/lib/utils"

interface MedEvent {
  id: number; medication_id: number; event_type: "start" | "stop" | "dose_change"; event_date: string
  old_dose: string | null; new_dose: string | null; source: string
}
const getEvents = (pid: number) => api.get<MedEvent[]>(`/patients/${pid}/medications/events`).then((r) => r.data)

const fmtDay = (iso: string) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short" })
const weekday = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { weekday: "short" })

/** Dose tracker: today's checklist, then one row per medicine with the last 14 days of dots. */
export function MedicationCalendar({ patientId }: { patientId: number }) {
  const qc = useQueryClient()
  const cal = useQuery({ queryKey: ["med-calendar", patientId], queryFn: () => ep.getMedCalendar(patientId) })
  const meds = useQuery({ queryKey: ["medications", patientId], queryFn: () => ep.listMedications(patientId) })
  const events = useQuery({ queryKey: ["med-events", patientId], queryFn: () => getEvents(patientId) })
  const toggle = useMutation({
    mutationFn: (s: DoseSlot & { date: string }) => {
      const slot = { scheduled_date: s.date, scheduled_time: s.time }
      return s.taken ? ep.unmarkDose(patientId, s.medication_id, slot) : ep.markDoseTaken(patientId, s.medication_id, slot)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["med-calendar", patientId] }),
  })

  if (cal.isLoading) return <p className="text-sm text-muted-foreground">Loading dose tracker…</p>
  if (cal.isError || !cal.data) return null
  const d = cal.data
  if (d.medication_count === 0) return <p className="text-sm text-muted-foreground">Add a medication to see your dose tracker.</p>

  const byId = new Map((meds.data ?? []).map((m) => [m.id, m]))
  const rows = d.groups.flatMap((g) => g.medications)
  const today = d.days.find((x) => x.is_today)
  const todaySlots = [...(today?.slots ?? [])].sort((a, b) => a.time.localeCompare(b.time))
  const lastChange = (mid: number) =>
    (events.data ?? []).filter((e) => e.medication_id === mid && e.event_type === "dose_change")
      .sort((a, b) => b.event_date.localeCompare(a.event_date))[0]

  return (
    <Card>
      <CardContent className="space-y-5 pt-5">
        {/* Today */}
        {today && (
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Today · {fmtDay(today.date)} · {todaySlots.filter((s) => s.taken).length} of {todaySlots.length} taken
            </p>
            <div className="flex flex-wrap gap-2">
              {todaySlots.map((s) => (
                <button
                  key={`${s.medication_id}-${s.time}`}
                  type="button"
                  disabled={toggle.isPending}
                  onClick={() => toggle.mutate({ ...s, date: today.date })}
                  aria-pressed={s.taken}
                  className={cn(
                    "inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-colors",
                    s.taken ? "border-emerald-300 bg-emerald-50 text-emerald-900" : "border-border hover:bg-muted",
                  )}
                >
                  <span className={cn("flex h-5 w-5 items-center justify-center rounded-full border",
                    s.taken ? "border-emerald-500 bg-emerald-500 text-white" : "border-slate-300 text-transparent")}>
                    <Check className="h-3.5 w-3.5" strokeWidth={3} />
                  </span>
                  <span className="tabular-nums text-muted-foreground">{s.time}</span>
                  <span className="font-medium">{s.name}</span>
                  {s.dose && <span className="text-muted-foreground">{s.dose}</span>}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Last 14 days, one row per medicine */}
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] border-separate border-spacing-0 text-sm">
            <thead>
              <tr className="text-[10px] uppercase tracking-wide text-muted-foreground">
                <th className="pb-2 pr-3 text-left font-semibold">Medicine</th>
                {d.days.map((day) => (
                  <th key={day.date} className={cn("w-8 pb-2 text-center font-semibold", day.is_today && "text-primary")}>
                    <div>{weekday(day.date).slice(0, 2)}</div>
                    <div className="text-[11px] normal-case">{Number(day.date.slice(8, 10))}</div>
                  </th>
                ))}
                <th className="pb-2 pl-3 text-right font-semibold">Taken</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((m) => {
                const med = byId.get(m.id)
                const change = lastChange(m.id)
                const slots = d.days.map((day) => ({ day, slots: day.slots.filter((s) => s.medication_id === m.id) }))
                const due = slots.flatMap((x) => x.slots)
                const taken = due.filter((s) => s.taken).length
                const pct = due.length ? Math.round((taken / due.length) * 100) : 0
                return (
                  <tr key={m.id} className="border-t">
                    <td className="border-t border-border py-2.5 pr-3 align-top">
                      <div className="font-medium text-foreground">
                        {m.name} <span className="font-normal text-muted-foreground">{m.dose}</span>
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {[
                          med?.dose_times?.join(", "),
                          med?.ingredients?.length && med.ingredients.join(" + ").toLowerCase() !== m.name.toLowerCase()
                            ? med.ingredients.join(" + ") : null,
                          med?.prescriber,
                        ].filter(Boolean).join(" · ")}
                      </div>
                      {change && (
                        <div className="text-xs text-muted-foreground">
                          Dose {change.old_dose} → {change.new_dose} on {fmtDay(change.event_date)}
                          {change.source === "visit_note" ? " (visit note)" : ""}
                        </div>
                      )}
                    </td>
                    {slots.map(({ day, slots: ss }) => (
                      <td key={day.date} className={cn("border-t border-border py-2.5 text-center align-middle", day.is_today && "bg-primary/5")}>
                        <div className="flex flex-col items-center gap-1">
                          {ss.map((s) => (
                            <button
                              key={s.time}
                              type="button"
                              disabled={toggle.isPending || !s.markable}
                              onClick={() => toggle.mutate({ ...s, date: day.date })}
                              title={`${fmtDay(day.date)} ${s.time} · ${s.taken ? "taken (click to undo)" : "not marked (click to mark taken)"}`}
                              className={cn(
                                "h-3.5 w-3.5 rounded-full border transition-transform hover:scale-125",
                                s.taken ? "border-emerald-500 bg-emerald-500" : day.is_today ? "border-slate-400 bg-white" : "border-rose-300 bg-rose-50",
                              )}
                            />
                          ))}
                        </div>
                      </td>
                    ))}
                    <td className="border-t border-border py-2.5 pl-3 text-right align-middle tabular-nums">
                      <span className={cn("font-semibold", pct >= 90 ? "text-emerald-700" : pct >= 70 ? "text-amber-700" : "text-rose-700")}>
                        {taken}/{due.length}
                      </span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1.5"><span className="h-3 w-3 rounded-full bg-emerald-500" /> taken</span>
          <span className="inline-flex items-center gap-1.5"><span className="h-3 w-3 rounded-full border border-rose-300 bg-rose-50" /> not marked</span>
          <span className="inline-flex items-center gap-1.5"><span className="h-3 w-3 rounded-full border border-slate-400 bg-white" /> due today</span>
          <span>Click any dot to mark or undo.</span>
        </div>
        <div className="flex items-start gap-2 text-xs text-muted-foreground">
          <ClipboardList className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <p>{d.disclaimer}</p>
        </div>
      </CardContent>
    </Card>
  )
}
