import { useEffect, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AlertTriangle, Check, History, Send, Sparkles } from "lucide-react"
import { useAuth } from "@/lib/auth"
import * as ep from "@/lib/endpoints"
import type { HistoryEntry, IntakeResult, ReasoningSummary, SemanticMatch } from "@/lib/endpoints"
import { Button, Card, CardContent, Input, Select, Textarea } from "@/components/ui"

const MAX_CLARIFY_ROUNDS = 3

// ---------- helpers ----------
function fmtTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })
}
function fmtDay(iso?: string): string {
  if (!iso) return ""
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })
}

/** Concise "what the system extracted" from a structured fact. */
function summarizeExtracted(structured: Record<string, unknown>): string {
  const s = structured as Record<string, any>
  const name: string = s.name || s.type || "entry"
  const a = (s.attributes as Record<string, any>) || {}
  const parts: string[] = []
  if (a.systolic != null && a.diastolic != null) parts.push(`${a.systolic}/${a.diastolic}`)
  if (s.value != null) parts.push(`${s.value}${s.unit ? " " + s.unit : ""}`)
  if (a.severity != null) parts.push(`severity ${a.severity}`)
  if (a.duration) parts.push(String(a.duration))
  if (a.location) parts.push(String(a.location))
  if (a.onset) parts.push(`onset ${a.onset}`)
  return parts.length ? `${name} · ${parts.join(" · ")}` : name
}

// ---------- intelligence shown beneath a freshly-logged entry ----------
interface Intel {
  matches: SemanticMatch[]
  reasoning: ReasoningSummary
}

function IntelCards({ intel }: { intel: Intel }) {
  const strong = intel.matches.filter((m) => m.distance < 1.0).slice(0, 2)
  const obs = intel.reasoning.observations ?? []
  const alerts = intel.reasoning.alerts ?? []
  if (!strong.length && !obs.length && !alerts.length) return null
  return (
    <div className="mt-2 space-y-2">
      {strong.length > 0 && (
        <div className="rounded-lg border border-border bg-background/60 p-3 text-sm">
          <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            <History className="h-3.5 w-3.5" /> Related to your past entries
          </div>
          <ul className="space-y-1">
            {strong.map((m, i) => (
              <li key={i} className="text-foreground">
                Similar to {fmtDay(m.metadata?.date)}: <span className="text-muted-foreground">“{m.text}”</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {alerts.map((a, i) => (
        <div key={`a${i}`} className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          <AlertTriangle className="h-4 w-4 shrink-0" /> {a.message}
        </div>
      ))}
      {obs.length > 0 && (
        <div className="rounded-lg border border-teal-200 bg-teal-50/60 p-3 text-sm">
          <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-teal-700">
            <Sparkles className="h-3.5 w-3.5" /> New observation{obs.length > 1 ? "s" : ""}
          </div>
          <ul className="space-y-1">
            {obs.map((o, i) => (
              <li key={i} className="flex gap-2 text-foreground">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-teal-600" />
                {o}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

// ---------- one thread row (the user's words + what the system did) ----------
function ThreadRow({ entry, intel }: { entry: HistoryEntry; intel?: Intel }) {
  return (
    <div className="space-y-1.5">
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-primary px-3.5 py-2 text-sm text-primary-foreground">
          {entry.raw_text || <span className="italic opacity-80">(no text)</span>}
        </div>
      </div>
      <p className="pr-1 text-right text-[11px] text-muted-foreground">{fmtTime(entry.created_at)}</p>
      <div className="max-w-[85%]">
        <div className="inline-flex items-center gap-1.5 rounded-2xl rounded-bl-sm border border-border bg-muted px-3.5 py-2 text-sm">
          <Check className="h-3.5 w-3.5 shrink-0 text-teal-600" />
          <span className="text-muted-foreground">Logged:</span>
          <span className="font-medium capitalize text-foreground">{summarizeExtracted(entry.structured)}</span>
        </div>
        {intel && <IntelCards intel={intel} />}
      </div>
    </div>
  )
}

// ---------- free-text composer with bounded multi-turn clarify ----------
function Composer({ pid, onProcessed }: { pid: number; onProcessed: (r: IntakeResult) => void }) {
  const [text, setText] = useState("")
  const [base, setBase] = useState<string | null>(null) // accumulated transcript while clarifying
  const [question, setQuestion] = useState<string | null>(null)
  const [answer, setAnswer] = useState("")
  const [round, setRound] = useState(0)
  const [note, setNote] = useState("")

  function reset() {
    setText(""); setBase(null); setQuestion(null); setAnswer(""); setRound(0)
  }

  const submit = useMutation({
    mutationFn: () => ep.postIntake(pid, text),
    onSuccess: (res) => {
      setNote("")
      if (res.status === "clarification_needed") {
        setBase(text)
        setQuestion(res.question ?? "Could you add a bit more detail?")
        setRound(1)
      } else {
        onProcessed(res)
        reset()
      }
    },
    onError: () => setNote("Something went wrong — please try again."),
  })

  const send = useMutation({
    mutationFn: () => ep.postIntakeAnswer(pid, base ?? "", answer),
    onSuccess: (res) => {
      if (res.status === "clarification_needed") {
        const acc = `${base}\nAdditional info: ${answer}`
        if (round >= MAX_CLARIFY_ROUNDS) {
          // Cap reached: hand the accumulated detail back so nothing is lost.
          setText(acc)
          setNote("I've gathered what you shared — add anything else and resend to log it.")
          setBase(null); setQuestion(null); setAnswer(""); setRound(0)
        } else {
          setBase(acc)
          setQuestion(res.question ?? "A little more detail?")
          setAnswer("")
          setRound(round + 1)
        }
      } else {
        onProcessed(res)
        reset(); setNote("")
      }
    },
    onError: () => setNote("Something went wrong — please try again."),
  })

  const busy = submit.isPending || send.isPending

  return (
    <Card>
      <CardContent className="space-y-3 pt-5">
        <Textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Describe a symptom or note — e.g. 'throbbing headache for 2 days, about 6/10'"
          disabled={!!question}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && text.trim() && !question) submit.mutate()
          }}
        />
        {question && (
          <div className="space-y-2 rounded-lg border border-amber-300 bg-amber-50 p-3">
            <p className="text-sm font-medium text-amber-900">{question}</p>
            <p className="text-xs text-amber-700">Follow-up {round} of {MAX_CLARIFY_ROUNDS}</p>
            <Textarea value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="Your answer…" />
            <div className="flex gap-2">
              <Button onClick={() => send.mutate()} disabled={busy || !answer.trim()}>
                {send.isPending ? "Sending…" : "Send answer"}
              </Button>
              <Button variant="ghost" onClick={reset} disabled={busy}>Cancel</Button>
            </div>
          </div>
        )}
        {!question && (
          <div className="flex items-center gap-3">
            <Button onClick={() => submit.mutate()} disabled={busy || !text.trim()}>
              <Send className="h-4 w-4" /> {submit.isPending ? "Processing…" : "Log it"}
            </Button>
            {note && <span className="text-sm text-muted-foreground">{note}</span>}
            {!note && <span className="text-xs text-muted-foreground">Runs the full pipeline: parse → retrieve related → reason.</span>}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ---------- vital quick-add with contextual help (#4) ----------
const VITALS: { value: string; label: string; unit: string; help: string }[] = [
  { value: "bp_systolic", label: "BP systolic", unit: "mmHg", help: "Top blood-pressure number (pressure as the heart beats). Often around 90–120 mmHg." },
  { value: "bp_diastolic", label: "BP diastolic", unit: "mmHg", help: "Bottom blood-pressure number (pressure between beats). Often around 60–80 mmHg." },
  { value: "heart_rate", label: "Heart rate", unit: "bpm", help: "Resting beats per minute. Often around 60–100 bpm." },
  { value: "weight", label: "Weight", unit: "kg", help: "Body weight — most useful tracked as a trend over time." },
  { value: "blood_glucose", label: "Blood glucose", unit: "mg/dL", help: "Blood sugar. Fasting is often around 70–99 mg/dL." },
  { value: "spo2", label: "SpO₂", unit: "%", help: "Blood-oxygen saturation. Often around 95–100%." },
]

function VitalQuickAdd({ pid, onSaved }: { pid: number; onSaved: (label: string) => void }) {
  const qc = useQueryClient()
  const [vitalType, setVitalType] = useState("bp_systolic")
  const [value, setValue] = useState("")
  const meta = VITALS.find((v) => v.value === vitalType)!
  const m = useMutation({
    mutationFn: () => ep.createVital(pid, { vital_type: vitalType, value: Number(value), unit: meta.unit }),
    onSuccess: () => {
      onSaved(`${meta.label} ${value} ${meta.unit}`)
      setValue("")
      qc.invalidateQueries()
    },
  })
  return (
    <Card>
      <CardContent className="space-y-2 pt-5">
        <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Quick add a reading
        </div>
        <div className="flex flex-wrap gap-2">
          <Select value={vitalType} onChange={(e) => setVitalType(e.target.value)} className="w-40">
            {VITALS.map((v) => (
              <option key={v.value} value={v.value}>{v.label}</option>
            ))}
          </Select>
          <Input
            type="number"
            placeholder="value"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            className="w-28"
          />
          <span className="self-center text-sm text-muted-foreground">{meta.unit}</span>
          <Button onClick={() => m.mutate()} disabled={m.isPending || !value}>Save</Button>
        </div>
        <p className="text-xs text-muted-foreground">{meta.help}</p>
      </CardContent>
    </Card>
  )
}

// ---------- page ----------
export default function LogPage() {
  const { patient } = useAuth()
  const pid = patient!.id
  const qc = useQueryClient()
  const entries = useQuery({ queryKey: ["entries", pid], queryFn: () => ep.listEntries(pid) })
  const [intel, setIntel] = useState<Map<number, Intel>>(new Map())
  const [vitalNotes, setVitalNotes] = useState<{ id: number; label: string; at: string }[]>([])
  const bottomRef = useRef<HTMLDivElement>(null)

  // oldest → newest for a natural running log
  const ordered = [...(entries.data ?? [])].sort(
    (a, b) => +new Date(a.created_at) - +new Date(b.created_at),
  )

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [ordered.length, vitalNotes.length, intel])

  function onProcessed(res: IntakeResult) {
    const ne = res.new_entry
    if (ne) {
      setIntel((prev) =>
        new Map(prev).set(ne.entry_id, {
          matches: res.context_bundle?.semantic_matches ?? [],
          reasoning: res.reasoning_summary ?? {},
        }),
      )
    }
    qc.invalidateQueries() // refetch the thread + dashboard data
  }

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col gap-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Log</h1>
        <p className="text-sm text-muted-foreground">
          Tell the engine what's going on. It parses each entry, finds related past logs, and surfaces what it noticed.
        </p>
      </div>

      <Card className="flex-1 overflow-hidden">
        <CardContent className="h-full overflow-y-auto py-5">
          {entries.isLoading ? (
            <p className="text-sm text-muted-foreground">Loading your log…</p>
          ) : ordered.length === 0 && vitalNotes.length === 0 ? (
            <p className="text-sm text-muted-foreground">No entries yet. Log your first one below.</p>
          ) : (
            <div className="space-y-5">
              {ordered.map((e) => (
                <ThreadRow key={e.id} entry={e} intel={intel.get(e.id)} />
              ))}
              {vitalNotes.map((n) => (
                <div key={`v${n.id}`} className="max-w-[85%]">
                  <div className="inline-flex items-center gap-1.5 rounded-2xl rounded-bl-sm border border-border bg-muted px-3.5 py-2 text-sm">
                    <Check className="h-3.5 w-3.5 shrink-0 text-teal-600" />
                    <span className="text-muted-foreground">Recorded:</span>
                    <span className="font-medium text-foreground">{n.label}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
          <div ref={bottomRef} />
        </CardContent>
      </Card>

      <Composer pid={pid} onProcessed={onProcessed} />
      <VitalQuickAdd
        pid={pid}
        onSaved={(label) => setVitalNotes((p) => [...p, { id: Date.now(), label, at: new Date().toISOString() }])}
      />
    </div>
  )
}
