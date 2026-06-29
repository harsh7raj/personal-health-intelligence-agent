import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import * as ep from "@/lib/endpoints"
import { Badge, Button, Card, CardContent, CardHeader, CardTitle } from "@/components/ui"

export function AlertsPanel({ patientId }: { patientId: number }) {
  const qc = useQueryClient()
  const alerts = useQuery({
    queryKey: ["alerts", patientId, "unack"],
    queryFn: () => ep.listAlerts(patientId, true),
  })
  const ack = useMutation({
    mutationFn: (aid: number) => ep.ackAlert(patientId, aid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts", patientId] }),
  })

  if (!alerts.data || alerts.data.length === 0) return null

  return (
    <Card className="border-destructive/40">
      <CardHeader>
        <CardTitle className="text-destructive">Alerts ({alerts.data.length})</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {alerts.data.map((a) => (
          <div key={a.id} className="flex items-center justify-between gap-3 text-sm">
            <span>
              <Badge className="mr-2 border-destructive/40 text-destructive">{a.severity ?? "info"}</Badge>
              {a.message}
            </span>
            <Button variant="outline" onClick={() => ack.mutate(a.id)} disabled={ack.isPending}>
              Acknowledge
            </Button>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}
