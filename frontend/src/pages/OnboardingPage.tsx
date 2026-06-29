import { useState, type FormEvent } from "react"
import { Navigate, useNavigate } from "react-router-dom"
import { useAuth } from "@/lib/auth"
import * as ep from "@/lib/endpoints"
import { Button, Card, CardContent, CardHeader, CardTitle, Input, Label } from "@/components/ui"

export default function OnboardingPage() {
  const { user, patient, loading, refreshPatient } = useAuth()
  const nav = useNavigate()
  const [name, setName] = useState("")
  const [age, setAge] = useState("")
  const [sex, setSex] = useState("")
  const [conditions, setConditions] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")

  if (loading) return <div className="p-8 text-muted-foreground">Loading…</div>
  if (!user) return <Navigate to="/login" replace />
  if (patient) return <Navigate to="/" replace />

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError("")
    try {
      const p = await ep.createPatient({
        name,
        age: age ? Number(age) : null,
        sex: sex || null,
      })
      const conds = conditions.split(",").map((c) => c.trim()).filter(Boolean)
      if (conds.length) await ep.putBackground(p.id, { conditions: conds })
      await refreshPatient()
      nav("/")
    } catch {
      setError("Could not create profile")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Set up your profile</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-1">
              <Label>Name</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} required />
            </div>
            <div className="flex gap-3">
              <div className="flex-1 space-y-1">
                <Label>Age</Label>
                <Input type="number" value={age} onChange={(e) => setAge(e.target.value)} />
              </div>
              <div className="flex-1 space-y-1">
                <Label>Sex</Label>
                <Input value={sex} onChange={(e) => setSex(e.target.value)} placeholder="F / M / ..." />
              </div>
            </div>
            <div className="space-y-1">
              <Label>Known conditions (comma-separated)</Label>
              <Input
                value={conditions}
                onChange={(e) => setConditions(e.target.value)}
                placeholder="e.g. Hypertension, Asthma"
              />
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <Button type="submit" disabled={busy} className="w-full">
              {busy ? "Saving…" : "Continue"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
