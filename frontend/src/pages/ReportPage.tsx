import { useEffect, useRef, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AlertTriangle, ArrowDown, ArrowLeft, ArrowUp, Check, Copy, Download, HelpCircle, Loader2, Minus } from "lucide-react"
import { useAuth } from "@/lib/auth"
import * as ep from "@/lib/endpoints"
import type { ReportRow } from "@/lib/endpoints"
import { ChatPanel } from "@/components/ChatPanel"
import { Badge, Button, Card, CardContent, CardHeader, CardTitle } from "@/components/ui"
import { cn, saveBlob } from "@/lib/utils"

const REPORT_SUGGESTIONS = [
  "What does each flagged test measure?",
  "Is this bad?",
  "How does this compare to last time?",
  "Why could this be high?",
]

const fmtDay = (iso?: string | null) =>
  iso ? new Date(`${iso.slice(0, 10)}T12:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : ""

const FLAG_STYLE: Record<string, string> = {
  high: "border-transparent bg-amber-100 text-amber-800",
  low: "border-transparent bg-sky-100 text-sky-800",
  normal: "border-transparent bg-teal-50 text-teal-700",
}

/** Where the value sits against its printed range. Drawn only when the range is numeric. */
function RangeBar({ row }: { row: ReportRow }) {
  const value = Number(String(row.value ?? "").replace(/,/g, ""))
  const { range_low: low, range_high: high } = row
  if (!Number.isFinite(value) || (low == null && high == null)) {
    return <span className="text-xs text-muted-foreground">{row.reference_range ? `range ${row.reference_range}` : "no numeric range"}</span>
  }
  const lo = low ?? 0
  const hi = high ?? Math.max(lo * 2, value * 1.2)
  const pad = (hi - lo) * 0.5 || Math.abs(hi) * 0.5 || 1
  // Leave room either side so a value far outside the range doesn't sit on the edge.
  const min = Math.min(low != null ? lo - pad : 0, value - pad * 0.3)
  const max = Math.max(hi + pad, value + pad * 0.3)
  const pct = (x: number) => ((x - min) / (max - min)) * 100
  const inside = row.flag === "normal"
  return (
    <div className="w-full">
      <div className="relative h-2 rounded-full bg-muted">
        <div className="absolute inset-y-0 rounded-full bg-teal-200" style={{ left: `${pct(lo)}%`, width: `${pct(hi) - pct(lo)}%` }} />
        <div
          className={cn("absolute -top-1 h-4 w-1.5 -translate-x-1/2 rounded-full", inside ? "bg-teal-700" : row.flag === "low" ? "bg-sky-600" : "bg-amber-600")}
          style={{ left: `${Math.min(100, Math.max(0, pct(value)))}%` }}
          title={`${row.value} ${row.unit ?? ""}`}
        />
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
        <span>{low ?? ""}</span>
        <span>range {row.reference_range}</span>
        <span>{high ?? ""}</span>
      </div>
    </div>
  )
}

function Change({ row }: { row: ReportRow }) {
  if (!row.previous || !row.change) return <span className="text-xs text-muted-foreground">first result</span>
  const Icon = row.change.direction === "up" ? ArrowUp : row.change.direction === "down" ? ArrowDown : Minus
  return (
    <div className="text-xs text-muted-foreground">
      <div className="flex items-center gap-1 font-medium text-foreground">
        <Icon className="h-3 w-3" />
        {row.change.amount > 0 ? "+" : ""}
        {row.change.amount}
        {row.change.percent != null ? ` (${row.change.percent > 0 ? "+" : ""}${row.change.percent}%)` : ""}
      </div>
      was {row.previous.value} on {fmtDay(row.previous.date)}
    </div>
  )
}

function ValueRow({ row }: { row: ReportRow }) {
  const flagged = row.flag === "high" || row.flag === "low"
  return (
    <div className={cn("grid grid-cols-[minmax(0,1.3fr)_minmax(0,0.8fr)_minmax(0,1.6fr)_minmax(0,1fr)] items-center gap-3 border-b py-3 last:border-0",
      row.critical && "bg-red-50")}>
      <div className="min-w-0">
        <div className="truncate text-sm font-medium text-foreground" title={row.test_name}>{row.display_name}</div>
        {row.display_name !== row.test_name && <div className="truncate text-[11px] text-muted-foreground">{row.test_name}</div>}
      </div>
      <div>
        <span className={cn("text-sm font-semibold", flagged && "text-amber-800", row.flag === "low" && "text-sky-800")}>{row.value ?? "—"}</span>
        {row.unit && <span className="ml-1 text-xs text-muted-foreground">{row.unit}</span>}
        <div className="mt-0.5">
          <Badge className={FLAG_STYLE[row.flag] ?? "border-transparent bg-slate-100 text-slate-600"}>
            {row.flag === "unknown" ? "no range" : row.flag}
          </Badge>
        </div>
      </div>
      <RangeBar row={row} />
      <Change row={row} />
    </div>
  )
}

function DoctorQuestions({ pid, rid }: { pid: number; rid: number }) {
  const [copied, setCopied] = useState(false)
  const q = useMutation({ mutationFn: () => ep.reportQuestions(pid, rid) })
  async function copy() {
    await navigator.clipboard.writeText((q.data?.questions ?? []).map((x) => `- ${x}`).join("\n"))
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }
  return (
    <Card>
      <CardContent className="space-y-2 pt-4">
        <Button variant="outline" onClick={() => q.mutate()} disabled={q.isPending} className="w-full">
          {q.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <HelpCircle className="h-4 w-4" />}
          What should I ask my doctor?
        </Button>
        {q.data && (
          <div className="space-y-2">
            <ul className="list-disc space-y-1 pl-5 text-sm text-foreground">
              {q.data.questions.map((x) => <li key={x}>{x}</li>)}
            </ul>
            <Button variant="ghost" onClick={copy}>
              {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />} {copied ? "Copied" : "Copy questions"}
            </Button>
          </div>
        )}
        {q.isError && <p className="text-sm text-destructive">Couldn't write questions right now.</p>}
      </CardContent>
    </Card>
  )
}

export default function ReportPage() {
  const { patient } = useAuth()
  const pid = patient!.id
  const rid = Number(useParams().rid)
  const qc = useQueryClient()
  const report = useQuery({
    queryKey: ["report", pid, rid],
    queryFn: () => ep.getReport(pid, rid),
    refetchInterval: (query) => (["uploaded", "parsing"].includes(query.state.data?.status ?? "") ? 2500 : false),
  })
  const thread = useQuery({ queryKey: ["chat", pid, rid], queryFn: () => ep.getChatHistory(pid, rid) })
  const explain = useMutation({
    mutationFn: () => ep.explainReport(pid, rid),
    onSettled: () => qc.invalidateQueries({ queryKey: ["chat", pid, rid] }),
  })
  const asked = useRef(false)
  const dl = useMutation({
    mutationFn: async () => saveBlob(await ep.fetchReportBlob(pid, rid), report.data?.filename ?? "report"),
  })

  // Open with the explanation: the first time a parsed report is viewed, write it.
  const parsed = report.data?.status === "parsed"
  const empty = thread.isSuccess && !thread.data.some((m) => m.meta?.kind === "report_explainer")
  useEffect(() => {
    if (parsed && empty && !asked.current) {
      asked.current = true
      explain.mutate()
    }
  }, [parsed, empty, explain])

  const r = report.data
  if (report.isLoading) return <p className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Loading report…</p>
  if (!r) return <p className="text-sm text-destructive">Couldn't load this report.</p>
  const flagged = r.values.filter((v) => v.flag === "high" || v.flag === "low").length

  return (
    <div className="space-y-4">
      <Link to="/reports" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" /> All reports
      </Link>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_420px]">
        <div className="min-w-0 space-y-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-foreground">{r.report_type ?? "Report"}</h1>
              <p className="mt-1 text-sm text-muted-foreground">
                {r.test_date ? `Test date ${fmtDay(r.test_date)}` : `Uploaded ${fmtDay(r.created_at)}`} · {r.filename}
              </p>
            </div>
            <Button variant="outline" onClick={() => dl.mutate()} disabled={dl.isPending}>
              <Download className="h-3.5 w-3.5" /> Original file
            </Button>
          </div>

          {r.critical.length > 0 && (
            <div className="rounded-xl border-2 border-red-300 bg-red-50 p-4 text-sm text-red-800" role="alert">
              <div className="flex items-start gap-2">
                <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
                <div className="space-y-1 font-semibold">{r.critical.map((c) => <p key={c.message}>{c.message}</p>)}</div>
              </div>
            </div>
          )}

          {!parsed ? (
            <Card>
              <CardContent className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
                {r.status === "failed" ? (
                  <span className="text-destructive">{r.parse_error ?? "Couldn't read this report."}</span>
                ) : (
                  <><Loader2 className="h-4 w-4 animate-spin" /> Reading the report…</>
                )}
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardHeader className="pb-1">
                <CardTitle>
                  {r.values.length} results{flagged ? ` · ${flagged} outside the printed range` : ""}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-[minmax(0,1.3fr)_minmax(0,0.8fr)_minmax(0,1.6fr)_minmax(0,1fr)] gap-3 border-b pb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  <span>Test</span><span>Result</span><span>Against the range</span><span>Since last time</span>
                </div>
                {r.values.map((row, i) => <ValueRow key={`${row.test_name}-${i}`} row={row} />)}
                {r.values.length === 0 && <p className="py-4 text-sm text-muted-foreground">No measured values in this document.</p>}
                <p className="pt-3 text-[11px] text-muted-foreground">
                  Flags compare each value with the range printed on the report. Only your doctor can say what a result means for you.
                </p>
              </CardContent>
            </Card>
          )}
        </div>

        <div className="space-y-3 lg:sticky lg:top-4 lg:self-start">
          <h2 className="text-sm font-semibold text-foreground">Explain this report</h2>
          {explain.isPending && (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Going through the report with your history…
            </p>
          )}
          <ChatPanel
            pid={pid}
            reportId={rid}
            suggestions={REPORT_SUGGESTIONS}
            emptyText={parsed ? "Preparing the explanation…" : "The explanation appears once the report has been read."}
            placeholder="Ask about this report, e.g. 'what is TSH?'"
            className="h-[560px]"
          />
          {parsed && <DoctorQuestions pid={pid} rid={rid} />}
        </div>
      </div>
    </div>
  )
}
