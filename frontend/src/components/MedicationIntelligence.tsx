import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { ChevronDown, Clock, Info, Pill, Sparkles } from "lucide-react"
import * as ep from "@/lib/endpoints"
import type { MedIntelMedication } from "@/lib/endpoints"
import { Card, CardContent } from "@/components/ui"
import { cn } from "@/lib/utils"

function MedRow({ m }: { m: MedIntelMedication }) {
  const [open, setOpen] = useState(false)
  const r = m.reference

  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center gap-2.5 px-3.5 py-3 text-left hover:bg-muted/50"
      >
        <Pill className="h-4 w-4 shrink-0 text-primary" />
        <span className="font-semibold capitalize text-foreground">{m.name}</span>
        {m.dose && <span className="text-xs text-muted-foreground">{m.dose}</span>}
        <span className="ml-auto flex items-center gap-2">
          <ChevronDown className={cn("h-4 w-4 text-muted-foreground transition-transform", open && "rotate-180")} />
        </span>
      </button>

      {open && (
        <div className="space-y-3 border-t border-border px-3.5 py-3 text-sm">
          {/* Per-drug reference. */}
          {r ? (
            <div className="space-y-1.5">
              {r.provenance === "ai" && (
                <span className="inline-flex items-center gap-1 rounded-full bg-violet-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-violet-700">
                  <Sparkles className="h-3 w-3" /> AI-generated
                </span>
              )}
              <p className="text-foreground">{r.used_for}</p>
              <p className="flex items-start gap-1.5 text-muted-foreground">
                <Clock className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {r.timing}
              </p>
              <p className="flex items-start gap-1.5 text-muted-foreground">
                <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {r.considerations}
              </p>
              <p className={cn("text-xs", r.provenance === "ai" ? "font-medium text-violet-700" : "text-muted-foreground")}>
                Source: {r.source}
              </p>
            </div>
          ) : (
            <p className="text-muted-foreground">
              General reference information not available for this medication — please consult the label or a pharmacist.
            </p>
          )}

        </div>
      )}
    </div>
  )
}

export function MedicationIntelligence({ patientId }: { patientId: number }) {
  const q = useQuery({ queryKey: ["med-intel", patientId], queryFn: () => ep.getMedIntel(patientId) })
  const d = q.data

  if (q.isLoading) return <p className="text-sm text-muted-foreground">Checking medications…</p>
  if (q.isError || !d) return null
  if (d.medications.length === 0) return null

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="space-y-2 pt-5">
          <p className="text-sm text-muted-foreground">General reference information. Expand a medicine for what it is commonly used for and how it is usually taken.</p>
          <div className="space-y-2">
            {d.medications.map((m) => (
              <MedRow key={m.id} m={m} />
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
