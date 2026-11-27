import { Link } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Bell, Check, ClipboardList, Plus, Stethoscope } from "lucide-react"
import { useAuth } from "@/lib/auth"
import * as vi from "@/lib/visits"
import { Badge, Button, Card, CardContent, CardHeader, CardTitle } from "@/components/ui"

const fmt = (iso?: string | null) =>
  iso ? new Date(`${iso.slice(0, 10)}T12:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : ""

export default function VisitsPage() {
  const { patient } = useAuth()
  const pid = patient!.id
  const qc = useQueryClient()
  const visits = useQuery({ queryKey: ["visits", pid], queryFn: () => vi.listVisits(pid) })
  const doctors = useQuery({ queryKey: ["doctors", pid], queryFn: () => vi.listDoctors(pid) })
  const reminders = useQuery({ queryKey: ["reminders", pid], queryFn: () => vi.listReminders(pid) })
  const done = useMutation({
    mutationFn: (rid: number) => vi.reminderDone(pid, rid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["reminders", pid] }),
  })

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Doctor visits</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Right after a visit, say or type what happened. It becomes a note your assistant remembers, and your medicines update once you confirm.
          </p>
        </div>
        <Link to="/visits/new">
          <Button><Plus className="h-4 w-4" /> New visit recap</Button>
        </Link>
      </div>

      {(reminders.data ?? []).length > 0 && (
        <Card>
          <CardHeader className="pb-2"><CardTitle className="flex items-center gap-2"><Bell className="h-4 w-4" /> Reminders</CardTitle></CardHeader>
          <CardContent>
            <ul className="divide-y divide-border text-sm">
              {reminders.data!.map((r) => (
                <li key={r.id} className="flex items-center justify-between gap-3 py-2">
                  <span>
                    {r.text}
                    {r.due_date && <span className="text-muted-foreground"> · due {fmt(r.due_date)}</span>}
                  </span>
                  <Button variant="ghost" onClick={() => done.mutate(r.id)} disabled={done.isPending}>
                    <Check className="h-3.5 w-3.5" /> Done
                  </Button>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="pb-2"><CardTitle className="flex items-center gap-2"><ClipboardList className="h-4 w-4" /> Before your next visit</CardTitle></CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          {(doctors.data ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground">Add a visit recap or a medicine with its prescriber to prepare a brief.</p>
          ) : (
            doctors.data!.map((d) => (
              <Link key={d.name} to={`/visits/brief?doctor=${encodeURIComponent(d.name)}`}>
                <Button variant="outline">
                  <Stethoscope className="h-3.5 w-3.5" /> Brief for {d.name}{d.specialty ? ` (${d.specialty})` : ""}
                </Button>
              </Link>
            ))
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2"><CardTitle>Visit notes</CardTitle></CardHeader>
        <CardContent>
          {(visits.data ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground">No visits yet.</p>
          ) : (
            <ul className="divide-y divide-border text-sm">
              {visits.data!.map((v) => (
                <li key={v.id}>
                  <Link to={`/visits/${v.id}`} className="flex flex-wrap items-center gap-2 py-2.5 hover:bg-muted/40">
                    <span className="font-medium text-foreground">{fmt(v.visit_date)}</span>
                    <span>{v.doctor_name}{v.specialty ? ` · ${v.specialty}` : ""}</span>
                    {v.reason && <span className="text-muted-foreground">· {v.reason}</span>}
                    <Badge className={v.status === "draft" ? "ml-auto border-transparent bg-amber-100 text-amber-800" : "ml-auto border-transparent bg-teal-50 text-teal-700"}>
                      {v.status === "draft" ? "needs review" : "confirmed"}
                    </Badge>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
