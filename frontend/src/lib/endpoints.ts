import { api } from "./api"

// ---------- Types (mirror backend DTOs) ----------
export interface User { id: number; email: string; role: string }
export interface Patient {
  id: number; name: string; age?: number | null; sex?: string | null
  height?: number | null; weight?: number | null; blood_group?: string | null
  contact?: string | null; attributes: Record<string, unknown>
  created_at: string; updated_at: string
}
export interface Background {
  patient_id: number; conditions: string[]; allergies: string[]
  family_history: string[]; surgical_history: string[]; lifestyle: Record<string, unknown>
}
export interface SnapshotProblem { name: string; severity: string | null; frequency: string | null; trend: string | null }
export interface Snapshot {
  patient_id: number; active_problems: SnapshotProblem[]; recent_changes: string[]
  observations: string[]; missing_information: string[]; suggested_next_actions: string[]
}
export interface Story { story: string; generated_by: "llm" | "fallback" }
export interface Alert {
  id: number; kind: string; message: string; severity: string | null
  vital_type: string | null; acknowledged: boolean; created_at: string
}
export interface VitalReading {
  id: number; patient_id: number; vital_type: string; value: number
  unit: string | null; recorded_at: string; created_at: string
}
export interface VitalSummary {
  vital_type: string; latest: number | null; recent_avg: number | null
  baseline_avg: number | null; delta_pct: number | null; trend: string | null
}
export interface Medication {
  id: number; patient_id: number; name: string; dose: string | null
  frequency: string | null; dose_times: string[]; interval_days: number; purpose: string | null
  started_on: string | null; active: boolean
  attributes: Record<string, unknown>; created_at: string; updated_at: string
}
export interface Symptom {
  id: number; patient_id: number; type: string; raw_text: string | null
  structured: Record<string, unknown>; source: string | null; created_at: string
}
export interface Problem {
  id: number; name: string; severity: string | null; frequency: string | null
  trend: string | null; status: string; first_seen: string | null
  last_seen: string | null; resolved_at: string | null; attributes: Record<string, unknown>
}
export interface Observation { id: number; text: string; created_at: string }
export interface DoctorAccess {
  id: number; token: string; doctor_label: string | null
  expires_at: string; revoked: boolean; created_at: string
}
export interface SemanticMatch {
  text: string
  metadata: { entry_id?: number; type?: string; date?: string }
  distance: number
}
export interface ReasoningSummary {
  entry_type?: string
  problem?: string | null
  vitals_updated?: string[]
  alerts?: { kind: string; vital_type?: string | null; message: string }[]
  observations?: string[]
  suggested_actions?: string[]
  resolved?: string[]
}
export interface NewEntry {
  entry_id: number
  type: string
  name: string | null
  structured: Record<string, unknown>
  raw_text: string
}
export interface IntakeResult {
  status: "processed" | "clarification_needed"
  question?: string | null
  new_entry?: NewEntry | null
  context_bundle?: { semantic_matches?: SemanticMatch[] } & Record<string, unknown> | null
  reasoning_summary?: ReasoningSummary | null
}
export interface HistoryEntry {
  id: number
  patient_id: number
  type: string
  raw_text: string | null
  structured: Record<string, unknown>
  source: string | null
  created_at: string
}
export interface TimelineEntryDetail {
  id: number; type: string; raw_text: string | null
  structured: Record<string, unknown>; source: string | null; created_at: string
}
export interface TimelineVitalDetail {
  id: number; vital_type: string; value: number; unit: string | null; recorded_at: string
}
export interface TimelineObservationDetail { id: number; text: string; created_at: string }
export interface TimelineAlertDetail {
  id: number; kind: string; message: string; severity: string | null
  vital_type: string | null; created_at: string
}
export interface TimelineDetail {
  date: string; window_days: number
  entries: TimelineEntryDetail[]
  vital_readings: TimelineVitalDetail[]
  observations: TimelineObservationDetail[]
  alerts: TimelineAlertDetail[]
}
export interface AlertContextReading {
  id: number; vital_type: string; value: number; unit: string | null
  recorded_at: string; breaches: boolean
}
export interface AlertContext {
  alert: Alert; threshold: string | null; readings: AlertContextReading[]
}
export interface ProblemTimelinePoint {
  date: string
  kind: "first_seen" | "episode" | "reading" | "trend_change" | "resolved"
  label: string; detail: string | null; severity: string | null; entry_id: number | null
}
export interface ProblemTimeline {
  problem: {
    id: number; name: string; status: string; severity: string | null
    frequency: string | null; trend: string | null
    first_seen: string | null; last_seen: string | null; resolved_at: string | null
    episode_count: number
  }
  points: ProblemTimelinePoint[]
}

// ---------- Auth ----------
export async function login(email: string, password: string): Promise<string> {
  const body = new URLSearchParams({ username: email, password })
  const { data } = await api.post<{ access_token: string }>("/auth/login", body)
  return data.access_token
}
export async function register(email: string, password: string): Promise<User> {
  const { data } = await api.post<User>("/auth/register", { email, password })
  return data
}
export const getMe = () => api.get<User>("/auth/me").then((r) => r.data)
export const getMyPatient = () => api.get<Patient>("/patients/me").then((r) => r.data)
export const createPatient = (p: Partial<Patient>) =>
  api.post<Patient>("/patients", p).then((r) => r.data)
export const updatePatient = (id: number, p: Partial<Patient>) =>
  api.put<Patient>(`/patients/${id}`, p).then((r) => r.data)

// ---------- Background ----------
export const getBackground = (id: number) =>
  api.get<Background>(`/patients/${id}/background`).then((r) => r.data)
export const putBackground = (id: number, b: Partial<Background>) =>
  api.put<Background>(`/patients/${id}/background`, b).then((r) => r.data)

// ---------- Intake ----------
export const postIntake = (id: number, raw_text: string) =>
  api.post<IntakeResult>(`/patients/${id}/intake`, { raw_text }).then((r) => r.data)
export const postIntakeAnswer = (id: number, raw_text: string, answer: string) =>
  api.post<IntakeResult>(`/patients/${id}/intake/answer`, { raw_text, answer }).then((r) => r.data)

// ---------- Structured entry ----------
export const listVitals = (id: number) =>
  api.get<VitalReading[]>(`/patients/${id}/vitals`).then((r) => r.data)
export const getVitalsSummary = (id: number) =>
  api.get<VitalSummary[]>(`/patients/${id}/vitals/summary`).then((r) => r.data)
export const createVital = (id: number, v: { vital_type: string; value: number; unit?: string }) =>
  api.post<VitalReading>(`/patients/${id}/vitals`, v).then((r) => r.data)
export const listMedications = (id: number) =>
  api.get<Medication[]>(`/patients/${id}/medications`).then((r) => r.data)
export interface DrugReference {
  used_for: string; timing: string; considerations: string; source: string
  provenance: "medlineplus" | "ai"
}
export interface MedIntelMedication {
  id: number; name: string; dose: string | null; normalized: string; reference: DrugReference | null
}
export interface MedIntelInteraction {
  drug_a: string; drug_b: string; status: "known" | "none_known" | "same_drug"
  level: string | null; source: string; advice?: string | null; note?: string | null
}
export interface MedIntel {
  medications: MedIntelMedication[]
  interactions: MedIntelInteraction[]
  known_interaction_count: number
  pairs_checked: number
  disclaimer: string
  interaction_source: string
  reference_source_url: string
}
export const getMedIntel = (id: number) =>
  api.get<MedIntel>(`/patients/${id}/medications/intelligence`).then((r) => r.data)

// ---------- Medication dose tracker (2-week rolling calendar) ----------
export interface DoseSlot {
  medication_id: number; name: string; dose: string | null; time: string
  timing: string | null; taken: boolean; markable: boolean
}
export interface CalendarDay {
  date: string; is_today: boolean; is_future: boolean; slots: DoseSlot[]
}
export interface CalendarMedication {
  id: number; name: string; dose: string | null; purpose: string; color_index: number
}
export interface CalendarGroup { purpose: string; medications: CalendarMedication[] }
export interface MedCalendar {
  start_date: string; end_date: string; today: string
  days: CalendarDay[]; groups: CalendarGroup[]; medication_count: number; disclaimer: string
}
export const getMedCalendar = (id: number) =>
  api.get<MedCalendar>(`/patients/${id}/medications/calendar`).then((r) => r.data)
export const markDoseTaken = (
  id: number, medId: number, slot: { scheduled_date: string; scheduled_time: string },
) => api.post(`/patients/${id}/medications/${medId}/doses`, slot)
export const unmarkDose = (
  id: number, medId: number, slot: { scheduled_date: string; scheduled_time: string },
) => api.delete(`/patients/${id}/medications/${medId}/doses`, { data: slot })
export const createMedication = (
  id: number,
  m: { name: string; dose?: string; frequency?: string; dose_times?: string[]; purpose?: string },
) =>
  api.post<Medication>(`/patients/${id}/medications`, m).then((r) => r.data)
export const deleteMedication = (id: number, mid: number) =>
  api.delete(`/patients/${id}/medications/${mid}`)
export const listSymptoms = (id: number) =>
  api.get<Symptom[]>(`/patients/${id}/symptoms`).then((r) => r.data)
export const listEntries = (id: number, limit = 100, offset = 0) =>
  api.get<HistoryEntry[]>(`/patients/${id}/entries`, { params: { limit, offset } }).then((r) => r.data)
export interface Report {
  id: number
  patient_id: number
  filename: string
  report_type: string | null
  summary: string | null
  created_at: string
}
export const listReports = (id: number) =>
  api.get<Report[]>(`/patients/${id}/reports`).then((r) => r.data)
export const uploadReport = (id: number, file: File, report_type?: string, summary?: string) => {
  const fd = new FormData()
  fd.append("file", file)
  if (report_type) fd.append("report_type", report_type)
  if (summary) fd.append("summary", summary)
  return api.post(`/patients/${id}/reports`, fd).then((r) => r.data)
}
export const deleteReport = (id: number, rid: number) =>
  api.delete(`/patients/${id}/reports/${rid}`)
export const fetchReportBlob = (id: number, rid: number) =>
  api.get(`/patients/${id}/reports/${rid}/file`, { responseType: "blob" }).then((r) => r.data as Blob)

// ---------- Outputs ----------
export const getSnapshot = (id: number, obsLimit?: number) =>
  api
    .get<Snapshot>(`/patients/${id}/snapshot`, {
      params: obsLimit ? { obs_limit: obsLimit } : undefined,
    })
    .then((r) => r.data)
export const getTimelineDetail = (id: number, day: string, windowDays = 1, start?: string) =>
  api
    .get<TimelineDetail>(`/patients/${id}/timeline/${day}/detail`, {
      params: start ? { start } : { window_days: windowDays },
    })
    .then((r) => r.data)
export const getStory = (id: number) =>
  api.get<Story>(`/patients/${id}/story`).then((r) => r.data)
export const getProblems = (id: number) =>
  api.get<Problem[]>(`/patients/${id}/problems`).then((r) => r.data)
export const getObservations = (id: number) =>
  api.get<Observation[]>(`/patients/${id}/observations`).then((r) => r.data)
export const fetchPdfBlob = (id: number) =>
  api.get(`/patients/${id}/consultation/pdf`, { responseType: "blob" }).then((r) => r.data as Blob)

// ---------- Alerts ----------
export const listAlerts = (id: number, unacknowledged = false) =>
  api.get<Alert[]>(`/patients/${id}/alerts`, { params: { unacknowledged } }).then((r) => r.data)
export const ackAlert = (id: number, aid: number) =>
  api.post<Alert>(`/patients/${id}/alerts/${aid}/ack`).then((r) => r.data)
export const getAlertContext = (id: number, aid: number) =>
  api.get<AlertContext>(`/patients/${id}/alerts/${aid}/context`).then((r) => r.data)
export const getProblemTimeline = (id: number, problemId: number) =>
  api.get<ProblemTimeline>(`/patients/${id}/problems/${problemId}/timeline`).then((r) => r.data)

// ---------- Doctor access ----------
export const listDoctorAccess = (id: number) =>
  api.get<DoctorAccess[]>(`/patients/${id}/doctor-access`).then((r) => r.data)
export const createDoctorAccess = (id: number, doctor_label?: string, expires_in_days = 7) =>
  api.post<DoctorAccess>(`/patients/${id}/doctor-access`, { doctor_label, expires_in_days }).then((r) => r.data)
export const revokeDoctorAccess = (id: number, tokenId: number) =>
  api.delete(`/patients/${id}/doctor-access/${tokenId}`)

// ---------- Shared (token-gated, no auth) ----------
export const getSharedSnapshot = (token: string) =>
  api.get<Snapshot>(`/shared/${token}/snapshot`).then((r) => r.data)
export const getSharedStory = (token: string) =>
  api.get<Story>(`/shared/${token}/story`).then((r) => r.data)
export const sharedPdfUrl = (token: string) => `${import.meta.env.VITE_API_BASE ?? "/api"}/shared/${token}/consultation/pdf`
