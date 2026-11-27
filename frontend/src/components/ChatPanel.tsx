import { useEffect, useRef, useState } from "react"
import { Link } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AlertTriangle, Check, FileDown, Loader2, Send, Share2 } from "lucide-react"
import * as ep from "@/lib/endpoints"
import type { ChatEscalation, ChatEvidence, ChatMessage, LoggedTag } from "@/lib/endpoints"
import { vitalLabel } from "@/lib/vitals"
import { Button, Dialog, Textarea } from "@/components/ui"
import { cn } from "@/lib/utils"

const DEFAULT_SUGGESTIONS = [
  "How has my blood pressure been lately?",
  "When did my headaches start?",
  "What did my last report say?",
  "Headache since this morning, about 6/10",
]

function fmtDay(iso?: string | null): string {
  if (!iso) return ""
  return new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })
}

/** Short label for an evidence chip: a glossary entry's test name, else its date, else its id. */
function chipLabel(e: ChatEvidence | undefined, id: string): string {
  if (e?.kind === "glossary") return `about ${e.name ?? id}`
  return e?.date ? fmtDay(e.date) : id
}

function evidenceTitle(e: ChatEvidence): string {
  if (e.kind === "reading" || e.kind === "lab") return `${vitalLabel(e.vital_type ?? "")} ${e.value ?? ""}${e.unit ? ` ${e.unit}` : ""}`
  if (e.kind === "medication_event") {
    const change = e.event === "dose_change" ? `dose ${e.old_dose} → ${e.new_dose}` : e.event === "stop" ? "stopped" : "started"
    return `${e.medication}: ${change}`
  }
  if (e.kind === "report") return `${e.report_type ?? "Report"}`
  if (e.kind === "glossary") return `What ${e.name} measures`
  return e.name ? `Logged: ${e.name}` : "Logged entry"
}

/** Plain text with any **bold** the model slipped in shown as bold, never as asterisks. */
function Bold({ text }: { text: string }) {
  const bits = text.split(/\*\*(.+?)\*\*/g)
  return <span>{bits.map((b, j) => (j % 2 ? <strong key={j}>{b}</strong> : b))}</span>
}

function ReplyText({ text, evidence, onOpen }: { text: string; evidence: ChatEvidence[]; onOpen: (e: ChatEvidence) => void }) {
  const byId = new Map(evidence.map((e) => [e.id, e]))
  const parts = text.split(/\[([A-Z]\d+)\]/g)
  return (
    <p className="whitespace-pre-line leading-relaxed">
      {parts.map((part, i) => {
        if (i % 2 === 0) return <Bold key={i} text={part} />
        const item = byId.get(part)
        return (
          <button
            key={i}
            type="button"
            onClick={() => item && onOpen(item)}
            disabled={!item}
            className="mx-0.5 inline-flex items-center rounded-full border border-teal-300 bg-teal-50 px-1.5 py-px align-baseline text-[11px] font-medium text-teal-800 hover:bg-teal-100"
            title="Open the original record"
          >
            {chipLabel(item, part)}
          </button>
        )
      })}
    </p>
  )
}

function LoggedChip({ tag }: { tag: LoggedTag }) {
  const bits = [tag.name, tag.severity, ...tag.tags.map((t) => t.replace(/_/g, " "))].filter(Boolean)
  return (
    <div className="mb-1.5 inline-flex items-center gap-1.5 rounded-full bg-background px-2 py-0.5 text-xs text-muted-foreground">
      <Check className="h-3 w-3 text-teal-600" /> Logged: <span className="font-medium text-foreground">{bits.join(" · ")}</span>
    </div>
  )
}

function EscalationBanner({ esc, pid }: { esc: ChatEscalation; pid: number }) {
  async function openPdf() {
    const blob = await ep.fetchPdfBlob(pid)
    window.open(URL.createObjectURL(blob), "_blank")
  }
  return (
    <div className="mb-2 rounded-xl border-2 border-red-300 bg-red-50 p-3 text-sm text-red-800" role="alert">
      <div className="flex items-start gap-2">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
        <div className="space-y-2">
          <p className="font-semibold">{esc.message}</p>
          <div className="flex flex-wrap gap-2">
            <a href={`tel:${esc.call}`} className="rounded-md bg-red-600 px-3 py-1 text-xs font-semibold text-white hover:bg-red-700">
              Call {esc.call}
            </a>
            {esc.offer?.includes("consultation_pdf") && (
              <button onClick={openPdf} className="inline-flex items-center gap-1 rounded-md border border-red-300 bg-white px-3 py-1 text-xs font-medium hover:bg-red-100">
                <FileDown className="h-3.5 w-3.5" /> Doctor summary (PDF)
              </button>
            )}
            {esc.offer?.includes("share_link") && (
              <Link to="/share" className="inline-flex items-center gap-1 rounded-md border border-red-300 bg-white px-3 py-1 text-xs font-medium hover:bg-red-100">
                <Share2 className="h-3.5 w-3.5" /> Share with a doctor
              </Link>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function CriticalBanner({ lines }: { lines: string[] }) {
  return (
    <div className="mb-2 rounded-xl border-2 border-red-300 bg-red-50 p-3 text-sm font-semibold text-red-800" role="alert">
      <div className="flex items-start gap-2">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
        <div className="space-y-1">{lines.map((l) => <p key={l}>{l}</p>)}</div>
      </div>
    </div>
  )
}

function Bubble({ msg, pid, onOpen }: { msg: ChatMessage; pid: number; onOpen: (e: ChatEvidence) => void }) {
  if (msg.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-primary px-3.5 py-2 text-sm text-primary-foreground">{msg.content}</div>
      </div>
    )
  }
  return (
    <div className="max-w-[88%]">
      {msg.meta?.escalation && <EscalationBanner esc={msg.meta.escalation} pid={pid} />}
      {msg.meta?.critical && msg.meta.critical.length > 0 && <CriticalBanner lines={msg.meta.critical} />}
      <div className="rounded-2xl rounded-bl-sm border border-border bg-muted px-3.5 py-2.5 text-sm text-foreground">
        {msg.meta?.logged_entry && <LoggedChip tag={msg.meta.logged_entry} />}
        <ReplyText text={msg.content} evidence={msg.evidence ?? []} onOpen={onOpen} />
      </div>
    </div>
  )
}

/** The assistant chat. Reusable: the same panel opens beside reports/medicines (focus). */
export function ChatPanel({
  pid,
  reportId,
  suggestions = DEFAULT_SUGGESTIONS,
  emptyText,
  placeholder = "e.g. 'feeling shaky, skipped lunch' or 'how has my sugar been this month?'",
  className,
}: {
  pid: number
  /** Pin a report: its own thread, and follow-ups answered with that report in view. */
  reportId?: number
  suggestions?: string[]
  emptyText?: string
  placeholder?: string
  className?: string
}) {
  const qc = useQueryClient()
  const focus = reportId ? { type: "report", id: reportId } : undefined
  const history = useQuery({ queryKey: ["chat", pid, reportId ?? "all"], queryFn: () => ep.getChatHistory(pid, reportId) })
  const [text, setText] = useState("")
  const [pendingText, setPendingText] = useState<string | null>(null)
  const [open, setOpen] = useState<ChatEvidence | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  const send = useMutation({
    mutationFn: (message: string) => ep.sendChat(pid, message, focus),
    onMutate: (message) => setPendingText(message),
    onSettled: () => {
      setPendingText(null)
      qc.invalidateQueries() // the thread, plus dashboard data a log may have changed
    },
  })
  const messages = history.data ?? []

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages.length, pendingText])

  function submit(message: string) {
    const m = message.trim()
    if (!m || send.isPending) return
    setText("")
    send.mutate(m)
  }

  return (
    <div className={cn("flex min-h-0 flex-col gap-3", className)}>
      <div className="min-h-[340px] flex-1 space-y-4 overflow-y-auto rounded-xl border border-border bg-card p-4">
        {history.isLoading ? (
          <p className="text-sm text-muted-foreground">Loading your conversation…</p>
        ) : messages.length === 0 && !pendingText ? (
          <p className="text-sm text-muted-foreground">
            {emptyText ??
              "Tell me how you're feeling or log a reading, or ask about your history. I'll answer from your own records, with dates."}
          </p>
        ) : (
          messages.map((m) => <Bubble key={m.id} msg={m} pid={pid} onOpen={setOpen} />)
        )}
        {pendingText && (
          <>
            <div className="flex justify-end">
              <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-primary/80 px-3.5 py-2 text-sm text-primary-foreground">{pendingText}</div>
            </div>
            <div className="inline-flex items-center gap-2 rounded-2xl border border-border bg-muted px-3.5 py-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Looking through your history…
            </div>
          </>
        )}
        {send.isError && <p className="text-sm text-destructive">Something went wrong. Please try again.</p>}
        <div ref={bottomRef} />
      </div>

      <div className="space-y-2">
        <div className="flex gap-2">
          <Textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={placeholder}
            className="min-h-[44px]"
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault()
                submit(text)
              }
            }}
          />
          <Button onClick={() => submit(text)} disabled={send.isPending || !text.trim()} aria-label="Send">
            <Send className="h-4 w-4" />
          </Button>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {suggestions.map((s) => (
            <button
              key={s}
              onClick={() => submit(s)}
              disabled={send.isPending}
              className="rounded-full border border-border px-2.5 py-1 text-xs text-muted-foreground transition hover:bg-accent hover:text-foreground"
            >
              {s}
            </button>
          ))}
        </div>
        <p className="text-[11px] text-muted-foreground">Observations from your records, not a diagnosis. In an emergency call 112.</p>
      </div>

      {open && (
        <Dialog open onClose={() => setOpen(null)} title={evidenceTitle(open)}>
          <div className="space-y-2 text-sm">
            <p className="text-muted-foreground">
              {fmtDay(open.date)}
              {open.time ? ` · ${open.time}` : ""}
            </p>
            {open.text && <p className="text-foreground">“{open.text}”</p>}
            {open.kind === "glossary" && (
              <>
                <p className="text-foreground">{open.measures}</p>
                {open.url && (
                  <a href={open.url} target="_blank" rel="noreferrer" className="text-primary underline">
                    More on MedlinePlus
                  </a>
                )}
              </>
            )}
            {open.kind === "report" && open.report_id && (
              <Link to={`/reports/${open.report_id}`} className="text-primary underline">
                Open the report
              </Link>
            )}
            <p className="text-xs text-muted-foreground">Evidence {open.id}</p>
          </div>
        </Dialog>
      )}
    </div>
  )
}
