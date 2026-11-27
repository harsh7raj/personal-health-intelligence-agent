import type { VitalReading } from "./endpoints"

// Human labels for vital series keys, so the UI never shows raw keys like "blood_glucose".
const LABELS: Record<string, { label: string; unit?: string }> = {
  bp_systolic: { label: "Systolic BP", unit: "mmHg" },
  bp_diastolic: { label: "Diastolic BP", unit: "mmHg" },
  blood_pressure: { label: "Blood pressure", unit: "mmHg" },
  heart_rate: { label: "Heart rate", unit: "bpm" },
  weight: { label: "Weight", unit: "kg" },
  blood_glucose: { label: "Blood glucose", unit: "mg/dL" },
  spo2: { label: "SpO₂", unit: "%" },
  temperature: { label: "Temperature" },
}

function humanize(key: string): string {
  const s = key.replace(/_/g, " ").trim()
  return s.charAt(0).toUpperCase() + s.slice(1)
}

/** Label for a vital or lab series. Lab series ("lab_ldl_cholesterol") use the report's test name. */
export function vitalLabel(vitalType: string, sample?: Pick<VitalReading, "attributes">): string {
  const known = LABELS[vitalType]
  if (known) return known.label
  if (vitalType.startsWith("lab_")) {
    const name = sample?.attributes?.test_name
    return typeof name === "string" && name ? name : humanize(vitalType.slice(4))
  }
  return humanize(vitalType)
}

export function vitalUnit(vitalType: string, sample?: Pick<VitalReading, "unit">): string | undefined {
  return sample?.unit ?? LABELS[vitalType]?.unit
}

/** Y-axis range padded around the data. Recharts starts at 0 by default, which makes
 *  small real changes (weight 72 -> 70 kg) look flat. */
export function paddedDomain(values: number[]): [number, number] | ["auto", "auto"] {
  const v = values.filter((x) => Number.isFinite(x))
  if (!v.length) return ["auto", "auto"]
  const min = Math.min(...v)
  const max = Math.max(...v)
  const pad = max > min ? (max - min) * 0.2 : Math.max(Math.abs(max) * 0.05, 1)
  const lo = Math.floor(min - pad)
  return [min >= 0 && lo < 0 ? 0 : lo, Math.ceil(max + pad)]
}
