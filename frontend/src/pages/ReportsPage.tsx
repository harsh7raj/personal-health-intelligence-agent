import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useAuth } from "@/lib/auth"
import * as ep from "@/lib/endpoints"
import type { Report } from "@/lib/endpoints"
import { Button, Card, CardContent, CardHeader, CardTitle, Input } from "@/components/ui"
import { saveBlob } from "@/lib/utils"

export default function ReportsPage() {
  const { patient } = useAuth()
  const pid = patient!.id
  const qc = useQueryClient()
  const reports = useQuery({ queryKey: ["reports", pid], queryFn: () => ep.listReports(pid) })
  const [file, setFile] = useState<File | null>(null)
  const [type, setType] = useState("")

  const upload = useMutation({
    mutationFn: () => ep.uploadReport(pid, file!, type || undefined),
    onSuccess: () => {
      setFile(null)
      setType("")
      qc.invalidateQueries({ queryKey: ["reports", pid] })
    },
  })
  const del = useMutation({
    mutationFn: (rid: number) => ep.deleteReport(pid, rid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["reports", pid] }),
  })
  const dl = useMutation({
    mutationFn: async (r: Report) => {
      const blob = await ep.fetchReportBlob(pid, r.id)
      saveBlob(blob, r.filename)
    },
  })
  const list = reports.data ?? []

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight text-foreground">Lab Reports</h1>

      <Card>
        <CardHeader>
          <CardTitle>Upload report</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-2">
          <Input type="file" className="min-w-[200px] flex-1" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <Input className="w-44" placeholder="type (optional)" value={type} onChange={(e) => setType(e.target.value)} />
          <Button onClick={() => upload.mutate()} disabled={upload.isPending || !file}>
            Upload
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Uploaded reports</CardTitle>
        </CardHeader>
        <CardContent>
          {list.length === 0 ? (
            <p className="text-sm text-muted-foreground">No reports uploaded.</p>
          ) : (
            <ul className="divide-y divide-border">
              {list.map((r) => (
                <li key={r.id} className="flex items-center justify-between gap-3 py-2.5 text-sm">
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-foreground">{r.filename}</span>
                    {r.report_type && <span className="text-muted-foreground">· {r.report_type}</span>}
                    <span className="text-muted-foreground">· {new Date(r.created_at).toLocaleDateString()}</span>
                  </span>
                  <span className="flex gap-1">
                    <Button variant="outline" onClick={() => dl.mutate(r)} disabled={dl.isPending}>
                      Download
                    </Button>
                    <Button variant="ghost" className="text-destructive" onClick={() => del.mutate(r.id)} disabled={del.isPending}>
                      Remove
                    </Button>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
