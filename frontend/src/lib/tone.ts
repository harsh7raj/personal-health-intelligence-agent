// Consistent visual coding for trend/severity used across cards, badges, charts.
export type Tone = "up" | "down" | "flat" | "danger"

export function trendTone(t?: string | null): Tone {
  if (t === "rising" || t === "increasing") return "up"
  if (t === "falling" || t === "decreasing") return "down"
  return "flat"
}

export function severityTone(sev?: string | null): Tone {
  if (sev === "critical") return "danger"
  if (sev === "high") return "up"
  return "flat"
}

export const TONE: Record<
  Tone,
  { text: string; chip: string; dot: string; stroke: string; arrow: string; label: string }
> = {
  up: { text: "text-amber-700", chip: "bg-amber-100 text-amber-700", dot: "bg-amber-500", stroke: "#d97706", arrow: "↑", label: "rising" },
  down: { text: "text-blue-700", chip: "bg-blue-100 text-blue-700", dot: "bg-blue-500", stroke: "#2563eb", arrow: "↓", label: "falling" },
  flat: { text: "text-slate-600", chip: "bg-slate-100 text-slate-600", dot: "bg-slate-400", stroke: "#475569", arrow: "→", label: "stable" },
  danger: { text: "text-red-700", chip: "bg-red-100 text-red-700", dot: "bg-red-500", stroke: "#dc2626", arrow: "!", label: "alert" },
}
