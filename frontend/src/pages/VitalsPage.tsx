import { useQuery } from "@tanstack/react-query"
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { useAuth } from "@/lib/auth"
import * as ep from "@/lib/endpoints"
import type { VitalReading, VitalSummary } from "@/lib/endpoints"
import { Badge, Card, CardContent, CardHeader, CardTitle } from "@/components/ui"
import { cn } from "@/lib/utils"

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" })
}

function TrendBadge({ s }: { s?: VitalSummary }) {
  if (!s || !s.trend) return null
  const arrow = s.trend === "rising" ? "↑" : s.trend === "falling" ? "↓" : "→"
  const cls =
    s.trend === "rising"
      ? "border-amber-400 text-amber-600"
      : s.trend === "falling"
        ? "border-blue-400 text-blue-600"
        : "border-muted-foreground/30 text-muted-foreground"
  const delta = s.delta_pct != null ? ` ${(s.delta_pct * 100).toFixed(0)}%` : ""
  return (
    <Badge className={cn(cls)}>
      {arrow} {s.trend}
      {delta}
    </Badge>
  )
}

function buildBP(readings: VitalReading[]) {
  const map = new Map<string, { t: string; ts: number; systolic?: number; diastolic?: number }>()
  for (const r of readings) {
    if (r.vital_type !== "bp_systolic" && r.vital_type !== "bp_diastolic") continue
    const entry = map.get(r.recorded_at) ?? {
      t: fmtTime(r.recorded_at),
      ts: new Date(r.recorded_at).getTime(),
    }
    if (r.vital_type === "bp_systolic") entry.systolic = r.value
    else entry.diastolic = r.value
    map.set(r.recorded_at, entry)
  }
  return Array.from(map.values()).sort((a, b) => a.ts - b.ts)
}

export default function VitalsPage() {
  const { patient } = useAuth()
  const pid = patient!.id
  const readingsQ = useQuery({ queryKey: ["vitals", pid], queryFn: () => ep.listVitals(pid) })
  const summaryQ = useQuery({ queryKey: ["vitals-summary", pid], queryFn: () => ep.getVitalsSummary(pid) })

  if (readingsQ.isLoading) return <p className="text-muted-foreground">Loading…</p>
  const readings = readingsQ.data ?? []
  const summaries = summaryQ.data ?? []
  const summaryFor = (vt: string) => summaries.find((s) => s.vital_type === vt)

  if (readings.length === 0) {
    return (
      <div className="space-y-4">
        <h1 className="text-xl font-semibold">Vitals</h1>
        <p className="text-muted-foreground">No readings yet — add some on the Log page.</p>
      </div>
    )
  }

  const types = Array.from(new Set(readings.map((r) => r.vital_type)))
  const hasBP = types.includes("bp_systolic") || types.includes("bp_diastolic")
  const otherTypes = types.filter((t) => t !== "bp_systolic" && t !== "bp_diastolic")
  const bpData = buildBP(readings)

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Vitals</h1>
      <p className="text-xs text-muted-foreground">Arrow/colour shows trend direction, not a clinical judgment.</p>

      {hasBP && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-sm">Blood pressure</CardTitle>
            <div className="flex gap-2">
              <TrendBadge s={summaryFor("bp_systolic")} />
              <TrendBadge s={summaryFor("bp_diastolic")} />
            </div>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={bpData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="t" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="systolic" stroke="#dc2626" />
                <Line type="monotone" dataKey="diastolic" stroke="#2563eb" />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {otherTypes.map((vt) => {
        const data = readings
          .filter((r) => r.vital_type === vt)
          .map((r) => ({ t: fmtTime(r.recorded_at), value: r.value }))
        return (
          <Card key={vt}>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-sm">{vt}</CardTitle>
              <TrendBadge s={summaryFor(vt)} />
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={data}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="t" />
                  <YAxis />
                  <Tooltip />
                  <Line type="monotone" dataKey="value" stroke="#16a34a" />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}
