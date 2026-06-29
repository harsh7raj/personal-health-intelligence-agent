import { useParams } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import * as ep from "@/lib/endpoints"
import { Button, Card, CardContent, CardHeader, CardTitle } from "@/components/ui"
import { SnapshotView } from "@/components/SnapshotView"

export default function DoctorViewPage() {
  const { token = "" } = useParams()
  const snapQ = useQuery({
    queryKey: ["shared-snap", token],
    queryFn: () => ep.getSharedSnapshot(token),
    retry: false,
  })
  const storyQ = useQuery({
    queryKey: ["shared-story", token],
    queryFn: () => ep.getSharedStory(token),
    retry: false,
  })

  if (snapQ.isError) {
    return (
      <div className="p-10 text-center text-muted-foreground">
        This share link is invalid, expired, or has been revoked.
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">
          Patient Summary{" "}
          <span className="text-sm font-normal text-muted-foreground">(shared, read-only)</span>
        </h1>
        <a href={ep.sharedPdfUrl(token)} target="_blank" rel="noreferrer">
          <Button variant="outline">Download PDF</Button>
        </a>
      </div>
      {snapQ.data && <SnapshotView data={snapQ.data} />}
      {storyQ.data && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Health Story</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="whitespace-pre-line text-sm leading-relaxed">{storyQ.data.story}</p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
