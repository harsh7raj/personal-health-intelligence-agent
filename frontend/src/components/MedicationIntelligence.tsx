import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { AlertTriangle, ChevronDown, Clock, Info, Pill, ShieldAlert, Sparkles } from "lucide-react"
import * as ep from "@/lib/endpoints"
import type { MedIntel, MedIntelInteraction, MedIntelMedication } from "@/lib/endpoints"
import { Card, CardContent } from "@/components/ui"
import { cn } from "@/lib/utils"

const LEVEL_STYLE: Record<string, { chip: string; label: string; rank: number }> = {
  Major: { chip: "bg-red-100 text-red-700", label: "Major", rank: 0 },
  Moderate: { chip: "bg-amber-100 text-amber-700", label: "Moderate", rank: 1 },
  Minor: { chip: "bg-blue-100 text-blue-700", label: "Minor", rank: 2 },
  Unknown: { chip: "bg-slate-100 text-slate-600", label: "Severity not classified", rank: 3 },
}
const levelStyle = (level: string | null) => LEVEL_STYLE[level ?? "Unknown"] ?? LEVEL_STYLE.Unknown

function Disclaimer({ text }: { text: string }) {
  return (
    <div className="flex items-start gap-2.5 rounded-lg border border-amber-300 bg-amber-50 p-3.5 text-sm text-amber-900">
      <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />
      <p>{text}</p>
    </div>
  )
}

// All interactions touching `medName`, with the partner drug resolved to "the other side".
function partnersOf(medName: string, interactions: MedIntelInteraction[]) {
  return interactions
    .filter((it) => it.drug_a === medName || it.drug_b === medName)
    .map((it) => ({ ...it, other: it.drug_a === medName ? it.drug_b : it.drug_a }))
}

function MedRow({ m, d }: { m: MedIntelMedication; d: MedIntel }) {
  const [open, setOpen] = useState(false)
  const r = m.reference
  const partners = partnersOf(m.name, d.interactions)
  const known = partners.filter((p) => p.status === "known")
  const noneCount = partners.filter((p) => p.status === "none_known").length
  // Highest-severity known interaction drives the collapsed summary chip.
  const top = known.slice().sort((a, b) => levelStyle(a.level).rank - levelStyle(b.level).rank)[0]

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
          {known.length > 0 ? (
            <span className={cn("rounded-full px-2 py-0.5 text-xs font-semibold", levelStyle(top.level).chip)}>
              {known.length} interaction{known.length === 1 ? "" : "s"}
            </span>
          ) : (
            <span className="text-xs text-muted-foreground">No known interactions</span>
          )}
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

          {/* Interactions involving this medication. */}
          <div className="border-t border-border pt-2.5">
            <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              With your other medications
            </p>
            {known.length === 0 && partners.every((p) => p.status !== "same_drug") ? (
              <p className="text-xs text-muted-foreground">
                No known interaction found with your other medications in DDInter 2.0 — this is not a guarantee they are
                safe together.
              </p>
            ) : (
              <ul className="space-y-1.5">
                {known.map((p, i) => (
                  <li key={i} className="flex flex-wrap items-center gap-2">
                    <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-amber-600" />
                    <span className="text-foreground">with {p.other}</span>
                    <span className={cn("rounded-full px-2 py-0.5 text-xs font-semibold", levelStyle(p.level).chip)}>
                      {levelStyle(p.level).label}
                    </span>
                    <span className="w-full pl-5 text-xs text-muted-foreground">{p.advice}</span>
                  </li>
                ))}
                {partners
                  .filter((p) => p.status === "same_drug")
                  .map((p, i) => (
                    <li key={`s${i}`} className="text-xs text-muted-foreground">
                      Same medication as {p.other} (brand/generic) — not a separate interaction.
                    </li>
                  ))}
                {noneCount > 0 && (
                  <li className="text-xs text-muted-foreground">
                    No known interaction found with {noneCount} other medication{noneCount === 1 ? "" : "s"} in DDInter 2.0.
                  </li>
                )}
              </ul>
            )}
          </div>
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
      <Disclaimer text={d.disclaimer} />

      <Card>
        <CardContent className="space-y-2 pt-5">
          <p className="text-sm text-muted-foreground">
            {d.known_interaction_count} known interaction{d.known_interaction_count === 1 ? "" : "s"} across{" "}
            {d.pairs_checked} checked pair{d.pairs_checked === 1 ? "" : "s"}. Expand a medication for its reference info
            and any interactions.
          </p>
          <div className="space-y-2">
            {d.medications.map((m) => (
              <MedRow key={m.id} m={m} d={d} />
            ))}
          </div>
          <p className="border-t border-border pt-2 text-xs text-muted-foreground">
            Interaction data source: {d.interaction_source}. Flags are known, sourced entries — not the system's own
            judgement. Absence of a flag means none was found in this dataset, not that a combination is safe.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
