import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import * as ep from "@/lib/endpoints"
import { Button, Card, CardContent, Input, Select } from "@/components/ui"

const VITALS: { value: string; label: string; unit: string; help: string }[] = [
  { value: "bp_systolic", label: "BP systolic", unit: "mmHg", help: "Top blood-pressure number (pressure as the heart beats). Often around 90–120 mmHg." },
  { value: "bp_diastolic", label: "BP diastolic", unit: "mmHg", help: "Bottom blood-pressure number (pressure between beats). Often around 60–80 mmHg." },
  { value: "heart_rate", label: "Heart rate", unit: "bpm", help: "Resting beats per minute. Often around 60–100 bpm." },
  { value: "weight", label: "Weight", unit: "kg", help: "Body weight — most useful tracked as a trend over time." },
  { value: "blood_glucose", label: "Blood glucose", unit: "mg/dL", help: "Blood sugar. Fasting is often around 70–99 mg/dL." },
  { value: "spo2", label: "SpO₂", unit: "%", help: "Blood-oxygen saturation. Often around 95–100%." },
]

/** Quick numeric reading entry (BP becomes one field in Phase 6). */
export function VitalQuickAdd({ pid }: { pid: number }) {
  const qc = useQueryClient()
  const [vitalType, setVitalType] = useState("bp_systolic")
  const [value, setValue] = useState("")
  const [saved, setSaved] = useState<string | null>(null)
  const meta = VITALS.find((v) => v.value === vitalType)!
  const m = useMutation({
    mutationFn: () => ep.createVital(pid, { vital_type: vitalType, value: Number(value), unit: meta.unit }),
    onSuccess: () => {
      setSaved(`Recorded ${meta.label} ${value} ${meta.unit}`)
      setValue("")
      qc.invalidateQueries()
    },
  })
  return (
    <Card>
      <CardContent className="space-y-2 pt-5">
        <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Quick add a reading</div>
        <div className="flex flex-wrap items-center gap-2">
          <Select value={vitalType} onChange={(e) => setVitalType(e.target.value)} className="w-40">
            {VITALS.map((v) => (
              <option key={v.value} value={v.value}>{v.label}</option>
            ))}
          </Select>
          <Input type="number" placeholder="value" value={value} onChange={(e) => setValue(e.target.value)} className="w-28" />
          <span className="text-sm text-muted-foreground">{meta.unit}</span>
          <Button onClick={() => m.mutate()} disabled={m.isPending || !value}>Save</Button>
          {saved && <span className="text-sm text-teal-700">{saved}</span>}
        </div>
        <p className="text-xs text-muted-foreground">{meta.help}</p>
      </CardContent>
    </Card>
  )
}
