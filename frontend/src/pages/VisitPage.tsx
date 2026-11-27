import { useEffect, useState } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AlertTriangle, ArrowLeft, Check, Loader2, Plus, ShieldAlert, Trash2, X } from "lucide-react"
import { useAuth } from "@/lib/auth"
import * as ep from "@/lib/endpoints"
import * as vi from "@/lib/visits"
import type { MedicineChange, VisitNote } from "@/lib/visits"
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input, Select, Textarea } from "@/components/ui"

const fmt = (iso?: string | null) =>
  iso ? new Date(`${iso.slice(0, 10)}T12:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : ""

function ListEditor({ items, onChange, placeholder }: { items: string[]; onChange: (v: string[]) => void; placeholder: string }) {
  return (
    <div className="space-y-1.5">
      {items.map((t, i) => (
        <div key={i} className="flex gap-2">
          <Textarea className="min-h-[38px]" value={t} onChange={(e) => onChange(items.map((x, j) => (j === i ? e.target.value : x)))} />
          <Button variant="ghost" onClick={() => onChange(items.filter((_, j) => j !== i))} aria-label="Remove"><X className="h-4 w-4" /></Button>
        </div>
      ))}
      <Button variant="ghost" onClick={() => onChange([...items, ""])}><Plus className="h-3.5 w-3.5" /> {placeholder}</Button>
    </div>
  )
}

function Field({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</h3>
      {children}
    </div>
  )
}

function ReadOnly({ s, doctor }: { s: VisitNote; doctor: string }) {
  const list = (xs: string[]) => (xs.length ? <ul className="list-disc pl-5">{xs.map((x) => <li key={x}>{x}</li>)}</ul> : <p className="text-muted-foreground">—</p>)
  return (
    <div className="space-y-4 text-sm">
      {s.reason && <Field title="Reason">{s.reason}</Field>}
      <Field title={`What ${doctor} said`}>{list(s.doctor_said)}</Field>
      <Field title="Discussed">{list(s.discussed)}</Field>
      <Field title="Medicine changes">
        {list(s.medicine_changes.map((c) => `${c.action} ${c.name}${c.dose ? ` ${c.dose}` : ""}${c.reason ? ` (${c.reason})` : ""}`))}
      </Field>
      <Field title="Tests">{list(s.tests_ordered.map((t) => `${t.name}${t.due_date ? `, due ${fmt(t.due_date)}` : t.when ? `, ${t.when}` : ""}`))}</Field>
      <Field title="Follow-up">{s.follow_up ? `${s.follow_up.when ?? ""}${s.follow_up.date ? ` (${fmt(s.follow_up.date)})` : ""}` : "—"}</Field>
      <Field title="Watch for">{list(s.watch_for)}</Field>
      <Field title="Questions for next time">{list(s.questions_next_time)}</Field>
    </div>
  )
}

export default function VisitPage() {
  const { patient } = useAuth()
  const pid = patient!.id
  const vid = Number(useParams().vid)
  const qc = useQueryClient()
  const navigate = useNavigate()
  const visit = useQuery({ queryKey: ["visit", pid, vid], queryFn: () => vi.getVisit(pid, vid) })
  const meds = useQuery({ queryKey: ["medications", pid], queryFn: () => ep.listMedications(pid) })
  const [s, setS] = useState<VisitNote | null>(null)
  const [dirty, setDirty] = useState(false)
  useEffect(() => {
    if (visit.data && !dirty) setS(visit.data.structured)
  }, [visit.data, dirty])
  const edit = (patch: Partial<VisitNote>) => { setS((cur) => (cur ? { ...cur, ...patch } : cur)); setDirty(true) }
  const setChange = (i: number, patch: Partial<MedicineChange>) =>
    edit({ medicine_changes: s!.medicine_changes.map((c, j) => (j === i ? { ...c, ...patch } : c)) })

  const saveEdits = useMutation({
    mutationFn: () => vi.updateVisit(pid, vid, { structured: s! }),
    onSuccess: (v) => { qc.setQueryData(["visit", pid, vid], v); setDirty(false) },
  })
  const preview = useMutation({ mutationFn: async () => { if (dirty) await saveEdits.mutateAsync(); return vi.previewVisit(pid, vid) } })
  const confirm = useMutation({
    mutationFn: async () => { if (dirty) await saveEdits.mutateAsync(); return vi.confirmVisit(pid, vid) },
    onSuccess: (v) => {
      qc.setQueryData(["visit", pid, vid], v)
      for (const k of ["medications", "med-safety", "med-calendar", "visits", "reminders", "doctors"]) qc.invalidateQueries({ queryKey: [k, pid] })
    },
  })
  const del = useMutation({ mutationFn: () => vi.deleteVisit(pid, vid), onSuccess: () => navigate("/visits") })

  const v = visit.data
  if (visit.isLoading || !v || !s) return <p className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Loading…</p>
  const checks = v.medicine_checks ?? []
  const confirmErr = (confirm.error as { response?: { data?: { detail?: string } } } | null)?.response?.data?.detail

  return (
    <div className="max-w-4xl space-y-5">
      <Link to="/visits" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="h-4 w-4" /> All visits</Link>
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold tracking-tight text-foreground">{v.doctor_name} · {fmt(v.visit_date)}</h1>
        <Badge className={v.status === "draft" ? "border-transparent bg-amber-100 text-amber-800" : "border-transparent bg-teal-50 text-teal-700"}>
          {v.status === "draft" ? "review and confirm" : "confirmed"}
        </Badge>
        {v.status === "confirmed" && (
          <Link to={`/visits/brief?doctor=${encodeURIComponent(v.doctor_name)}`} className="ml-auto"><Button variant="outline">Pre-visit brief</Button></Link>
        )}
      </div>
      {v.applied && v.applied.length > 0 && (
        <p className="rounded-md bg-teal-50 p-3 text-sm text-teal-800"><Check className="mr-1 inline h-4 w-4" /> Applied: {v.applied.join(", ")}. Reminders and questions saved; medicines re-checked.</p>
      )}

      {v.status === "confirmed" ? (
        <Card><CardContent className="pt-5"><ReadOnly s={v.structured} doctor={v.doctor_name} /></CardContent></Card>
      ) : (
        <>
          <p className="text-sm text-muted-foreground">
            Check the note below. Nothing changes in your medicines or reminders until you confirm. The doctor's words are kept as theirs.
          </p>
          <Card>
            <CardContent className="space-y-5 pt-5 text-sm">
              <Field title="Reason for the visit">
                <Input value={s.reason ?? ""} onChange={(e) => edit({ reason: e.target.value || null })} />
              </Field>
              <Field title={`What ${v.doctor_name} said`}><ListEditor items={s.doctor_said} onChange={(x) => edit({ doctor_said: x })} placeholder="Add" /></Field>
              <Field title="Discussed"><ListEditor items={s.discussed} onChange={(x) => edit({ discussed: x })} placeholder="Add" /></Field>

              <Field title="Medicine changes">
                <div className="space-y-2">
                  {s.medicine_changes.map((c, i) => {
                    const chk = checks[i]
                    return (
                      <div key={i} className="space-y-2 rounded-lg border border-border p-3">
                        <div className="flex flex-wrap gap-2">
                          <Select className="w-28" value={c.action} onChange={(e) => setChange(i, { action: e.target.value as MedicineChange["action"] })}>
                            <option value="start">start</option><option value="change">change</option><option value="stop">stop</option>
                          </Select>
                          <Input className="min-w-[140px] flex-1" value={c.name} onChange={(e) => setChange(i, { name: e.target.value, confirmed: false })} />
                          <Input className="w-28" placeholder="dose" value={c.dose ?? ""} onChange={(e) => setChange(i, { dose: e.target.value || null })} />
                          <Input className="w-36" placeholder="frequency" value={c.frequency ?? ""} onChange={(e) => setChange(i, { frequency: e.target.value || null })} />
                          <Button variant="ghost" onClick={() => edit({ medicine_changes: s.medicine_changes.filter((_, j) => j !== i) })} aria-label="Remove"><X className="h-4 w-4" /></Button>
                        </div>
                        {c.action !== "start" && (
                          <Select value={c.medication_id ?? chk?.medication_id ?? ""} onChange={(e) => setChange(i, { medication_id: Number(e.target.value) || undefined, confirmed: true })}>
                            <option value="">Which of your medicines is this?</option>
                            {(meds.data ?? []).filter((m) => m.active).map((m) => <option key={m.id} value={m.id}>{m.name} {m.dose ?? ""}</option>)}
                          </Select>
                        )}
                        {chk?.status === "please_check" && !c.confirmed && !dirty && (
                          <div className="flex flex-wrap items-center gap-2 rounded-md bg-amber-50 p-2 text-amber-900">
                            <AlertTriangle className="h-4 w-4" /> <span className="flex-1">Please check: {chk.note}</span>
                            {chk.suggested_medication_id && (
                              <Button variant="outline" onClick={() => setChange(i, { name: chk.matched_name ?? c.name, medication_id: chk.suggested_medication_id, confirmed: true })}>
                                Yes, {chk.matched_name}
                              </Button>
                            )}
                            {chk.suggestion.length > 0 && (
                              <Button variant="outline" onClick={() => setChange(i, { ingredients: chk.suggestion.map((x) => x.name), confirmed: true })}>
                                Yes, it's {chk.suggestion.map((x) => x.name).join(" + ")}
                              </Button>
                            )}
                            <Button variant="ghost" onClick={() => setChange(i, { confirmed: true })}>The name is right</Button>
                          </div>
                        )}
                        {c.confirmed && <p className="text-xs text-teal-700"><Check className="mr-1 inline h-3 w-3" />Checked by you</p>}
                        {chk?.status === "ok" && chk.ingredients.length > 0 && !dirty && (
                          <p className="text-xs text-muted-foreground">{chk.ingredients.join(" + ")} (RxNorm){chk.matched_name ? ` · your ${chk.matched_name}` : ""}</p>
                        )}
                      </div>
                    )
                  })}
                  <Button variant="ghost" onClick={() => edit({ medicine_changes: [...s.medicine_changes, { action: "start", name: "", dose: null, frequency: null, reason: null }] })}>
                    <Plus className="h-3.5 w-3.5" /> Add a medicine change
                  </Button>
                </div>
              </Field>

              <Field title="Tests ordered">
                {s.tests_ordered.map((t, i) => (
                  <div key={i} className="flex gap-2">
                    <Input value={t.name} onChange={(e) => edit({ tests_ordered: s.tests_ordered.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)) })} />
                    <Input type="date" className="w-44" value={t.due_date ?? ""} onChange={(e) => edit({ tests_ordered: s.tests_ordered.map((x, j) => (j === i ? { ...x, due_date: e.target.value || null } : x)) })} />
                  </div>
                ))}
                <Button variant="ghost" onClick={() => edit({ tests_ordered: [...s.tests_ordered, { name: "", when: null, due_date: null }] })}><Plus className="h-3.5 w-3.5" /> Add a test</Button>
              </Field>
              <Field title="Follow-up">
                <div className="flex gap-2">
                  <Input placeholder="e.g. in 6 weeks" value={s.follow_up?.when ?? ""} onChange={(e) => edit({ follow_up: { when: e.target.value || null, date: s.follow_up?.date ?? null } })} />
                  <Input type="date" className="w-44" value={s.follow_up?.date ?? ""} onChange={(e) => edit({ follow_up: { when: s.follow_up?.when ?? null, date: e.target.value || null } })} />
                </div>
              </Field>
              <Field title="Things to watch for"><ListEditor items={s.watch_for} onChange={(x) => edit({ watch_for: x })} placeholder="Add" /></Field>
              <Field title="Questions for next time"><ListEditor items={s.questions_next_time} onChange={(x) => edit({ questions_next_time: x })} placeholder="Add a question" /></Field>
              <details className="text-xs text-muted-foreground"><summary className="cursor-pointer">Your recap as {v.source === "typed" ? "typed" : "transcribed"}</summary><p className="mt-1 whitespace-pre-line">{v.transcript}</p></details>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2"><CardTitle className="flex items-center gap-2"><ShieldAlert className="h-4 w-4" /> Check against your other medicines</CardTitle></CardHeader>
            <CardContent className="space-y-2 text-sm">
              <Button variant="outline" onClick={() => preview.mutate()} disabled={preview.isPending}>
                {preview.isPending && <Loader2 className="h-4 w-4 animate-spin" />} Check for clashes
              </Button>
              {preview.data?.findings.map((f) => (
                <div key={f.id} className="rounded-md border border-border p-2.5">
                  <p className="font-medium">{f.level_label}{f.severity ? ` · ${f.severity}` : ""}: {f.title}</p>
                  <p>{f.explanation}</p>
                  {f.quote && <p className="text-xs italic text-muted-foreground">“{f.quote}”</p>}
                </div>
              ))}
              {preview.data?.message && <p className="rounded-md bg-muted p-2.5">{preview.data.message}</p>}
            </CardContent>
          </Card>

          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={() => confirm.mutate()} disabled={confirm.isPending}>
              {confirm.isPending && <Loader2 className="h-4 w-4 animate-spin" />} Confirm note
            </Button>
            {dirty && <Button variant="outline" onClick={() => saveEdits.mutate()} disabled={saveEdits.isPending}>Save edits</Button>}
            <Button variant="ghost" className="ml-auto text-destructive" onClick={() => del.mutate()}><Trash2 className="h-3.5 w-3.5" /> Discard</Button>
          </div>
          {confirm.isError && <p className="text-sm text-destructive">{confirmErr ?? "Couldn't confirm the note."}</p>}
        </>
      )}
    </div>
  )
}
