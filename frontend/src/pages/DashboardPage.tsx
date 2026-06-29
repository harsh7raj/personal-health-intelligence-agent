import { useQuery } from "@tanstack/react-query"
import { useAuth } from "@/lib/auth"
import * as ep from "@/lib/endpoints"
import { AlertsPanel } from "@/components/AlertsPanel"
import { SnapshotView } from "@/components/SnapshotView"

export default function DashboardPage() {
  const { patient } = useAuth()
  const pid = patient!.id
  const snap = useQuery({ queryKey: ["snapshot", pid], queryFn: () => ep.getSnapshot(pid) })

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Today's Snapshot</h1>
      <AlertsPanel patientId={pid} />
      {snap.isLoading && <p className="text-muted-foreground">Loading…</p>}
      {snap.isError && <p className="text-destructive">Could not load snapshot.</p>}
      {snap.data && <SnapshotView data={snap.data} />}
    </div>
  )
}
