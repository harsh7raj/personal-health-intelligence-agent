import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Pill, Plus, Trash2 } from "lucide-react"
import { useAuth } from "@/lib/auth"
import * as ep from "@/lib/endpoints"
import { AddMedicineDialog } from "@/components/AddMedicineDialog"
import { MedicationCalendar } from "@/components/MedicationCalendar"
import { MedicationIntelligence } from "@/components/MedicationIntelligence"
import { MedicationSafety } from "@/components/MedicationSafety"
import { Button, Card, CardContent } from "@/components/ui"

export default function MedicationsPage() {
  const { patient } = useAuth()
  const pid = patient!.id
  const qc = useQueryClient()
  const meds = useQuery({ queryKey: ["medications", pid], queryFn: () => ep.listMedications(pid) })
  const [adding, setAdding] = useState(false)
  const del = useMutation({
    mutationFn: (mid: number) => ep.deleteMedication(pid, mid),
    onSuccess: () => {
      for (const k of ["medications", "med-intel", "med-calendar", "med-safety", "med-events"]) qc.invalidateQueries({ queryKey: [k, pid] })
    },
  })
  const list = (meds.data ?? []).filter((m) => m.active)

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Medications</h1>
        <Button onClick={() => setAdding(true)}><Plus className="h-4 w-4" /> Add medicine</Button>
      </div>

      <MedicationCalendar patientId={pid} />

      <div>
        <h2 className="mb-3 text-lg font-semibold tracking-tight text-foreground">Your medicines</h2>
        {list.length === 0 ? (
          <Card>
            <CardContent className="flex flex-col items-center gap-2 py-10 text-center">
              <Pill className="h-6 w-6 text-primary" />
              <p className="text-sm text-muted-foreground">No medicines yet. Add one to see it on the calendar and get safety checks.</p>
              <Button onClick={() => setAdding(true)}><Plus className="h-4 w-4" /> Add medicine</Button>
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {list.map((m) => (
              <Card key={m.id}>
                <CardContent className="flex items-start justify-between gap-3 pt-4">
                  <div className="min-w-0 space-y-0.5">
                    <p className="font-semibold text-foreground">{m.name} <span className="font-normal text-muted-foreground">{m.dose}</span></p>
                    {m.ingredients.length > 0 && m.ingredients.join(" + ").toLowerCase() !== m.name.toLowerCase() && (
                      <p className="text-xs text-muted-foreground">{m.ingredients.join(" + ")}</p>
                    )}
                    <p className="text-sm text-muted-foreground">{m.frequency}{m.dose_times.length ? ` · ${m.dose_times.join(", ")}` : ""}</p>
                    <p className="text-xs text-muted-foreground">
                      {[m.purpose, m.prescriber && `${m.prescriber}${m.prescriber_specialty ? ` (${m.prescriber_specialty})` : ""}`,
                        m.started_on && `since ${new Date(`${m.started_on}T12:00:00`).toLocaleDateString(undefined, { month: "short", year: "numeric" })}`]
                        .filter(Boolean).join(" · ")}
                    </p>
                  </div>
                  <Button variant="ghost" className="text-destructive" onClick={() => del.mutate(m.id)} disabled={del.isPending} aria-label={`Remove ${m.name}`}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      <div>
        <h2 className="mb-3 text-lg font-semibold tracking-tight text-foreground">Medication safety</h2>
        <MedicationSafety patientId={pid} />
      </div>

      <div>
        <h2 className="mb-3 text-lg font-semibold tracking-tight text-foreground">About your medicines</h2>
        <MedicationIntelligence patientId={pid} />
      </div>

      <AddMedicineDialog pid={pid} meds={meds.data ?? []} open={adding} onClose={() => setAdding(false)} />
    </div>
  )
}
