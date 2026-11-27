import { Link, useSearchParams } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { ArrowLeft, Loader2, Printer, Share2 } from "lucide-react"
import { useAuth } from "@/lib/auth"
import * as vi from "@/lib/visits"
import { BriefView } from "@/components/BriefView"
import { Button, Card, CardContent } from "@/components/ui"

export default function BriefPage() {
  const { patient } = useAuth()
  const pid = patient!.id
  const doctor = useSearchParams()[0].get("doctor") ?? ""
  const q = useQuery({ queryKey: ["brief", pid, doctor], queryFn: () => vi.getBrief(pid, doctor), enabled: doctor.length > 1 })
  return (
    <div className="max-w-4xl space-y-4">
      <div className="flex flex-wrap items-center gap-2 print:hidden">
        <Link to="/visits" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="h-4 w-4" /> Visits</Link>
        <Button variant="outline" className="ml-auto" onClick={() => window.print()}><Printer className="h-4 w-4" /> Print</Button>
        <Link to="/share"><Button variant="outline"><Share2 className="h-4 w-4" /> Share with the doctor</Button></Link>
      </div>
      {q.isLoading ? (
        <p className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Preparing the brief…</p>
      ) : q.data ? (
        <Card className="print:border-0 print:shadow-none"><CardContent className="pt-5"><BriefView b={q.data} /></CardContent></Card>
      ) : (
        <p className="text-sm text-destructive">Couldn't prepare the brief.</p>
      )}
      <p className="text-xs text-muted-foreground print:hidden">The doctor link from Share shows this brief too (read-only).</p>
    </div>
  )
}
