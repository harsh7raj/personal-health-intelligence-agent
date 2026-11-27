import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useAuth } from "@/lib/auth"
import * as ep from "@/lib/endpoints"
import { MedicationIntelligence } from "@/components/MedicationIntelligence"
import { MedicationSafety } from "@/components/MedicationSafety"
import type { NameResolution } from "@/lib/endpoints"
import { MedicationCalendar } from "@/components/MedicationCalendar"
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input } from "@/components/ui"

export default function MedicationsPage() {
  const { patient } = useAuth()
  const pid = patient!.id
  const qc = useQueryClient()
  const meds = useQuery({ queryKey: ["medications", pid], queryFn: () => ep.listMedications(pid) })
  const [name, setName] = useState("")
  const [dose, setDose] = useState("")
  const [frequency, setFrequency] = useState("")
  const [purpose, setPurpose] = useState("")
  const [doseTimes, setDoseTimes] = useState("")
  const [prescriber, setPrescriber] = useState("")
  const [specialty, setSpecialty] = useState("")
  // What's in it: RxNorm's answer, or an AI suggestion the user must confirm before saving.
  const [resolution, setResolution] = useState<NameResolution | null>(null)
  const [confirmed, setConfirmed] = useState<string[] | null>(null)
  const resolve = useMutation({
    mutationFn: (n: string) => ep.resolveMedName(pid, n),
    onSuccess: (r) => {
      setResolution(r)
      setConfirmed(r.status === "rxnorm" ? r.ingredients : null)
    },
  })
  const invalidateMeds = () => {
    for (const key of ["medications", "med-intel", "med-calendar", "med-safety"]) qc.invalidateQueries({ queryKey: [key, pid] })
  }

  const add = useMutation({
    mutationFn: () => {
      const times = doseTimes
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean)
      return ep.createMedication(pid, {
        name,
        dose: dose || undefined,
        frequency: frequency || undefined,
        purpose: purpose || undefined,
        dose_times: times.length ? times : undefined,
        prescriber: prescriber || undefined,
        prescriber_specialty: specialty || undefined,
        ...(confirmed && resolution?.status === "suggested" ? { ingredients: confirmed, brand_name: name } : {}),
      })
    },
    onSuccess: () => {
      setName("")
      setDose("")
      setFrequency("")
      setPurpose("")
      setDoseTimes("")
      setPrescriber("")
      setSpecialty("")
      setResolution(null)
      setConfirmed(null)
      invalidateMeds()
    },
  })
  const del = useMutation({
    mutationFn: (mid: number) => ep.deleteMedication(pid, mid),
    onSuccess: invalidateMeds,
  })
  const suggestion = resolution?.status === "suggested" ? resolution.suggestion : []
  const list = meds.data ?? []

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight text-foreground">Medications</h1>

      <div>
        <h2 className="mb-3 text-lg font-semibold tracking-tight text-foreground">Dose tracker</h2>
        <MedicationCalendar patientId={pid} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Add medication</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex flex-wrap gap-2">
            <Input
              className="min-w-[140px] flex-1"
              placeholder="name (brand or generic, e.g. Thyronorm 75)"
              value={name}
              onChange={(e) => {
                setName(e.target.value)
                setResolution(null)
                setConfirmed(null)
              }}
              onBlur={() => name.trim() && resolve.mutate(name.trim())}
            />
            <Input className="w-32" placeholder="dose" value={dose} onChange={(e) => setDose(e.target.value)} />
            <Input className="w-44" placeholder="frequency (e.g. twice daily)" value={frequency} onChange={(e) => setFrequency(e.target.value)} />
          </div>
          <div className="flex flex-wrap gap-2">
            <Input className="min-w-[140px] flex-1" placeholder="purpose (e.g. eye strain)" value={purpose} onChange={(e) => setPurpose(e.target.value)} />
            <Input className="w-56" placeholder="dose times, e.g. 08:00, 20:00 (optional)" value={doseTimes} onChange={(e) => setDoseTimes(e.target.value)} />
          </div>
          <div className="flex flex-wrap gap-2">
            <Input className="min-w-[140px] flex-1" placeholder="prescribed by (e.g. Dr. Rao), optional" value={prescriber} onChange={(e) => setPrescriber(e.target.value)} />
            <Input className="w-56" placeholder="specialty (e.g. endocrinology), optional" value={specialty} onChange={(e) => setSpecialty(e.target.value)} />
            <Button onClick={() => add.mutate()} disabled={add.isPending || !name}>
              Add
            </Button>
          </div>
          {resolve.isPending && <p className="text-xs text-muted-foreground">Looking up what's in it…</p>}
          {resolution?.status === "rxnorm" && (
            <p className="text-xs text-muted-foreground">Contains {resolution.ingredients.join(" + ")} (RxNorm).</p>
          )}
          {suggestion.length > 0 && (
            <div className="space-y-2 rounded-md border border-violet-200 bg-violet-50 p-3 text-sm text-violet-900">
              <p>
                {name} isn't in RxNorm. It may contain{" "}
                <b>{suggestion.map((s) => `${s.name}${s.strength ? ` ${s.strength}` : ""}`).join(" + ")}</b>{" "}
                (AI suggestion{suggestion.every((s) => s.verified) ? ", each found in RxNorm" : ""}). Is that right? Check the strip or ask your pharmacist.
              </p>
              {confirmed ? (
                <p className="text-xs font-medium">Confirmed. Safety checks will use these ingredients.</p>
              ) : (
                <div className="flex gap-2">
                  <Button onClick={() => setConfirmed(suggestion.map((s) => s.name))}>Yes, that's right</Button>
                  <Button variant="ghost" onClick={() => setResolution(null)}>No / not sure</Button>
                </div>
              )}
            </div>
          )}
          {(resolution?.status === "unknown" || resolution?.status === "offline") && (
            <p className="text-xs text-muted-foreground">
              Couldn't identify this medicine{resolution.status === "offline" ? " (lookup offline)" : ""}. It will be saved, but safety checks may miss it.
            </p>
          )}
          <p className="text-xs text-muted-foreground">
            Leave dose times blank to auto-fill from the frequency — you can adjust them later.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Current medications</CardTitle>
        </CardHeader>
        <CardContent>
          {list.length === 0 ? (
            <p className="text-sm text-muted-foreground">No medications recorded.</p>
          ) : (
            <ul className="divide-y divide-border">
              {list.map((m) => (
                <li key={m.id} className="flex items-center justify-between gap-3 py-2.5 text-sm">
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-foreground">{m.name}</span>
                    {m.ingredients.length > 0 && m.ingredients.join(" + ").toLowerCase() !== m.name.toLowerCase() && (
                      <span className="text-xs text-muted-foreground">({m.ingredients.join(" + ")})</span>
                    )}
                    {m.dose && <span className="text-muted-foreground">{m.dose}</span>}
                    {m.frequency && <span className="text-muted-foreground">· {m.frequency}</span>}
                    {m.purpose && <Badge className="border-transparent bg-slate-100 text-slate-600">{m.purpose}</Badge>}
                    {m.prescriber && <span className="text-muted-foreground">· {m.prescriber}{m.prescriber_specialty ? ` (${m.prescriber_specialty})` : ""}</span>}
                    <Badge className={m.active ? "border-transparent bg-secondary text-secondary-foreground" : "border-transparent bg-slate-100 text-slate-500"}>
                      {m.active ? "active" : "inactive"}
                    </Badge>
                  </span>
                  <Button variant="ghost" className="text-destructive" onClick={() => del.mutate(m.id)} disabled={del.isPending}>
                    Remove
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <div>
        <h2 className="mb-3 text-lg font-semibold tracking-tight text-foreground">Medication safety</h2>
        <MedicationSafety patientId={pid} />
      </div>

      <div>
        <h2 className="mb-3 text-lg font-semibold tracking-tight text-foreground">About your medicines</h2>
        <MedicationIntelligence patientId={pid} />
      </div>
    </div>
  )
}
