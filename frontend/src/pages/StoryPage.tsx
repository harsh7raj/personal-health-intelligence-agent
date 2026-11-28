import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { BookOpen, Loader2, RefreshCw } from "lucide-react"
import { useAuth } from "@/lib/auth"
import { api } from "@/lib/api"
import { Badge, Button, Card, CardContent } from "@/components/ui"

interface DetailedStory {
  sections: { title: string; body: string }[]
  generated_by: "llm" | "fallback"
  generated_at: string
  based_on?: { problems: number; medicines: number; lab_results: number; visits: number }
}
const getStory = (pid: number, refresh = false) =>
  api.get<DetailedStory>(`/patients/${pid}/story/detailed`, { params: { refresh } }).then((r) => r.data)

export default function StoryPage() {
  const { patient } = useAuth()
  const pid = patient!.id
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ["story-detailed", pid], queryFn: () => getStory(pid), staleTime: 5 * 60_000 })
  const regen = useMutation({
    mutationFn: () => getStory(pid, true),
    onSuccess: (d) => qc.setQueryData(["story-detailed", pid], d),
  })
  const d = q.data
  const busy = q.isLoading || regen.isPending

  return (
    <div className="max-w-3xl space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Your health story</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Everything in your record, told as one story: patterns, medicines, readings, lab results and what your doctors said.
          </p>
        </div>
        <Button variant="outline" onClick={() => regen.mutate()} disabled={busy}>
          <RefreshCw className={busy ? "h-4 w-4 animate-spin" : "h-4 w-4"} /> Regenerate
        </Button>
      </div>

      {busy && !d && (
        <Card>
          <CardContent className="flex items-center gap-2 py-10 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Reading through your whole record… this takes about 20 seconds the first time.
          </CardContent>
        </Card>
      )}

      {d && (
        <>
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <BookOpen className="h-3.5 w-3.5" />
            Written {new Date(d.generated_at).toLocaleString()}
            {d.based_on && (
              <span>
                · from {d.based_on.problems} symptoms, {d.based_on.medicines} medicines, {d.based_on.lab_results} lab results and{" "}
                {d.based_on.visits} visit notes
              </span>
            )}
            {d.generated_by === "fallback" && (
              <Badge className="border-amber-400 text-amber-700">Short summary: the AI story couldn't be written right now</Badge>
            )}
          </div>
          <div className="space-y-4">
            {d.sections.map((s) => (
              <Card key={s.title}>
                <CardContent className="space-y-2 pt-5">
                  <h2 className="text-base font-semibold text-foreground">{s.title}</h2>
                  <p className="whitespace-pre-line text-sm leading-relaxed text-foreground">{s.body}</p>
                </CardContent>
              </Card>
            ))}
          </div>
          <p className="text-xs text-muted-foreground">
            Written by AI from your own records, checked for diagnosis wording. Not a diagnosis; your doctor can say what it means for you.
          </p>
        </>
      )}
      {q.isError && <p className="text-sm text-destructive">Couldn't load your story.</p>}
    </div>
  )
}
