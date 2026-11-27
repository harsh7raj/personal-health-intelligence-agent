import { useState } from "react"
import { useLocation } from "react-router-dom"
import { Pin, X } from "lucide-react"
import { useAuth } from "@/lib/auth"
import { ChatPanel } from "@/components/ChatPanel"
import { VitalQuickAdd } from "@/components/VitalQuickAdd"

/** Landing page: the assistant. Log how you feel, ask about your history; it remembers. */
export default function AssistantPage() {
  const { patient } = useAuth()
  const pid = patient!.id
  // "Ask about this" on the Medications page pins a finding for the next questions.
  const state = useLocation().state as { focus?: Record<string, unknown>; title?: string } | null
  const [pinned, setPinned] = useState(state?.focus ? { focus: state.focus, title: state.title ?? "" } : null)
  return (
    <div className="flex min-h-[calc(100vh-4rem)] flex-col gap-4 lg:h-[calc(100vh-4rem)]">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Assistant</h1>
        <p className="text-sm text-muted-foreground">
          Log symptoms and readings in your own words, or ask about your history. Every answer links to the records it came from.
        </p>
      </div>
      {pinned && (
        <div className="flex items-center gap-2 rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-900">
          <Pin className="h-4 w-4 shrink-0" /> Asking about: <span className="font-medium">{pinned.title}</span>
          <button className="ml-auto" onClick={() => setPinned(null)} aria-label="Unpin">
            <X className="h-4 w-4" />
          </button>
        </div>
      )}
      <ChatPanel
        pid={pid}
        focus={pinned?.focus}
        suggestions={pinned ? ["What does this mean for me?", "What should I ask my pharmacist?", "Can I take ibuprofen with my medicines?"] : undefined}
        className="flex-1"
      />
      <VitalQuickAdd pid={pid} />
    </div>
  )
}
