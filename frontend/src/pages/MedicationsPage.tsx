import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useAuth } from "@/lib/auth"
import * as ep from "@/lib/endpoints"
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input } from "@/components/ui"

export default function MedicationsPage() {
  const { patient } = useAuth()
  const pid = patient!.id
  const qc = useQueryClient()
  const meds = useQuery({ queryKey: ["medications", pid], queryFn: () => ep.listMedications(pid) })
  const [name, setName] = useState("")
  const [dose, setDose] = useState("")
  const [frequency, setFrequency] = useState("")

  const add = useMutation({
    mutationFn: () => ep.createMedication(pid, { name, dose: dose || undefined, frequency: frequency || undefined }),
    onSuccess: () => {
      setName("")
      setDose("")
      setFrequency("")
      qc.invalidateQueries({ queryKey: ["medications", pid] })
    },
  })
  const del = useMutation({
    mutationFn: (mid: number) => ep.deleteMedication(pid, mid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["medications", pid] }),
  })
  const list = meds.data ?? []

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight text-foreground">Medications</h1>

      <Card>
        <CardHeader>
          <CardTitle>Add medication</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Input className="min-w-[140px] flex-1" placeholder="name" value={name} onChange={(e) => setName(e.target.value)} />
          <Input className="w-32" placeholder="dose" value={dose} onChange={(e) => setDose(e.target.value)} />
          <Input className="w-44" placeholder="frequency" value={frequency} onChange={(e) => setFrequency(e.target.value)} />
          <Button onClick={() => add.mutate()} disabled={add.isPending || !name}>
            Add
          </Button>
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
                    {m.dose && <span className="text-muted-foreground">{m.dose}</span>}
                    {m.frequency && <span className="text-muted-foreground">· {m.frequency}</span>}
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
    </div>
  )
}
