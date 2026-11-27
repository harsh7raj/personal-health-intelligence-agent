import type { ReactNode } from "react"
import type { Brief } from "@/lib/visits"
import { vitalLabel } from "@/lib/vitals"

const fmt = (iso?: string | null) =>
  iso ? new Date(`${iso.slice(0, 10)}T12:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : ""

function Section({ title, children, empty }: { title: string; children: ReactNode; empty?: boolean }) {
  return (
    <section className="break-inside-avoid space-y-1.5 border-t border-border pt-3">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">{title}</h3>
      {empty ? <p className="text-sm text-muted-foreground">Nothing recorded.</p> : children}
    </section>
  )
}

/** The pre-visit brief: built in code from the record, the same for the patient and the doctor link. */
export function BriefView({ b }: { b: Brief }) {
  const lv = b.last_visit
  const readings = Object.entries(b.readings_since)
  return (
    <div className="space-y-4 text-sm text-foreground">
      <div>
        <h2 className="text-xl font-bold">Pre-visit brief: {b.doctor}</h2>
        <p className="text-muted-foreground">
          Prepared {fmt(b.generated_on)} · covers {lv ? `since the last visit on ${fmt(lv.date)}` : `the last 90 days (since ${fmt(b.since)})`}.
          From the patient's own records; not a diagnosis.
        </p>
      </div>

      <Section title="Last visit" empty={!lv}>
        {lv && (
          <div className="space-y-1">
            <p>
              <b>{fmt(lv.date)}</b>
              {lv.reason ? ` · ${lv.reason}` : ""}
            </p>
            <ul className="list-disc pl-5">{lv.doctor_said.map((t) => <li key={t}>{t}</li>)}</ul>
            {lv.medicine_changes.length > 0 && (
              <p>Medicine changes: {lv.medicine_changes.map((c) => `${c.action} ${c.name}${c.dose ? ` ${c.dose}` : ""}`).join("; ")}</p>
            )}
            {lv.watch_for.length > 0 && <p>Asked to watch for: {lv.watch_for.join("; ")}</p>}
          </div>
        )}
      </Section>

      <Section title="Current medicines" empty={b.current_medicines.length === 0}>
        <ul className="list-disc pl-5">
          {b.current_medicines.map((m) => (
            <li key={m.name}>
              {m.name} {m.dose ?? ""} {m.frequency ? `· ${m.frequency}` : ""} {m.prescriber ? `· ${m.prescriber}` : ""}
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Changed by other doctors since then" empty={b.other_doctors_changes.length === 0}>
        <ul className="list-disc pl-5">
          {b.other_doctors_changes.map((c, i) => (
            <li key={i}>
              {fmt(c.date)}: {c.medication} {c.event === "dose_change" ? `${c.old_dose} → ${c.new_dose}` : c.event}
              {c.prescriber ? ` (${c.prescriber})` : ""}
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Symptoms logged since" empty={b.symptoms_since.length === 0}>
        <ul className="list-disc pl-5">
          {b.symptoms_since.map((s) => (
            <li key={s.name}>
              {s.name}: {s.count}× ({s.dates.slice(-4).map(fmt).join(", ")})
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Readings since" empty={readings.length === 0 && b.alerts_since.length === 0}>
        <ul className="list-disc pl-5">
          {readings.map(([vt, r]) => (
            <li key={vt}>
              {vitalLabel(vt)}: {r.count} readings, average {r.average}, range {r.lowest}–{r.highest}, latest {r.latest.value} ({fmt(r.latest.date)})
            </li>
          ))}
          {b.alerts_since.map((a, i) => <li key={`a${i}`}>{fmt(a.date)}: {a.message}</li>)}
        </ul>
      </Section>

      <Section title="Reports since" empty={b.reports_since.length === 0}>
        <ul className="list-disc pl-5">
          {b.reports_since.map((r) => (
            <li key={r.report_id}>
              {r.type ?? "Report"} ({fmt(r.date)})
              {r.outside_range.length > 0 &&
                `: ${r.outside_range.map((v) => `${v.test_name} ${v.value}${v.unit ? ` ${v.unit}` : ""} (${v.flag}, range ${v.reference_range ?? "?"})`).join("; ")}`}
            </li>
          ))}
        </ul>
      </Section>

      <Section title={`Doses not marked as taken (last ${b.doses_not_marked.days} days)`} empty={b.doses_not_marked.count === 0}>
        <p>
          {b.doses_not_marked.count} in total:{" "}
          {Object.entries(b.doses_not_marked.by_medicine).map(([m, n]) => `${m} ${n}`).join(", ")}. (Not marked may also mean not ticked.)
        </p>
      </Section>

      <Section title="Open medication findings" empty={b.medication_findings.length === 0}>
        <ul className="list-disc pl-5">
          {b.medication_findings.map((f) => (
            <li key={f.id}>
              <b>{f.level_label}{f.severity ? ` · ${f.severity}` : ""}:</b> {f.title}. {f.explanation}
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Reminders" empty={b.reminders.length === 0}>
        <ul className="list-disc pl-5">
          {b.reminders.map((r) => <li key={r.id}>{r.text}{r.due_date ? ` · due ${fmt(r.due_date)}` : ""}</li>)}
        </ul>
      </Section>

      <Section title="Questions to ask" empty={b.questions.length === 0}>
        <ol className="list-decimal pl-5">{b.questions.map((q) => <li key={q.id}>{q.text}</li>)}</ol>
      </Section>
    </div>
  )
}
