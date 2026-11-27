// Doctor visits, saved questions, reminders and the pre-visit brief (Phase 3).
import { api } from "@/lib/api"
import type { MedFinding } from "@/lib/endpoints"

export interface MedicineChange {
  action: "start" | "stop" | "change"
  name: string
  dose: string | null
  frequency: string | null
  reason: string | null
  medication_id?: number
  ingredients?: string[]
  confirmed?: boolean
}
export interface MedicineCheck {
  status: "ok" | "please_check"
  ingredients: string[]
  rxnorm: string
  medication_id: number | null
  suggested_medication_id?: number
  matched_name: string | null
  note: string | null
  suggestion: { name: string; strength: string | null; verified: boolean }[]
}
export interface VisitNote {
  reason: string | null
  discussed: string[]
  doctor_said: string[]
  medicine_changes: MedicineChange[]
  tests_ordered: { name: string; when: string | null; due_date: string | null }[]
  follow_up: { when: string | null; date: string | null } | null
  watch_for: string[]
  questions_next_time: string[]
}
export interface Visit {
  id: number
  doctor_name: string
  specialty: string | null
  visit_date: string
  source: "typed" | "voice" | "recording"
  status: "draft" | "confirmed"
  transcript: string
  structured: VisitNote
  has_audio: boolean
  confirmed_at: string | null
  medicine_checks?: MedicineCheck[]
  generated_by?: string
  applied?: string[]
}
export interface VisitListItem {
  id: number; doctor_name: string; specialty: string | null; visit_date: string
  status: "draft" | "confirmed"; source: string; reason: string | null
}
export interface Doctor { name: string; specialty: string | null; last_visit: string | null }
export interface Reminder { id: number; kind: "test" | "follow_up"; text: string; doctor_name: string | null; due_date: string | null }
export interface Brief {
  doctor: string
  generated_on: string
  since: string
  last_visit: {
    id: string; date: string; doctor: string; reason: string | null; doctor_said: string[]
    medicine_changes: MedicineChange[]; tests_ordered: { name: string; due_date: string | null }[]
    follow_up: { when: string | null; date: string | null } | null; watch_for: string[]
  } | null
  current_medicines: { name: string; dose: string | null; frequency: string | null; prescriber: string | null }[]
  symptoms_since: { name: string; count: number; dates: string[] }[]
  readings_since: Record<string, { count: number; latest: { value: number; date: string }; lowest: number; highest: number; average: number }>
  alerts_since: { date: string; message: string }[]
  reports_since: { report_id: number; type: string | null; date: string; outside_range: { test_name: string; value: string; unit: string | null; reference_range: string | null; flag: string }[] }[]
  doses_not_marked: { days: number; count: number; by_medicine: Record<string, number> }
  other_doctors_changes: { medication: string; event: string; date: string; old_dose: string | null; new_dose: string | null; prescriber: string | null }[]
  medication_findings: Pick<MedFinding, "id" | "level_label" | "severity" | "title" | "explanation" | "quote" | "source" | "medicines">[]
  questions: { id: number; text: string; source: string }[]
  reminders: { id: number; kind: string; text: string; due_date: string | null }[]
}

export const listVisits = (pid: number) => api.get<VisitListItem[]>(`/patients/${pid}/visits`).then((r) => r.data)
export const getVisit = (pid: number, vid: number) => api.get<Visit>(`/patients/${pid}/visits/${vid}`).then((r) => r.data)
export const createVisit = (pid: number, form: FormData) =>
  api.post<Visit>(`/patients/${pid}/visits`, form).then((r) => r.data)
export const updateVisit = (pid: number, vid: number, body: Partial<Pick<Visit, "doctor_name" | "specialty" | "visit_date">> & { structured?: VisitNote }) =>
  api.put<Visit>(`/patients/${pid}/visits/${vid}`, body).then((r) => r.data)
export const previewVisit = (pid: number, vid: number) =>
  api.post<{ findings: MedFinding[]; message: string | null }>(`/patients/${pid}/visits/${vid}/preview`).then((r) => r.data)
export const confirmVisit = (pid: number, vid: number) =>
  api.post<Visit>(`/patients/${pid}/visits/${vid}/confirm`).then((r) => r.data)
export const deleteVisit = (pid: number, vid: number) => api.delete(`/patients/${pid}/visits/${vid}`)
export const listDoctors = (pid: number) => api.get<Doctor[]>(`/patients/${pid}/visits/doctors`).then((r) => r.data)
export const getBrief = (pid: number, doctor: string) =>
  api.get<Brief>(`/patients/${pid}/visits/brief`, { params: { doctor } }).then((r) => r.data)
export const listReminders = (pid: number) => api.get<Reminder[]>(`/patients/${pid}/reminders`).then((r) => r.data)
export const reminderDone = (pid: number, rid: number) => api.post(`/patients/${pid}/reminders/${rid}/done`)
export const questionDone = (pid: number, qid: number) => api.post(`/patients/${pid}/questions/${qid}/done`)
export const saveQuestions = (pid: number, qs: { text: string; doctor_name?: string; source?: string; source_id?: number }[]) =>
  api.post<{ added: number }>(`/patients/${pid}/questions`, qs).then((r) => r.data)
export const getSharedDoctors = (token: string) => api.get<Doctor[]>(`/shared/${token}/doctors`).then((r) => r.data)
export const getSharedBrief = (token: string, doctor: string) =>
  api.get<Brief>(`/shared/${token}/brief`, { params: { doctor } }).then((r) => r.data)
