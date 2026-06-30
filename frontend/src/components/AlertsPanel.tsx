import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import * as ep from "@/lib/endpoints"
import { Button, Card, CardContent, CardHeader, CardTitle } from "@/components/ui"
import { TONE, severityTone } from "@/lib/tone"
import { cn } from "@/lib/utils"

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
    <Card>
      <CardHeader>
        <CardTitle className="text-red-600">Alerts · {alerts.data.length}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {alerts.data.map((a) => {
          const c = TONE[severityTone(a.severity)]
          return (
            <div
              key={a.id}
              className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2 text-sm"
            >
              <span className="flex items-center gap-2.5">
                <span className={cn("h-2 w-2 shrink-0 rounded-full", c.dot)} />
                <span className={cn("rounded px-1.5 py-0.5 text-xs font-semibold", c.chip)}>
                  {a.severity ?? "info"}
                </span>
                {a.message}
              </span>
              <Button variant="outline" onClick={() => ack.mutate(a.id)} disabled={ack.isPending}>
                Acknowledge
              </Button>
            </div>
          )
        })}
      </CardContent>
    </Card>
  )
}
