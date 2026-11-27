import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import * as ep from "@/lib/endpoints"
import type { Alert } from "@/lib/endpoints"
import { Button, Card, CardContent, CardHeader, CardTitle } from "@/components/ui"
import { TONE, severityTone } from "@/lib/tone"
import { cn } from "@/lib/utils"

function fmtDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  })
}

function AlertRow({
  patientId,
  alert,
  onAck,
  acking,
}: {
  patientId: number
  alert: Alert
  onAck: (id: number) => void
  acking: boolean
}) {
  const [open, setOpen] = useState(false)
  const c = TONE[severityTone(alert.severity)]
  const ctx = useQuery({
    queryKey: ["alert-context", patientId, alert.id],
    queryFn: () => ep.getAlertContext(patientId, alert.id),
    enabled: open,
  })

  return (
    <div className="rounded-lg border border-border text-sm">
      <div className="flex items-center justify-between gap-3 px-3 py-1.5">
        <button
          onClick={() => setOpen((v) => !v)}
          className="flex flex-1 items-center gap-2.5 text-left"
          aria-expanded={open}
        >
          <span
            className={cn("text-muted-foreground transition-transform", open && "rotate-90")}
            aria-hidden
          >
            ▸
          </span>
          <span className={cn("h-2 w-2 shrink-0 rounded-full", c.dot)} />
          <span className={cn("rounded px-1.5 py-0.5 text-xs font-semibold", c.chip)}>
            {alert.severity ?? "info"}
          </span>
          <span>{alert.message}</span>
        </button>
        <Button variant="outline" onClick={() => onAck(alert.id)} disabled={acking}>
          Acknowledge
        </Button>
      </div>
      {open && (
        <div className="border-t border-border bg-background/40 px-3 py-2.5 text-xs">
          {ctx.isLoading && <p className="text-muted-foreground">Loading triggering readings…</p>}
          {ctx.isError && <p className="text-destructive">Could not load context.</p>}
          {ctx.data && (
            <div className="space-y-2">
              <p className="text-muted-foreground">
                Raised {fmtDateTime(alert.created_at)}
                {ctx.data.threshold && (
                  <>
                    {" · rule: "}
                    <span className="font-medium text-foreground">{ctx.data.threshold}</span>
                  </>
                )}
              </p>
              {ctx.data.readings.length === 0 ? (
                <p className="text-muted-foreground">No linked readings recorded.</p>
              ) : (
                <ul className="space-y-1">
                  {ctx.data.readings.map((r) => (
                    <li key={r.id} className="flex items-center justify-between gap-3">
                      <span className={cn(r.breaches ? "font-semibold text-foreground" : "text-foreground")}>
                        {r.vital_type.replace(/_/g, " ")} {r.display ?? Math.round(r.value * 10) / 10}
                        {r.unit ? ` ${r.unit}` : ""}
                        {r.breaches && (
                          <span className={cn("ml-2 rounded px-1.5 py-0.5 text-[10px] font-semibold", c.chip)}>
                            crosses threshold
                          </span>
                        )}
                      </span>
                      <span className="text-muted-foreground">{fmtDateTime(r.recorded_at)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

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
      <CardHeader className="pb-2">
        <CardTitle className="text-red-600">Alerts · {alerts.data.length}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-1.5">
        {alerts.data.map((a) => (
          <AlertRow
            key={a.id}
            patientId={patientId}
            alert={a}
            onAck={ack.mutate}
            acking={ack.isPending}
          />
        ))}
      </CardContent>
    </Card>
  )
}
