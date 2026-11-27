import { useEffect, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AlertTriangle, Download, FileText, Loader2, MessageSquareText, RotateCw, Sparkles, Trash2 } from "lucide-react"
import { useAuth } from "@/lib/auth"
import * as ep from "@/lib/endpoints"
import type { FlaggedValue, Report, ReportStatus } from "@/lib/endpoints"
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input } from "@/components/ui"
import { cn, saveBlob } from "@/lib/utils"
import { TONE, type Tone } from "@/lib/tone"

const fmtDate = (d?: string | null) => (d ? new Date(d).toLocaleDateString() : null)

// Poll while any report is still working its way to a terminal state, so the
// card updates from "parsing" -> "indexed"/"failed" without a manual reload.
const isPending = (s: ReportStatus) => s === "uploaded" || s === "parsing"

// Map backend status -> user-facing label + badge styling. The requirement's
// progression is Uploaded -> Parsing -> Indexed; the backend's terminal success
// state ("parsed") is where the report has also been indexed into the vector store.
const STATUS_META: Record<ReportStatus, { label: string; className: string }> = {
  uploaded: { label: "Uploaded", className: "border-transparent bg-slate-100 text-slate-600" },
  parsing: { label: "Parsing", className: "border-transparent bg-secondary text-secondary-foreground" },
  parsed: { label: "Indexed", className: "border-transparent bg-primary/10 text-primary" },
  failed: { label: "Failed", className: "border-transparent bg-red-100 text-red-700" },
}

// High/low reuse the app-wide trend coding (amber = up/high, blue = down/low);
// anything else (e.g. "unknown") reads as neutral.
function flagTone(flag: string): Tone {
  if (flag === "high") return "up"
  if (flag === "low") return "down"
  return "flat"
}

function StatusBadge({ status }: { status: ReportStatus }) {
  const meta = STATUS_META[status]
  return (
    <Badge className={meta.className}>
      {isPending(status) && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
      {meta.label}
    </Badge>
  )
}

function FlaggedValueChip({ v }: { v: FlaggedValue }) {
  const tone = TONE[flagTone(v.flag)]
  return (
    <div className={cn("rounded-lg border px-3 py-2", tone.chip)}>
      <div className="flex items-baseline gap-1.5">
        <span className="text-sm font-semibold">
          {v.value ?? "—"}
          {v.unit ? <span className="ml-0.5 text-xs font-normal">{v.unit}</span> : null}
        </span>
        <span className="text-xs font-medium uppercase tracking-wide opacity-80">
          {tone.arrow} {v.flag}
        </span>
      </div>
      <div className="text-xs font-medium opacity-90">{v.test_name}</div>
      {v.reference_range && (
        <div className="text-[11px] opacity-70">ref {v.reference_range}</div>
      )}
    </div>
  )
}

function ReportCard({
  report,
  onDownload,
  onDelete,
  onRetry,
  onExplain,
  busy,
}: {
  report: Report
  onDownload: (r: Report) => void
  onDelete: (rid: number) => void
  onRetry: (rid: number) => void
  onExplain: (rid: number) => void
  busy: boolean
}) {
  const testDate = fmtDate(report.test_date)
  const uploadDate = fmtDate(report.created_at)
  const extraFlagged = report.flagged_count - report.flagged_values.length

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-2.5">
            <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent text-primary">
              <FileText className="h-4 w-4" />
            </span>
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold text-foreground">{report.filename}</div>
              <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted-foreground">
                {testDate ? <span>Test date {testDate}</span> : uploadDate && <span>Uploaded {uploadDate}</span>}
                {testDate && uploadDate && <span>· uploaded {uploadDate}</span>}
              </div>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {report.report_type && (
              <Badge className="border-transparent bg-slate-100 text-slate-600">{report.report_type}</Badge>
            )}
            <StatusBadge status={report.status} />
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {report.status === "failed" ? (
          <div className="flex flex-wrap items-start justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5">
            <div className="flex min-w-0 items-start gap-2 text-sm text-red-700">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span className="min-w-0">{report.parse_error ?? "Couldn't read this report."}</span>
            </div>
            <Button variant="outline" onClick={() => onRetry(report.id)} disabled={busy} className="shrink-0">
              <RotateCw className={cn("h-3.5 w-3.5", busy && "animate-spin")} /> Retry
            </Button>
          </div>
        ) : isPending(report.status) ? (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Pulling out the key numbers…
          </p>
        ) : (
          <>
            {report.critical_count > 0 && (
              <div className="flex items-start gap-2 rounded-lg border-2 border-red-300 bg-red-50 px-3 py-2.5 text-sm font-semibold text-red-800" role="alert">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>
                  {report.critical_count === 1 ? "A value is" : `${report.critical_count} values are`} beyond the level where
                  labs advise contacting a doctor the same day. Please contact your doctor today.
                </span>
              </div>
            )}
            {report.ai_summary && (
              <p className="flex items-start gap-2 text-sm leading-relaxed text-foreground">
                <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                <span>{report.ai_summary}</span>
              </p>
            )}
            {report.flagged_values.length > 0 && (
              <div>
                <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Flagged values
                </div>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                  {report.flagged_values.map((v, i) => (
                    <FlaggedValueChip key={`${v.test_name}-${i}`} v={v} />
                  ))}
                </div>
                {extraFlagged > 0 && (
                  <div className="mt-1.5 text-xs text-muted-foreground">
                    +{extraFlagged} more flagged {extraFlagged === 1 ? "value" : "values"}
                  </div>
                )}
              </div>
            )}
            {report.status === "parsed" && !report.ai_summary && report.flagged_values.length === 0 && (
              <p className="text-sm text-muted-foreground">
                No lab values were flagged — nothing outside the reference ranges.
              </p>
            )}
          </>
        )}

        <div className="flex items-center gap-1 border-t pt-3">
          {report.status === "parsed" && (
            <Button onClick={() => onExplain(report.id)}>
              <MessageSquareText className="h-3.5 w-3.5" /> Explain this report
            </Button>
          )}
          <Button variant="ghost" onClick={() => onDownload(report)} disabled={busy}>
            <Download className="h-3.5 w-3.5" /> Original file
          </Button>
          <Button variant="ghost" className="ml-auto text-destructive" onClick={() => onDelete(report.id)} disabled={busy}>
            <Trash2 className="h-3.5 w-3.5" /> Remove
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

export default function ReportsPage() {
  const { patient } = useAuth()
  const pid = patient!.id
  const qc = useQueryClient()
  const reports = useQuery({
    queryKey: ["reports", pid],
    queryFn: () => ep.listReports(pid),
    // Keep refetching while anything is still uploading/parsing; stop once every
    // report has reached a terminal state.
    refetchInterval: (query) =>
      (query.state.data ?? []).some((r) => isPending(r.status)) ? 2500 : false,
  })
  const [file, setFile] = useState<File | null>(null)
  const [type, setType] = useState("")
  const navigate = useNavigate()
  const justUploaded = useRef<number | null>(null)

  const invalidate = () => qc.invalidateQueries({ queryKey: ["reports", pid] })

  const upload = useMutation({
    mutationFn: () => ep.uploadReport(pid, file!, type || undefined),
    onSuccess: (created: { id: number }) => {
      justUploaded.current = created.id
      setFile(null)
      setType("")
      invalidate()
    },
  })

  // When the report uploaded here finishes processing, open it with its explanation.
  useEffect(() => {
    const done = (reports.data ?? []).find((r) => r.id === justUploaded.current && r.status === "parsed")
    if (done) {
      justUploaded.current = null
      navigate(`/reports/${done.id}`)
    }
  }, [reports.data, navigate])
  const del = useMutation({
    mutationFn: (rid: number) => ep.deleteReport(pid, rid),
    onSuccess: invalidate,
  })
  const dl = useMutation({
    mutationFn: async (r: Report) => {
      const blob = await ep.fetchReportBlob(pid, r.id)
      saveBlob(blob, r.filename)
    },
  })
  const retry = useMutation({
    mutationFn: (rid: number) => ep.retryReport(pid, rid),
    onSuccess: invalidate,
  })

  const list = reports.data ?? []
  const busyId = del.variables ?? retry.variables ?? dl.variables?.id

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Lab Reports</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Upload a lab report and I'll pull out the key numbers and tell you what's changed.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Upload a report</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <Input
              type="file"
              accept=".pdf,.txt,image/jpeg,image/png,image/webp"
              className="min-w-[200px] flex-1"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            <Input
              className="w-44"
              placeholder="type (optional)"
              value={type}
              onChange={(e) => setType(e.target.value)}
            />
            <Button onClick={() => upload.mutate()} disabled={upload.isPending || !file}>
              {upload.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Upload
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            PDF, scanned PDF or a phone photo of a lab report. I'll read the values, compare each with its printed
            range and your earlier reports, and open an explanation when it's ready.
          </p>
        </CardContent>
      </Card>

      {reports.isLoading ? (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading reports…
        </p>
      ) : list.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 py-12 text-center">
            <span className="flex h-11 w-11 items-center justify-center rounded-full bg-accent text-primary">
              <FileText className="h-5 w-5" />
            </span>
            <p className="text-sm font-medium text-foreground">No reports yet</p>
            <p className="max-w-sm text-sm text-muted-foreground">
              Upload a lab report and I'll pull out the key numbers, flag anything outside its normal
              range, and tell you what's changed since last time.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {list.map((r) => (
            <ReportCard
              key={r.id}
              report={r}
              onDownload={(rep) => dl.mutate(rep)}
              onDelete={(rid) => del.mutate(rid)}
              onRetry={(rid) => retry.mutate(rid)}
              onExplain={(rid) => navigate(`/reports/${rid}`)}
              busy={busyId === r.id && (del.isPending || retry.isPending || dl.isPending)}
            />
          ))}
        </div>
      )}
    </div>
  )
}
