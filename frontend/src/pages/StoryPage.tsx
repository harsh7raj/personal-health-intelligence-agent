import { useQuery } from "@tanstack/react-query"
import { useAuth } from "@/lib/auth"
import * as ep from "@/lib/endpoints"
import { Badge, Button, Card, CardContent, CardHeader, CardTitle } from "@/components/ui"

export default function StoryPage() {
  const { patient } = useAuth()
  const pid = patient!.id
  const q = useQuery({ queryKey: ["story", pid], queryFn: () => ep.getStory(pid) })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Your Health Story</h1>
        <Button variant="outline" onClick={() => q.refetch()} disabled={q.isFetching}>
          {q.isFetching ? "Generating…" : "Regenerate"}
        </Button>
      </div>
      {q.isLoading && <p className="text-muted-foreground">Generating…</p>}
      {q.data && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-sm">Narrative</CardTitle>
            {q.data.generated_by === "fallback" && (
              <Badge className="border-amber-400 text-amber-600">
                Offline summary — AI narrative unavailable
              </Badge>
            )}
          </CardHeader>
          <CardContent>
            <p className="whitespace-pre-line text-sm leading-relaxed">{q.data.story}</p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
