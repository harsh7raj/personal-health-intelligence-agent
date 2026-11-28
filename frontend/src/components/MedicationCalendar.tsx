import { useEffect, useMemo, useState } from "react"
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Check, ChevronLeft, ChevronRight, Loader2 } from "lucide-react"
import { api } from "@/lib/api"
import * as ep from "@/lib/endpoints"
import type { CalendarDay, DoseSlot, MedCalendar } from "@/lib/endpoints"
import { cn } from "@/lib/utils"

// Google Calendar-like colours, one per medicine (stable by the backend's color_index).
const PALETTE = [
  { solid: "#039be5", soft: "#e1f5fe", text: "#01579b" }, // peacock
  { solid: "#33b679", soft: "#e8f5e9", text: "#1b5e20" }, // sage
  { solid: "#8e24aa", soft: "#f3e5f5", text: "#4a148c" }, // grape
  { solid: "#f4511e", soft: "#fbe9e7", text: "#bf360c" }, // tangerine
  { solid: "#3f51b5", soft: "#e8eaf6", text: "#1a237e" }, // blueberry
  { solid: "#e67c73", soft: "#fdecea", text: "#8c1d18" }, // flamingo
  { solid: "#0b8043", soft: "#e0f2e9", text: "#0b5130" }, // basil
  { solid: "#f6bf26", soft: "#fff8e1", text: "#7a5b00" }, // banana
]
const color = (i: number) => PALETTE[i % PALETTE.length]
const HOUR_PX = 48

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
const parse = (s: string) => new Date(`${s}T12:00:00`)
const addDays = (d: Date, n: number) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n, 12)
const startOfWeek = (d: Date) => addDays(d, -d.getDay()) // Sunday, like Google Calendar
const hourLabel = (h: number) => (h === 0 ? "12 AM" : h < 12 ? `${h} AM` : h === 12 ? "12 PM" : `${h - 12} PM`)
const minutes = (t: string) => Number(t.slice(0, 2)) * 60 + Number(t.slice(3, 5))

const getCalendar = (pid: number, start: string, end: string) =>
  api.get<MedCalendar>(`/patients/${pid}/medications/calendar`, { params: { start, end } }).then((r) => r.data)

type Toggle = (slot: DoseSlot, date: string) => void

function DoseBlock({ s, date, idx, onToggle, compact }: { s: DoseSlot; date: string; idx: number; onToggle: Toggle; compact?: boolean }) {
  const c = color(idx)
  const missed = !s.taken && s.markable
  const future = !s.markable
  return (
    <button
      type="button"
      onClick={() => s.markable && onToggle(s, date)}
      title={`${s.name} ${s.dose ?? ""} at ${s.time}${s.taken ? " · taken (click to undo)" : future ? " · upcoming" : " · not marked (click to mark taken)"}`}
      className={cn(
        "flex w-full items-center gap-1 overflow-hidden rounded-md px-1.5 text-left text-[11px] leading-tight shadow-sm transition hover:brightness-95",
        compact ? "py-0.5" : "h-full py-1",
        future ? "cursor-default opacity-60" : "cursor-pointer",
      )}
      style={
        s.taken
          ? { background: c.solid, color: "white" }
          : { background: c.soft, color: c.text, border: `1px ${missed ? "dashed" : "solid"} ${c.solid}` }
      }
    >
      {s.taken ? <Check className="h-3 w-3 shrink-0" strokeWidth={3} /> : <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: c.solid }} />}
      <span className="min-w-0 truncate">
        <span className="font-semibold">{s.name}</span>
        {!compact && <span className="opacity-80"> · {s.time}{s.dose ? ` · ${s.dose}` : ""}</span>}
        {compact && <span className="opacity-80"> {s.time}</span>}
      </span>
    </button>
  )
}

function WeekView({ days, colorOf, onToggle }: { days: CalendarDay[]; colorOf: (id: number) => number; onToggle: Toggle }) {
  const times = days.flatMap((d) => d.slots.map((s) => minutes(s.time)))
  const first = Math.max(0, Math.floor((times.length ? Math.min(...times) : 480) / 60) - 1)
  const last = Math.min(24, Math.ceil((times.length ? Math.max(...times) : 1200) / 60) + 2)
  const hours = Array.from({ length: last - first }, (_, i) => first + i)
  const [now, setNow] = useState(new Date())
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 60_000)
    return () => clearInterval(t)
  }, [])
  const nowMin = now.getHours() * 60 + now.getMinutes()

  return (
    <div className="overflow-x-auto">
      <div className="min-w-[760px]">
        {/* Day headers */}
        <div className="grid border-b border-border" style={{ gridTemplateColumns: "56px repeat(7, 1fr)" }}>
          <div />
          {days.map((d) => {
            const dt = parse(d.date)
            return (
              <div key={d.date} className="py-2 text-center">
                <div className={cn("text-[11px] font-medium uppercase tracking-wide", d.is_today ? "text-primary" : "text-muted-foreground")}>
                  {dt.toLocaleDateString(undefined, { weekday: "short" })}
                </div>
                <div className={cn("mx-auto mt-0.5 flex h-9 w-9 items-center justify-center rounded-full text-xl",
                  d.is_today ? "bg-primary text-primary-foreground" : "text-foreground")}>
                  {dt.getDate()}
                </div>
              </div>
            )
          })}
        </div>
        {/* Time grid */}
        <div className="relative grid" style={{ gridTemplateColumns: "56px repeat(7, 1fr)" }}>
          <div>
            {hours.map((h) => (
              <div key={h} className="relative text-right" style={{ height: HOUR_PX }}>
                <span className="absolute -top-2 right-2 text-[10px] text-muted-foreground">{h === first ? "" : hourLabel(h)}</span>
              </div>
            ))}
          </div>
          {days.map((d) => {
            const byTime = new Map<string, DoseSlot[]>()
            d.slots.forEach((s) => byTime.set(s.time, [...(byTime.get(s.time) ?? []), s]))
            return (
              <div key={d.date} className={cn("relative border-l border-border", d.is_today && "bg-primary/[0.03]")}>
                {hours.map((h) => <div key={h} className="border-b border-border/70" style={{ height: HOUR_PX }} />)}
                {[...byTime.entries()].map(([time, group]) => {
                  const top = ((minutes(time) - first * 60) / 60) * HOUR_PX + 1
                  return (
                    <div key={time} className="absolute inset-x-1 flex flex-col gap-0.5" style={{ top, height: Math.max(HOUR_PX * 0.85, group.length * 22) }}>
                      {group.map((s) => (
                        <div key={s.medication_id} className="min-h-0 flex-1">
                          <DoseBlock s={s} date={d.date} idx={colorOf(s.medication_id)} onToggle={onToggle} />
                        </div>
                      ))}
                    </div>
                  )
                })}
                {d.is_today && nowMin >= first * 60 && nowMin <= last * 60 && (
                  <div className="pointer-events-none absolute inset-x-0 z-10" style={{ top: ((nowMin - first * 60) / 60) * HOUR_PX }}>
                    <div className="relative h-0.5 bg-red-500">
                      <span className="absolute -left-1.5 -top-[5px] h-3 w-3 rounded-full bg-red-500" />
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

function MonthView({ days, month, colorOf, onToggle, onOpenWeek }: {
  days: CalendarDay[]; month: number; colorOf: (id: number) => number; onToggle: Toggle; onOpenWeek: (d: Date) => void
}) {
  const weekdays = days.slice(0, 7).map((d) => parse(d.date).toLocaleDateString(undefined, { weekday: "short" }))
  return (
    <div className="overflow-x-auto">
      <div className="min-w-[760px]">
        <div className="grid grid-cols-7 border-b border-border">
          {weekdays.map((w) => <div key={w} className="py-2 text-center text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{w}</div>)}
        </div>
        <div className="grid grid-cols-7">
          {days.map((d) => {
            const dt = parse(d.date)
            const other = dt.getMonth() !== month
            const shown = d.slots.slice(0, 3)
            return (
              <div key={d.date} className={cn("min-h-[112px] border-b border-r border-border p-1", other && "bg-muted/30")}>
                <div className="mb-1 flex justify-center">
                  <span className={cn("flex h-6 min-w-6 items-center justify-center rounded-full px-1 text-xs",
                    d.is_today ? "bg-primary font-semibold text-primary-foreground" : other ? "text-muted-foreground" : "text-foreground")}>
                    {dt.getDate() === 1 ? dt.toLocaleDateString(undefined, { month: "short", day: "numeric" }) : dt.getDate()}
                  </span>
                </div>
                <div className="space-y-0.5">
                  {shown.map((s) => (
                    <DoseBlock key={`${s.medication_id}-${s.time}`} s={s} date={d.date} idx={colorOf(s.medication_id)} onToggle={onToggle} compact />
                  ))}
                  {d.slots.length > 3 && (
                    <button type="button" onClick={() => onOpenWeek(dt)} className="w-full rounded px-1.5 text-left text-[11px] font-medium text-muted-foreground hover:bg-muted">
                      {d.slots.length - 3} more
                    </button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

/** Dose calendar in the style of Google Calendar: week (time grid) and month views. */
export function MedicationCalendar({ patientId }: { patientId: number }) {
  const qc = useQueryClient()
  const [view, setView] = useState<"week" | "month">("week")
  const [anchor, setAnchor] = useState(() => new Date())

  const range = useMemo(() => {
    if (view === "week") {
      const s = startOfWeek(anchor)
      return { start: iso(s), end: iso(addDays(s, 6)) }
    }
    const first = new Date(anchor.getFullYear(), anchor.getMonth(), 1, 12)
    const s = startOfWeek(first)
    return { start: iso(s), end: iso(addDays(s, 41)) }
  }, [view, anchor])

  const key = ["med-calendar", patientId, range.start, range.end]
  const q = useQuery({ queryKey: key, queryFn: () => getCalendar(patientId, range.start, range.end), placeholderData: keepPreviousData })
  const toggle = useMutation({
    mutationFn: ({ s, date }: { s: DoseSlot; date: string }) => {
      const slot = { scheduled_date: date, scheduled_time: s.time }
      return s.taken ? ep.unmarkDose(patientId, s.medication_id, slot) : ep.markDoseTaken(patientId, s.medication_id, slot)
    },
    onMutate: async ({ s, date }) => {  // flip it immediately, like Google Calendar does
      qc.setQueryData<MedCalendar>(key, (old) => old && {
        ...old,
        days: old.days.map((d) => d.date !== date ? d : {
          ...d, slots: d.slots.map((x) => (x.medication_id === s.medication_id && x.time === s.time ? { ...x, taken: !x.taken } : x)),
        }),
      })
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ["med-calendar", patientId] }),
  })
  const onToggle: Toggle = (s, date) => toggle.mutate({ s, date })

  const d = q.data
  const colorIdx = new Map<number, number>()
  d?.groups.forEach((g) => g.medications.forEach((m) => colorIdx.set(m.id, m.color_index)))
  const colorOf = (id: number) => colorIdx.get(id) ?? 0
  const step = (n: number) =>
    setAnchor((a) => (view === "week" ? addDays(a, 7 * n) : new Date(a.getFullYear(), a.getMonth() + n, 1, 12)))
  const title = view === "month"
    ? anchor.toLocaleDateString(undefined, { month: "long", year: "numeric" })
    : (() => {
        const s = startOfWeek(anchor), e = addDays(s, 6)
        const sameMonth = s.getMonth() === e.getMonth()
        return `${s.toLocaleDateString(undefined, { month: "short", day: "numeric" })} – ${e.toLocaleDateString(undefined, sameMonth ? { day: "numeric" } : { month: "short", day: "numeric" })}, ${e.getFullYear()}`
      })()
  const past = d?.days.filter((x) => !x.is_future).flatMap((x) => x.slots) ?? []

  if (d && d.medication_count === 0) {
    return <p className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">Add a medicine to see your dose calendar.</p>
  }

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-2.5">
        <button onClick={() => setAnchor(new Date())} className="rounded-md border border-border px-3 py-1.5 text-sm font-medium hover:bg-muted">Today</button>
        <button onClick={() => step(-1)} aria-label="Previous" className="rounded-full p-1.5 hover:bg-muted"><ChevronLeft className="h-5 w-5" /></button>
        <button onClick={() => step(1)} aria-label="Next" className="rounded-full p-1.5 hover:bg-muted"><ChevronRight className="h-5 w-5" /></button>
        <h3 className="text-lg font-normal text-foreground">{title}</h3>
        {q.isFetching && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
        <div className="ml-auto inline-flex overflow-hidden rounded-md border border-border text-sm">
          {(["week", "month"] as const).map((v) => (
            <button key={v} onClick={() => setView(v)} className={cn("px-3 py-1.5 capitalize", view === v ? "bg-primary/10 font-medium text-primary" : "hover:bg-muted")}>
              {v}
            </button>
          ))}
        </div>
      </div>

      {/* Legend + summary */}
      {d && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 border-b border-border px-4 py-2 text-xs">
          {d.groups.flatMap((g) => g.medications).map((m) => (
            <span key={m.id} className="inline-flex items-center gap-1.5 text-foreground">
              <span className="h-3 w-3 rounded-sm" style={{ background: color(m.color_index).solid }} />
              {m.name} <span className="text-muted-foreground">{m.dose}</span>
            </span>
          ))}
          {past.length > 0 && (
            <span className="ml-auto text-muted-foreground">
              {past.filter((s) => s.taken).length} of {past.length} doses so far marked taken
            </span>
          )}
        </div>
      )}

      {!d ? (
        <p className="flex items-center gap-2 p-6 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Loading…</p>
      ) : view === "week" ? (
        <WeekView days={d.days} colorOf={colorOf} onToggle={onToggle} />
      ) : (
        <MonthView days={d.days} month={anchor.getMonth()} colorOf={colorOf} onToggle={onToggle}
          onOpenWeek={(dt) => { setAnchor(dt); setView("week") }} />
      )}

      <div className="flex flex-wrap items-center gap-4 border-t border-border px-4 py-2 text-[11px] text-muted-foreground">
        <span className="inline-flex items-center gap-1.5"><span className="h-3 w-5 rounded-sm bg-[#039be5]" /> taken</span>
        <span className="inline-flex items-center gap-1.5"><span className="h-3 w-5 rounded-sm border border-dashed border-[#039be5] bg-[#e1f5fe]" /> not marked</span>
        <span className="inline-flex items-center gap-1.5"><span className="h-3 w-5 rounded-sm border border-[#039be5] bg-[#e1f5fe] opacity-60" /> upcoming</span>
        <span>Click a dose to mark it taken, again to undo.</span>
      </div>
    </div>
  )
}
