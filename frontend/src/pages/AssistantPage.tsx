import { useAuth } from "@/lib/auth"
import { ChatPanel } from "@/components/ChatPanel"
import { VitalQuickAdd } from "@/components/VitalQuickAdd"

/** Landing page: the assistant. Log how you feel, ask about your history; it remembers. */
export default function AssistantPage() {
  const { patient } = useAuth()
  const pid = patient!.id
  return (
    <div className="flex min-h-[calc(100vh-4rem)] flex-col gap-4 lg:h-[calc(100vh-4rem)]">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Assistant</h1>
        <p className="text-sm text-muted-foreground">
          Log symptoms and readings in your own words, or ask about your history. Every answer links to the records it came from.
        </p>
      </div>
      <ChatPanel pid={pid} className="flex-1" />
      <VitalQuickAdd pid={pid} />
    </div>
  )
}
