import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useAuth } from "@/lib/auth"
import * as ep from "@/lib/endpoints"
import { IntakeBox } from "@/components/IntakeBox"
import { Button, Card, CardContent, CardHeader, CardTitle, Input, Select } from "@/components/ui"

function useRefreshAll() {
  const qc = useQueryClient()
  return () => qc.invalidateQueries()
}

function VitalForm({ pid }: { pid: number }) {
  const refresh = useRefreshAll()
  const [vitalType, setVitalType] = useState("bp_systolic")
  const [value, setValue] = useState("")
  const [unit, setUnit] = useState("")
  const [msg, setMsg] = useState("")
  const m = useMutation({
    mutationFn: () =>
      ep.createVital(pid, { vital_type: vitalType, value: Number(value), unit: unit || undefined }),
    onSuccess: () => {
      setMsg("Saved ✓")
      setValue("")
      refresh()
    },
  })
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Add vital reading</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <Select value={vitalType} onChange={(e) => setVitalType(e.target.value)}>
          <option value="bp_systolic">BP systolic</option>
          <option value="bp_diastolic">BP diastolic</option>
          <option value="heart_rate">Heart rate</option>
          <option value="weight">Weight</option>
          <option value="blood_glucose">Blood glucose</option>
          <option value="spo2">SpO2</option>
        </Select>
        <Input type="number" placeholder="value" value={value} onChange={(e) => setValue(e.target.value)} />
        <Input placeholder="unit (optional)" value={unit} onChange={(e) => setUnit(e.target.value)} />
        <Button onClick={() => m.mutate()} disabled={m.isPending || !value}>
          Save
        </Button>{" "}
        {msg && <span className="text-sm text-green-600">{msg}</span>}
      </CardContent>
    </Card>
  )
}

function MedicationForm({ pid }: { pid: number }) {
  const refresh = useRefreshAll()
  const [name, setName] = useState("")
  const [dose, setDose] = useState("")
  const [frequency, setFrequency] = useState("")
  const [msg, setMsg] = useState("")
  const m = useMutation({
    mutationFn: () => ep.createMedication(pid, { name, dose: dose || undefined, frequency: frequency || undefined }),
    onSuccess: () => {
      setMsg("Saved ✓")
      setName("")
      setDose("")
      setFrequency("")
      refresh()
    },
  })
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Add medication</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <Input placeholder="name" value={name} onChange={(e) => setName(e.target.value)} />
        <Input placeholder="dose (optional)" value={dose} onChange={(e) => setDose(e.target.value)} />
        <Input placeholder="frequency (optional)" value={frequency} onChange={(e) => setFrequency(e.target.value)} />
        <Button onClick={() => m.mutate()} disabled={m.isPending || !name}>
          Save
        </Button>{" "}
        {msg && <span className="text-sm text-green-600">{msg}</span>}
      </CardContent>
    </Card>
  )
}

function ReportUpload({ pid }: { pid: number }) {
  const [file, setFile] = useState<File | null>(null)
  const [reportType, setReportType] = useState("")
  const [msg, setMsg] = useState("")
  const m = useMutation({
    mutationFn: () => ep.uploadReport(pid, file!, reportType || undefined),
    onSuccess: () => {
      setMsg("Uploaded ✓")
      setFile(null)
    },
  })
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Upload lab report</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <Input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <Input placeholder="report type (optional)" value={reportType} onChange={(e) => setReportType(e.target.value)} />
        <Button onClick={() => m.mutate()} disabled={m.isPending || !file}>
          Upload
        </Button>{" "}
        {msg && <span className="text-sm text-green-600">{msg}</span>}
      </CardContent>
    </Card>
  )
}

export default function LogPage() {
  const { patient } = useAuth()
  const pid = patient!.id
  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Log a health update</h1>
      <IntakeBox patientId={pid} />
      <p className="text-sm text-muted-foreground">
        The free-text box above runs the full AI pipeline (parsing → reasoning → snapshot). The forms below
        record structured data directly.
      </p>
      <div className="grid gap-4 md:grid-cols-3">
        <VitalForm pid={pid} />
        <MedicationForm pid={pid} />
        <ReportUpload pid={pid} />
      </div>
    </div>
  )
}
