import { useEffect, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Check, Clock, Loader2, Plus, Search, X } from "lucide-react"
import * as ep from "@/lib/endpoints"
import type { Medication, NameResolution } from "@/lib/endpoints"
import { Button, Dialog, Input, Label } from "@/components/ui"
import { cn } from "@/lib/utils"

// How often -> the frequency text, default times and the repeat interval.
const SCHEDULES = [
  { key: "once", label: "Once a day", frequency: "once daily", times: ["08:00"], interval: 1 },
  { key: "twice", label: "Twice a day", frequency: "twice daily", times: ["08:00", "20:00"], interval: 1 },
  { key: "thrice", label: "Three times a day", frequency: "three times daily", times: ["08:00", "14:00", "20:00"], interval: 1 },
  { key: "night", label: "At bedtime", frequency: "once daily at night", times: ["21:30"], interval: 1 },
  { key: "alternate", label: "Every other day", frequency: "every other day", times: ["08:00"], interval: 2 },
  { key: "weekly", label: "Once a week", frequency: "once a week", times: ["08:00"], interval: 7 },
] as const
type ScheduleKey = (typeof SCHEDULES)[number]["key"]
const PURPOSES = ["Blood pressure", "Blood sugar", "Cholesterol", "Thyroid", "Pain", "Vitamins", "Bones", "Stomach"]

const fmtTime = (t: string) => {
  const [h, m] = t.split(":").map(Number)
  return new Date(2000, 0, 1, h, m).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })
}

export function AddMedicineDialog({ pid, meds, open, onClose }: {
  pid: number; meds: Medication[]; open: boolean; onClose: () => void
}) {
  const qc = useQueryClient()
  const [name, setName] = useState("")
  const [dose, setDose] = useState("")
  const [schedule, setSchedule] = useState<ScheduleKey>("once")
  const [times, setTimes] = useState<string[]>(["08:00"])
  const [started, setStarted] = useState(new Date().toISOString().slice(0, 10))
  const [purpose, setPurpose] = useState("")
  const [prescriber, setPrescriber] = useState("")
  const [specialty, setSpecialty] = useState("")
  const [resolution, setResolution] = useState<NameResolution | null>(null)
  const [confirmed, setConfirmed] = useState<string[] | null>(null)

  const doctors = [...new Map(meds.filter((m) => m.prescriber).map((m) => [m.prescriber!, m.prescriber_specialty])).entries()]
  const sched = SCHEDULES.find((s) => s.key === schedule)!

  useEffect(() => {
    if (!open) return
    setName(""); setDose(""); setSchedule("once"); setTimes(["08:00"]); setStarted(new Date().toISOString().slice(0, 10))
    setPurpose(""); setPrescriber(""); setSpecialty(""); setResolution(null); setConfirmed(null)
  }, [open])

  const lookup = useMutation({
    mutationFn: (n: string) => ep.resolveMedName(pid, n),
    onSuccess: (r) => { setResolution(r); setConfirmed(r.status === "rxnorm" ? r.ingredients : null) },
  })
  const save = useMutation({
    mutationFn: () => ep.createMedication(pid, {
      name: name.trim(), dose: dose.trim() || undefined, frequency: sched.frequency,
      dose_times: [...times].sort(), interval_days: sched.interval, started_on: started,
      purpose: purpose.trim() || undefined, prescriber: prescriber.trim() || undefined,
      prescriber_specialty: specialty.trim() || undefined,
      ...(confirmed && resolution?.status === "suggested" ? { ingredients: confirmed, brand_name: name.trim() } : {}),
    }),
    onSuccess: () => {
      for (const k of ["medications", "med-intel", "med-calendar", "med-safety", "med-events"]) qc.invalidateQueries({ queryKey: [k, pid] })
      onClose()
    },
  })

  const pickSchedule = (k: ScheduleKey) => {
    setSchedule(k)
    setTimes([...SCHEDULES.find((s) => s.key === k)!.times])
  }
  const suggestion = resolution?.status === "suggested" ? resolution.suggestion : []
  const needsConfirm = suggestion.length > 0 && !confirmed
  const ready = name.trim().length > 1 && times.length > 0 && !needsConfirm && !lookup.isPending

  return (
    <Dialog open={open} onClose={onClose} title="Add a medicine">
      <div className="space-y-5 text-sm">
        {/* 1. What */}
        <section className="space-y-2">
          <Label>Medicine</Label>
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-2.5 top-3 h-4 w-4 text-muted-foreground" />
              <Input
                autoFocus
                className="pl-8"
                placeholder="Brand or generic, e.g. Thyronorm 75, Metformin"
                value={name}
                onChange={(e) => { setName(e.target.value); setResolution(null); setConfirmed(null) }}
                onBlur={() => name.trim().length > 1 && !resolution && lookup.mutate(name.trim())}
              />
            </div>
            <Input className="w-32" placeholder="Dose, e.g. 500 mg" value={dose} onChange={(e) => setDose(e.target.value)} />
          </div>
          {lookup.isPending && <p className="flex items-center gap-1.5 text-xs text-muted-foreground"><Loader2 className="h-3 w-3 animate-spin" /> Looking up what's in it…</p>}
          {resolution?.status === "rxnorm" && (
            <p className="flex items-center gap-1.5 text-xs text-emerald-700"><Check className="h-3.5 w-3.5" /> Contains {resolution.ingredients.join(" + ")} (RxNorm)</p>
          )}
          {suggestion.length > 0 && (
            <div className="space-y-2 rounded-lg border border-violet-200 bg-violet-50 p-3 text-violet-900">
              <p>
                <b>{name}</b> isn't in RxNorm. It may contain{" "}
                <b>{suggestion.map((s) => `${s.name}${s.strength ? ` ${s.strength}` : ""}`).join(" + ")}</b> (AI suggestion). Is that right?
              </p>
              {confirmed ? (
                <p className="flex items-center gap-1.5 text-xs font-medium"><Check className="h-3.5 w-3.5" /> Confirmed. Safety checks will use these ingredients.</p>
              ) : (
                <div className="flex gap-2">
                  <Button onClick={() => setConfirmed(suggestion.map((s) => s.name))}>Yes, that's right</Button>
                  <Button variant="ghost" onClick={() => setResolution({ ...resolution!, status: "unknown", suggestion: [] })}>No / not sure</Button>
                </div>
              )}
            </div>
          )}
          {resolution?.status === "unknown" && (
            <p className="text-xs text-muted-foreground">Couldn't identify it, so medicine safety checks may miss it. You can still add it.</p>
          )}
        </section>

        {/* 2. When */}
        <section className="space-y-2">
          <Label>How often</Label>
          <div className="flex flex-wrap gap-1.5">
            {SCHEDULES.map((s) => (
              <button key={s.key} type="button" onClick={() => pickSchedule(s.key)}
                className={cn("rounded-full border px-3 py-1.5 text-xs transition",
                  schedule === s.key ? "border-primary bg-primary text-primary-foreground" : "border-border hover:bg-muted")}>
                {s.label}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <Clock className="h-4 w-4 text-muted-foreground" />
            {times.map((t, i) => (
              <span key={i} className="inline-flex items-center gap-1 rounded-md border border-border pl-2">
                <input type="time" value={t} onChange={(e) => setTimes(times.map((x, j) => (j === i ? e.target.value : x)))}
                  className="bg-transparent py-1 text-sm outline-none" />
                {times.length > 1 && (
                  <button type="button" onClick={() => setTimes(times.filter((_, j) => j !== i))} className="p-1 text-muted-foreground hover:text-foreground" aria-label="Remove time">
                    <X className="h-3.5 w-3.5" />
                  </button>
                )}
              </span>
            ))}
            <button type="button" onClick={() => setTimes([...times, "12:00"])} className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-primary hover:bg-primary/10">
              <Plus className="h-3.5 w-3.5" /> Add a time
            </button>
          </div>
          <div className="flex items-center gap-2">
            <Label className="text-xs font-normal text-muted-foreground">Starting</Label>
            <Input type="date" className="w-44" value={started} onChange={(e) => setStarted(e.target.value)} />
          </div>
        </section>

        {/* 3. Why and who */}
        <section className="space-y-2">
          <Label>What it's for <span className="font-normal text-muted-foreground">(optional)</span></Label>
          <Input placeholder="e.g. Blood pressure" value={purpose} onChange={(e) => setPurpose(e.target.value)} />
          <div className="flex flex-wrap gap-1.5">
            {PURPOSES.map((p) => (
              <button key={p} type="button" onClick={() => setPurpose(p)}
                className={cn("rounded-full border px-2.5 py-1 text-xs", purpose === p ? "border-primary text-primary" : "border-border text-muted-foreground hover:bg-muted")}>
                {p}
              </button>
            ))}
          </div>
          <Label className="block pt-1">Prescribed by <span className="font-normal text-muted-foreground">(optional, helps spot clashes between doctors)</span></Label>
          <div className="flex gap-2">
            <Input placeholder="e.g. Dr. Rao" value={prescriber} onChange={(e) => setPrescriber(e.target.value)} />
            <Input className="w-48" placeholder="Specialty" value={specialty} onChange={(e) => setSpecialty(e.target.value)} />
          </div>
          {doctors.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {doctors.map(([doc, spec]) => (
                <button key={doc} type="button" onClick={() => { setPrescriber(doc); setSpecialty(spec ?? "") }}
                  className={cn("rounded-full border px-2.5 py-1 text-xs", prescriber === doc ? "border-primary text-primary" : "border-border text-muted-foreground hover:bg-muted")}>
                  {doc}{spec ? ` · ${spec}` : ""}
                </button>
              ))}
            </div>
          )}
        </section>

        {/* Preview + save */}
        <div className="rounded-lg bg-muted/60 p-3">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">You're adding</p>
          <p className="mt-0.5 text-foreground">
            <b>{name.trim() || "—"}</b> {dose} · {sched.label.toLowerCase()} at {[...times].sort().map(fmtTime).join(", ")} · from{" "}
            {new Date(`${started}T12:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}
            {prescriber ? ` · ${prescriber}` : ""}
          </p>
        </div>
        <div className="flex items-center justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={() => save.mutate()} disabled={!ready || save.isPending}>
            {save.isPending && <Loader2 className="h-4 w-4 animate-spin" />} Add medicine
          </Button>
        </div>
        {needsConfirm && <p className="text-right text-xs text-violet-700">Confirm or reject the suggested ingredients first.</p>}
        {save.isError && <p className="text-right text-xs text-destructive">Couldn't add it. Please try again.</p>}
      </div>
    </Dialog>
  )
}
