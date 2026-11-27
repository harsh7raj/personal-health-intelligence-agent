import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ExternalLink, Loader2, MessageSquareText, RotateCw, Search, ShieldAlert } from "lucide-react"
import * as ep from "@/lib/endpoints"
import type { MedFinding } from "@/lib/endpoints"
import { Button, Card, CardContent, Input } from "@/components/ui"
import { cn } from "@/lib/utils"

// Level badges: what the finding rests on. Severity colours belong to Verified findings only.
const LEVEL_BADGE: Record<MedFinding["level"], string> = {
  verified: "bg-slate-800 text-white",
  label: "bg-sky-100 text-sky-800",
  ai: "bg-violet-100 text-violet-800",
}
const SEVERITY: Record<string, string> = {
  Major: "bg-red-100 text-red-700",
  Moderate: "bg-amber-100 text-amber-800",
  Minor: "bg-blue-100 text-blue-700",
}
const KIND_LABEL: Record<MedFinding["kind"], string> = {
  interaction: "Interaction",
  duplicate: "Duplicate",
  timing: "Timing",
  condition: "Your record",
  side_effect: "Possible side effect",
  alcohol: "Alcohol",
}

function FindingCard({ f, onAsk }: { f: MedFinding; onAsk?: (f: MedFinding) => void }) {
  return (
    <div className={cn("space-y-2 rounded-lg border p-3.5 text-sm", f.level === "ai" ? "border-violet-200" : "border-border")}>
      <div className="flex flex-wrap items-center gap-2">
        <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-semibold", LEVEL_BADGE[f.level])}>{f.level_label}</span>
        {f.level === "verified" && f.severity && (
          <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-semibold", SEVERITY[f.severity] ?? "bg-slate-100 text-slate-600")}>
            {f.severity}
          </span>
        )}
        <span className="text-[11px] uppercase tracking-wide text-muted-foreground">{KIND_LABEL[f.kind]}</span>
      </div>
      <p className="font-semibold text-foreground">{f.title}</p>
      <p className="text-foreground">{f.explanation}</p>
      {f.quote && (
        <blockquote className="border-l-2 border-sky-300 pl-3 text-xs italic text-muted-foreground">“{f.quote}”</blockquote>
      )}
      {f.source && (
        <p className="text-xs text-muted-foreground">
          Source:{" "}
          {f.source.url ? (
            <a href={f.source.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 text-primary underline">
              {f.source.name} <ExternalLink className="h-3 w-3" />
            </a>
          ) : (
            f.source.name
          )}
        </p>
      )}
      {f.pharmacist_questions.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-muted-foreground">Questions to ask your pharmacist</p>
          <ul className="list-disc pl-5 text-xs text-foreground">
            {f.pharmacist_questions.map((q) => <li key={q}>{q}</li>)}
          </ul>
        </div>
      )}
      {onAsk && (
        <Button variant="ghost" onClick={() => onAsk(f)} className="-ml-2">
          <MessageSquareText className="h-3.5 w-3.5" /> Ask about this
        </Button>
      )}
    </div>
  )
}

function CanITake({ pid }: { pid: number }) {
  const [name, setName] = useState("")
  const check = useMutation({ mutationFn: () => ep.checkMedicine(pid, name.trim()) })
  const r = check.data
  return (
    <Card>
      <CardContent className="space-y-3 pt-5">
        <p className="text-sm font-semibold text-foreground">Thinking of taking something new?</p>
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            if (name.trim()) check.mutate()
          }}
        >
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. ibuprofen, Crocin, Shelcal" />
          <Button type="submit" disabled={check.isPending || !name.trim()}>
            {check.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />} Check
          </Button>
        </form>
        {r && (
          <div className="space-y-2">
            {r.assumed && <p className="rounded-md bg-violet-50 p-2 text-xs text-violet-800">{r.assumed}</p>}
            {r.findings.map((f) => <FindingCard key={f.id} f={f} />)}
            {r.message && <p className="rounded-md bg-muted p-2.5 text-sm text-foreground">{r.message}</p>}
          </div>
        )}
        {check.isError && <p className="text-sm text-destructive">Couldn't run the check right now.</p>}
      </CardContent>
    </Card>
  )
}

/** Medication safety (Phase 5): three levels, patient-aware checks, never an all-clear. */
export function MedicationSafety({ patientId }: { patientId: number }) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const q = useQuery({ queryKey: ["med-safety", patientId], queryFn: () => ep.getMedSafety(patientId) })
  const recheck = useMutation({
    mutationFn: () => ep.getMedSafety(patientId, true),
    onSuccess: (data) => qc.setQueryData(["med-safety", patientId], data),
  })
  const d = recheck.data ?? q.data
  const ask = (f: MedFinding) => navigate("/", { state: { focus: { type: "med_finding", id: f.id }, title: f.title } })

  return (
    <div className="space-y-4">
      <div className="flex items-start gap-2.5 rounded-lg border border-amber-300 bg-amber-50 p-3.5 text-sm text-amber-900">
        <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />
        <p>{d?.disclaimer ?? "These checks can miss things and are not medical advice. Don't stop or change any medicine on your own."}</p>
      </div>
      {q.isLoading ? (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Checking your medicines against DDInter, FDA labels and RxClass…
        </p>
      ) : d && d.medicines.length > 0 ? (
        <Card>
          <CardContent className="space-y-3 pt-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm text-muted-foreground">
                {d.findings.length} finding{d.findings.length === 1 ? "" : "s"} for {d.medicines.join(", ")} · checked{" "}
                {new Date(d.checked_at).toLocaleString()}
              </p>
              <Button variant="outline" onClick={() => recheck.mutate()} disabled={recheck.isPending}>
                <RotateCw className={cn("h-3.5 w-3.5", recheck.isPending && "animate-spin")} /> Re-check
              </Button>
            </div>
            {d.unresolved_medicines.length > 0 && (
              <p className="rounded-md bg-violet-50 p-2.5 text-xs text-violet-800">
                We couldn't identify {d.unresolved_medicines.join(", ")} in RxNorm, so checks for{" "}
                {d.unresolved_medicines.length === 1 ? "it" : "them"} may miss things. Re-add it with its generic name confirmed.
              </p>
            )}
            {d.findings.map((f) => <FindingCard key={f.id} f={f} onAsk={ask} />)}
            {d.pairs.filter((p) => p.message).map((p) => (
              <p key={p.medicines.join("+")} className="rounded-md bg-muted p-2.5 text-sm text-foreground">
                <span className="font-medium">{p.medicines.join(" + ")}:</span> {p.message}
              </p>
            ))}
            <p className="border-t border-border pt-2 text-xs text-muted-foreground">
              Levels: <b>Verified</b> = in the DDInter database (severity shown) or RxNorm/RxClass; <b>Official label</b> = quoted
              from the FDA label; <b>AI flag</b> = unverified, ask your pharmacist{d.ai_flags_enabled ? "" : " (switched off)"}.
            </p>
          </CardContent>
        </Card>
      ) : null}
      <CanITake pid={patientId} />
    </div>
  )
}
