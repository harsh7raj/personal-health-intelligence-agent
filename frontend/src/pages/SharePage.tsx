import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useAuth } from "@/lib/auth"
import * as ep from "@/lib/endpoints"
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input } from "@/components/ui"
import { saveBlob } from "@/lib/utils"

export default function SharePage() {
  const { patient } = useAuth()
  const pid = patient!.id
  const qc = useQueryClient()
  const tokensQ = useQuery({ queryKey: ["doctor-access", pid], queryFn: () => ep.listDoctorAccess(pid) })
  const [label, setLabel] = useState("")

  const gen = useMutation({
    mutationFn: () => ep.createDoctorAccess(pid, label || undefined),
    onSuccess: () => {
      setLabel("")
      qc.invalidateQueries({ queryKey: ["doctor-access", pid] })
    },
  })
  const revoke = useMutation({
    mutationFn: (tid: number) => ep.revokeDoctorAccess(pid, tid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["doctor-access", pid] }),
  })
  const dl = useMutation({
    mutationFn: async () => {
      const blob = await ep.fetchPdfBlob(pid)
      saveBlob(blob, `consultation_${pid}.pdf`)
    },
  })

  const origin = window.location.origin
  const tokens = tokensQ.data ?? []

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Share with a doctor</h1>
        <Button variant="outline" onClick={() => dl.mutate()} disabled={dl.isPending}>
          {dl.isPending ? "Preparing…" : "Download my PDF"}
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Generate a read-only access link</CardTitle>
        </CardHeader>
        <CardContent className="flex gap-2">
          <Input
            placeholder="doctor name / label (optional)"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
          />
          <Button onClick={() => gen.mutate()} disabled={gen.isPending}>
            Generate
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Access links</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {tokens.length === 0 && <p className="text-sm text-muted-foreground">No links yet.</p>}
          {tokens.map((t) => {
            const expired = new Date(t.expires_at) < new Date()
            const url = `${origin}/shared/${t.token}`
            return (
              <div key={t.id} className="flex items-center justify-between gap-3 border-b pb-2 text-sm">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span>{t.doctor_label || "Unnamed"}</span>
                    {t.revoked && (
                      <Badge className="border-muted-foreground/30 text-muted-foreground">revoked</Badge>
                    )}
                    {expired && !t.revoked && (
                      <Badge className="border-amber-400 text-amber-600">expired</Badge>
                    )}
                  </div>
                  {!t.revoked && !expired && (
                    <a href={url} target="_blank" rel="noreferrer" className="break-all text-primary">
                      {url}
                    </a>
                  )}
                </div>
                {!t.revoked && (
                  <Button variant="outline" onClick={() => revoke.mutate(t.id)} disabled={revoke.isPending}>
                    Revoke
                  </Button>
                )}
              </div>
            )
          })}
        </CardContent>
      </Card>
    </div>
  )
}
