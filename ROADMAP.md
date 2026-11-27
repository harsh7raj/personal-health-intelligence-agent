# Personal Health Intelligence Agent: v2 Roadmap

Everything we need to do for the next evaluation, in order.

**How to use this file**
- Tick boxes as you go (`- [x]`). Keep `memory.md` as the log of *decisions*; this file is the list of *tasks*.
- Effort estimates are rough, for one person working with an AI coding assistant.
- If you use a coding agent, point it at this file and `memory.md`, and work one section at a time.

---

## Goals (what we were asked to do)

1. **Add strong AI features:**
   - a chat assistant that remembers your history (Phase 2),
   - doctor visit recaps (Phase 3),
   - a report explainer (Phase 4),
   - smarter medication safety (Phase 5).
2. **Make the existing project better:** fix the bugs (Phase 1) and overhaul the UI (Phase 6).
3. **Build 3 demo-ready patients:** months of realistic synthetic history that shows off all of the above (Phase 7).

## Ground rules (must stay true everywhere)

- **Observe, never diagnose.** No diagnoses, causes, or treatment advice from the AI.
- **Code finds the pattern, the AI writes the words.** Retrieval, counting, date-matching, and safety thresholds are handled in Python. The LLM only phrases what it is handed.
- **Every AI claim shows its evidence.** Replies cite dated entries, report values, or quoted label text that the user can click.
- **The doctor's words are labeled as the doctor's.** The app relays a doctor's instructions; it never invents its own.
- **For medicines, the AI can raise a concern but can never give the all-clear.** The app never says two drugs are "safe" together.
- **Every medication finding says where it came from:** Verified (database), Official label (quoted), or AI flag (unverified).
- **Nothing medical is saved without the user confirming it** (visit notes, medicine changes, brand-to-generic matches).
- **Runs locally with one command, and still works if LiteLLM is down** (Groq fallback).

## Model plan (via LiteLLM)

| Task | Model |
|---|---|
| Sorting a message into log / question / both | Haiku |
| Parsing a log into structured data | Haiku |
| Extracting values from text PDFs | Haiku |
| Suggesting the generic name for a brand (e.g. Thyronorm → levothyroxine) | Haiku |
| Reading report photos and scans | Sonnet (vision) |
| Chat assistant replies, including the report explainer | Sonnet |
| Reading drug labels and quoting the relevant sentence | Sonnet |
| AI interaction flags (unverified level) | Sonnet |
| Turning visit recaps into notes | Sonnet |
| Health story | Sonnet |
| Generating the synthetic patients (one-time, cached) | Sonnet |
| Speech-to-text for visit recaps | Whisper `whisper-large-v3-turbo` on Groq (free tier) |
| Fallback for everything above | Groq `llama-3.3-70b-versatile` |

## Data sources

| Source | Used for | Notes |
|---|---|---|
| DDInter 2.0 | Verified drug–drug pairs with severity | Already imported into `drug_interactions`. CC BY-NC-SA 4.0: cite it, non-commercial only. |
| RxNorm (NLM) | Medicine name → ingredient | Already used in `services/rxnorm.py`. Covers US drugs only, so Indian brand names need mapping (Phase 5). |
| RxClass (NLM) | Drug classes, for spotting duplicates and class-level label matches | New. Free API. |
| openFDA drug labels | Official text on interactions, warnings, side effects, and how to take each drug | New. Free API. Cache locally and show openFDA's own "don't rely on this for medical decisions" disclaimer. |
| MedlinePlus (NLM) | Plain-language explanations of tests and medicines | A curated glossary with links. MedlinePlus Connect lookups need LOINC codes, so they're optional. |
| ~~RxNav interaction API~~ | — | Shut down in January 2024. Don't use it. |

Budget notes are at the end of this file.

---

## Phase 0: Setup (~half a day)

- [x] Create a `v2` branch and keep `main` demo-able. *(Local repo: `main` = untouched v1; never pushed.)*
- [x] Get the current app running locally as a baseline: `docker compose up -d`, migrations, seed. Run the backend on port **8001** (Chroma's container already uses 8000) and the frontend on 5173. *(On the Windows machine: portable Postgres instead of Docker, see README; found and fixed two Windows-only bugs: PDF date format and the DDInter import.)*
- [ ] Confirm the LiteLLM proxy URL, your key, and the exact model names it exposes (`GET <proxy-url>/v1/models`).
- [ ] Write `scripts/llm_smoke_test.py`: one JSON-mode call each to Sonnet and Haiku through the proxy. The code uses `response_format={"type": "json_object"}` everywhere, so confirm this works before building on it. *(Written on top of `llm.py`, which also tolerates fenced/chatty JSON; run it once the keys are in `.env`.)*
- [ ] Get a free Groq key for Whisper and the fallback.
- [ ] Optional: get a free openFDA API key for higher rate limits.

---

## Phase 1: Fix the foundations (~1–2 days)

### Setup and infrastructure
- [x] Fix the README run steps (uvicorn on `--port 8001`) and add a single start command or script. *(`uv run python -m scripts.dev`)*
- [x] Locally, use `CHROMA_MODE=embedded` (already supported in `app/vectorstore/chroma.py`) and drop the Chroma container. If you keep the container, pin its image version instead of `latest`.
- [x] Rewrite `app/core/llm.py`: replace `groq_client()` / `groq_json()` with one `llm_json(task, system, user)` that:
  - picks the model for the task from config,
  - calls LiteLLM,
  - falls back to Groq on any error,
  - logs tokens and estimated cost per call.
- [x] Update `app/core/config.py` and `.env.example` with `LLM_BASE_URL`, `LLM_API_KEY`, `MODEL_FAST` (Haiku), `MODEL_SMART` (Sonnet), `MODEL_VISION`, `FALLBACK_BASE_URL`, `FALLBACK_API_KEY`, `STT_MODEL`, `OPENFDA_API_KEY`, and `MED_AI_FLAGS_ENABLED`.
- [x] Add `app/core/clock.py` with a `now()` that can be overridden, and use it instead of direct `datetime.now(...)` calls. This lets the demo replay simulate past dates (Phase 7).
  - Files: `services/problems.py`, `clusters.py`, `missing_info.py`, `state_assembler.py`, `vitals_trend.py`, `report_extraction.py`, `pdf_report.py`, `graph/nodes/intake.py`, `memory.py`, `api/routes/vitals.py`.
  - Leave auth on real time: `core/security.py`, `api/deps.py`, and doctor-access token expiry.

### Data and logic bugs
- [x] **Backdating.** Entries only have `created_at`, so "I had a migraine yesterday" is stored as today.
  - Add `occurred_at` to `entries` (migration; default = `created_at`).
  - Have intake pull out the onset ("yesterday", "since Monday", "last night") and resolve it to a date.
  - Use `occurred_at` for the timeline, clustering, problems, and the Chroma `date` metadata.
- [x] **Context tags at intake.** Extract tags like skipped meal, poor sleep, stress, missed dose, alcohol, exercise, and travel as structured fields. The recurrence detector (Phase 2) needs these to find shared circumstances.
- [x] **Missing info and suggested actions never clear.** `services/missing_info.py` only inserts.
  - Resolve "No blood pressure reading in 60 days" when a BP reading is logged.
  - Add `POST .../suggested-actions/{id}/dismiss` and a dismiss button.
- [x] **Problem matching.** `services/problems.py` matches the exact lowercase string, so "headache", "headaches", and "head pain" become three problems. Have intake output a canonical symptom name (prompt plus a small synonym map) and match on that and the aliases.
- [x] **Problem trend.** Right now trend becomes `"increasing"` at 3 total episodes and can never go down. Compute it from frequency instead: last 30 days vs the 30–90 days before, giving increasing / stable / decreasing.
- [x] **Clustering.** `services/clusters.py` treats every symptom from the last 48h as one set, so a third symptom creates a brand-new cluster and repeated logs double-count. Instead, count symptom *pairs* that occur within 48h of each other (by `occurred_at`), once per episode.
- [x] **Language guard.** In `services/language_guard.py`:
  - `\byou have\b` drops harmless lines like "you have logged 3 headaches". Narrow it to "you have" followed by a condition word.
  - Exempt clearly attributed doctor statements in visit notes, so "Dr. Rao diagnosed…" isn't dropped.
  - Add tests for both directions.
- [x] **One BP alert per reading.** `services/alerts.py` creates separate systolic and diastolic alerts for one reading. Make it a single "BP 147/92 is above the alert threshold" alert.
- [x] **Medication history.** The `medications` table only stores `started_on`; dose changes overwrite the old dose. Add a `medication_events` table (start / stop / dose change, date, old → new, prescriber, source: manual or visit note). The assistant and the side-effect check both need it.
- [x] **Prescriber per medicine.** Add `prescriber` (doctor name and specialty) to medications so duplicates and clashes between doctors can be detected (Phase 5).
- [x] **Timezones.** `services/med_schedule.py` uses naive `date.today()`. Align it with the rest of the app: store in UTC, display in IST.

### Pipeline gaps
- [x] **Questions get treated as incomplete logs.** Add a router step before intake that labels each message log / question / both (Haiku). Questions skip saving and go straight to the assistant (Phase 2). *(Until Phase 2, questions get a short holding reply.)*
- [x] **Observations ignore past entries.** `services/observations.py` only gets aggregates and report chunks. Also pass it the dated past matches the memory node retrieves.
- [ ] **The Response agent is empty.** `graph/nodes/response.py` is a pass-through. It becomes the assistant reply in Phase 2. *(Phase 2 work.)*
- [ ] **The demo's observations are fake.** `scripts/seed_demo.py` inserts hardcoded strings. This gets replaced by the Phase 7 replay. *(Phase 7 work.)*

### Visible bugs (from the report screenshots)
- [ ] The story fallback prints `None` ("vitamin D deficiency (None, stable)") in `services/story.py::_fallback_story`. Fix it, and make the LLM story actually run. *(`None` fixed; a real LLM story check waits for the keys.)*
- [x] Vitals chart titles show raw keys ("BLOOD_GLUCOSE") because `pages/VitalsPage.tsx` renders `{vt}`. Add a label map.
- [x] Every chart's y-axis starts at 0, so weight looks flat. Use a padded automatic range.
- [x] Every seeded entry shows the same time (1:53 AM) because the seed uses "now minus N days". Give entries realistic times of day.
- [x] The dashboard timeline shows only the oldest events. Show recent events first, or make it scrollable.

---

## Phase 2: Chat assistant with memory (~3–4 days) ⭐ main new feature

**Goal:** the patient talks to it. It logs things, answers questions, and remembers, always with dates as evidence. This one engine also powers the report explainer (Phase 4) and the medication explanations (Phase 5).

### Backend
- [ ] Add `POST /patients/{id}/chat`, returning `{reply, evidence[], logged_entry?, escalation?}`. Accept an optional `focus` (e.g. `{type: "report", id: 12}`) so other pages can open the assistant with something pinned.
- [ ] Store turns in a new `chat_messages` table so follow-ups like "and before that?" work.
- [ ] Update the LangGraph flow and diagram:
  - logs go `router → intake → memory → reasoning → response`,
  - questions go `router → memory → response`,
  - **response = the assistant reply.**
- [ ] Write retrieval functions in plain Python (also usable as LLM tools):
  - `symptom_history(name)`: every past episode, from canonical name, synonyms, and semantic matches, with dates and original text. Search **all** history, not just the 180-day window.
  - `around(date, hours=48)`: what else was logged near a date (meals, missed doses, readings, sleep, stress).
  - `vital_series(type, days)` and `lab_series(test)`.
  - `medication_events(days)` and `missed_doses(days)`.
  - `reports(type)` and `visit_notes(doctor=None)`.
  - `med_check(drug_a, drug_b)` and `side_effect_check(symptom)` (from Phase 5).
  - `search(text)`: semantic search over entries, reports, and visit notes.
- [ ] Build a recurrence detector in `services/recurrence.py`, with no LLM. For a new symptom it finds:
  - how many prior episodes there were, their dates, and the gaps between them,
  - factors shared across episodes (e.g. "skipped meal within 6h", "dose taken that morning", "glucose < 70 within 24h"),
  - timing relative to medication events (e.g. "all 3 came after the dose change on …").
- [ ] Assemble an **evidence pack**: compact JSON of facts, entry IDs, and dates. Sonnet writes the reply from this pack only and must cite entry IDs. Reject any reply that cites an ID not in the pack.
- [ ] **Doctor's instructions:** if a confirmed visit note has a relevant instruction, quote it with attribution ("Dr. Rao said on 12 Aug: …").
- [ ] **Question mode:** answer things like "How has my sugar been this month?", "When did the headaches start?", or "What did my last thyroid report say?" from the retrieval functions, with citations.

### Safety
- [ ] Check red-flag rules in code *before* calling the LLM:
  - chest pain or tightness on exertion,
  - fainting,
  - one-sided weakness, face droop, or slurred speech,
  - severe breathlessness,
  - glucose < 54, or low-sugar symptoms with confusion,
  - BP ≥ 180/120,
  - SpO₂ < 92,
  - thoughts of self-harm.
- [ ] When a red flag fires, show a fixed escalation banner above the reply: "get medical help now / call 112", or Tele-MANAS 14416 for mental health. Verify both numbers before the demo.
- [ ] Run the non-diagnostic guard on every reply. If it trips, fall back to a plain list of the facts.
- [ ] Cap cost and speed: Haiku for the router, one Sonnet call per reply (two at most), the system prompt cached. Aim for replies under 5 seconds.

### Frontend
- [ ] Turn the Log page into the Assistant chat and make it the landing page:
  - user bubble and assistant bubble,
  - a small "Logged: migraine · moderate" tag,
  - date chips that open the original entry,
  - a red banner for escalations.
- [ ] Show suggested prompts under the input box.
- [ ] Add a loading state ("Looking through your history…").
- [ ] Build the chat as a reusable component, so the same chat can open as a side panel on the report and medication pages.

### Done when
- [ ] Harsh's climax message gives the expected reply 5 runs in a row (Phase 7).
- [ ] Every date in a reply links to a real entry.
- [ ] Red-flag test messages always escalate.

---

## Phase 3: Doctor visit recaps (~2–3 days)

**Goal:** right after a visit, the patient records or types what happened. The app turns it into a clean note that feeds the memory.

- [ ] Add a `visits` table: `doctor_name`, `specialty`, `visit_date`, `source` (voice / typed / recording), `transcript`, `audio_path`, `structured` (JSON), and `status` (draft / confirmed).
- [ ] Input: record in the browser (MediaRecorder), upload an audio file, or type the recap. Whisper on Groq turns audio into a transcript.
- [ ] Sonnet structures the transcript into:
  - reason for the visit,
  - what was discussed,
  - what the doctor said (attributed),
  - medicine changes (start / stop / change, with dose),
  - tests ordered,
  - follow-up date,
  - things to watch for,
  - questions for next time.
- [ ] Map brand names to generics and flag names that don't match RxNorm as "please check" (Phase 5). Speech-to-text mishears names like glimepiride vs glipizide.
- [ ] Add a review screen where the user edits and confirms. On confirm:
  - apply medicine changes to `medications` and `medication_events`, with this doctor as prescriber,
  - create reminders for tests and follow-ups,
  - embed the note so the assistant can recall it,
  - run the medication safety check (Phase 5) on the updated list.
- [ ] **Clashes between doctors:** if one doctor's new medicine interacts with or duplicates another doctor's, show it on the review screen and in the next pre-visit brief.
- [ ] **Pre-visit brief** for each doctor:
  - what happened at the last visit,
  - what's changed since (symptoms, readings, reports, adherence, other doctors' changes),
  - open medication findings,
  - the questions you saved (including ones saved from the report explainer),
  - printable, and shareable through the existing doctor link.
- [ ] **Consent:** before recording, show "Ask your doctor before recording." Make the self-recap the default option.
- [ ] Add pages: visits list, visit detail, the record/recap flow, and the pre-visit brief.

---

## Phase 4: Report explainer (~2–3 days)

**Goal:** upload a report and a chat panel opens that explains it in plain language, using the patient's own history. It's the Phase 2 assistant opened with the report pinned, not a separate chatbot.

### Extraction upgrades
The analyzer already exists (`services/report_extraction.py`, `services/report_indexing.py`), but it's basic and barely visible.
- [ ] **Photos and scans.** Accept JPG/PNG and image-only PDFs. Render PDF pages to images, send them to the vision model, and keep the same JSON output. This replaces the current `OcrRequiredError` dead end.
- [ ] **More report types.** Today there are only Lipid Panel, CBC, Thyroid Panel, Discharge Summary, Prescription, and Other. Add HbA1c / diabetes panel, kidney function, liver function, vitamins (D, B12), and urine routine.
- [ ] **Test-name aliases** so that, for example, "LDL-C" and "LDL Cholesterol (Direct)" trend as one series.
- [ ] **Numeric ranges.** Store each value's reference range as numbers (low / high) where possible, so the UI can draw range bars.
- [ ] **Critical values, decided in code.** Keep a curated list of dangerous values (very high or low potassium, sodium, glucose, very low hemoglobin or platelets) that triggers a "contact your doctor today" banner. Get the thresholds checked by your guide or a doctor.

### Explainer chat
- [ ] Open the explainer automatically when a report finishes processing, and from an "Explain this report" button on any report.
- [ ] The first message is generated automatically and covers:
  - what the report covers,
  - which values are outside the range, and by how much,
  - how each repeated test has changed since the previous report,
  - what each flagged test measures (from the glossary),
  - related things the patient has logged (symptoms, medicines and their purpose), framed as "worth discussing together", never as a cause.
- [ ] Handle follow-up questions:
  - "What is TSH?": explain from the glossary.
  - "Is this bad?": say where it sits against the range, how it's trending, and who to ask. No good/bad verdict.
  - "Why could this be high?": give general factors from the glossary, never "yours is high because…".
  - "How does this compare to last time?": answer from the trend data.
- [ ] **"What should I ask my doctor?"** generates questions, and one tap saves them to the pre-visit brief (Phase 3).
- [ ] Context the model gets (all citable): the extracted values, the raw report text, previous values for the same tests, conditions, current medicines, and related symptoms with dates.
- [ ] **Glossary** in `app/data/lab_glossary.py`: about 40 common tests, each with what it measures, general reasons it can be high or low, and typical units, plus MedlinePlus links. Curate it the same way as `data/drug_reference.py`.
- [ ] Safety: run the non-diagnostic guard on every reply, show any critical-value banner first, and never interpret beyond the printed range and the patient's record.

### Report page
- [ ] Add a full report page using the existing `GET /patients/{id}/reports/{rid}`, which the frontend currently never calls:
  - every value with a range bar, its flag, the previous value, and the change,
  - the explainer chat as a side panel.

---

## Phase 5: Medication safety upgrade (~2–3 days)

**Goal:** go beyond a pair lookup. Use official sources, use the patient's context, and be honest about how sure we are.

**The rule:** the AI can raise a concern, but it can never give the all-clear. A missed interaction is far worse than an extra question to the pharmacist. And an AI flag must never push someone to stop a medicine on their own.

### Sources and plumbing
- [ ] **Brand names to generics.** When RxNorm doesn't recognize a name (e.g. Indian brands like "Thyronorm 75" or "Shelcal"):
  - Haiku suggests the generic ingredients (levothyroxine 75 mcg; calcium carbonate + vitamin D3),
  - the user confirms,
  - the generics are checked against RxNorm,
  - `brand_name` and `ingredients[]` are stored on the medicine, and every check runs on ingredients.
- [ ] **Label service** (`services/drug_labels.py`): for each ingredient, fetch the openFDA label sections for drug interactions, warnings and precautions, contraindications, adverse reactions, and dosage and administration. Cache them in a `drug_labels` table with a fetched date, so the demo works offline.
- [ ] **Class service** (`services/drug_classes.py`): look up each ingredient's classes on RxClass (ATC class, mechanism, e.g. "CYP3A4 inhibitors") and cache them.

### Three-level pair check
Build `services/med_safety.py`, extending `services/med_intel.py`. For each pair of medicines:
- [ ] **Level 1, Verified:** the pair is in DDInter. Show the severity.
- [ ] **Level 2, Official label:** the pair isn't in DDInter, but one drug's label mentions the other drug, its ingredient, or one of its classes.
  - The AI reads the label sections and must return the exact sentence.
  - Code checks that the quoted sentence really appears in the cached label text, and discards the finding if it doesn't.
- [ ] **Level 3, AI flag (unverified):** nothing in the sources, but the AI sees a possible concern.
  - Show it with its reasoning, labeled "Unverified, ask your pharmacist", plus "Don't stop or change any medicine on your own."
  - Put this level behind `MED_AI_FLAGS_ENABLED`, so you can switch to sourced-only if your guide prefers.
- [ ] If nothing fires, say exactly: "No known interaction found in our sources. Confirm with your pharmacist." Never "safe". The AI can never return a "no interaction" result.
- [ ] DDInter always wins: if a pair is in DDInter, the label and AI levels can't contradict or downgrade it.

### Patient-aware checks
Each check cites its source.
- [ ] **Duplicates across doctors:** two medicines in the same class (RxClass) from different prescribers.
- [ ] **Timing:** a label says to keep two drugs apart (e.g. levothyroxine and calcium about 4 hours apart), and the patient's dose times or logs show them taken together.
- [ ] **Conditions and lab results:** a label warning matches something in the patient's record, e.g. a kidney warning when a recent report shows reduced kidney function, or a low-sugar warning when the patient has logged low readings.
- [ ] **Side effects:** when a new symptom appears after a medicine is started or its dose changes (`medication_events`), check whether that drug's label lists the symptom as an adverse reaction. Example: "Ankle swelling is listed in amlodipine's official label, and yours began 3 weeks after the dose increase. Worth mentioning to your doctor." Feed this into the assistant's evidence pack.
- [ ] Optional: food and alcohol notes from labels when the patient logs them (e.g. alcohol with metformin).

### When checks run
- [ ] When a medicine is added or changed, whether manually or by confirming a visit note.
- [ ] On demand from the Medications page.
- [ ] As assistant tools (`med_check`, `side_effect_check`), so the chat can answer "Can I take X with my medicines?" using the same three levels.

### UI
- [ ] Give each finding:
  - a level badge (Verified / Official label / AI flag),
  - the source link and quote,
  - a plain-language explanation,
  - "questions to ask your pharmacist",
  - the disclaimer.
- [ ] Use severity colors only for Verified findings.
- [ ] Add an "Ask about this" button that opens the assistant with the finding pinned.

---

## Phase 6: UI overhaul (~2–3 days)

### Principles
- Put the AI front and centre, and make everything else support it.
- Show "what needs attention" before "everything we know".
- Make AI content look different: an AI label, "based on N entries", and links to the evidence.
- Use human labels and real units; never show raw keys or `None`.

### Tasks
- [ ] Navigation: Assistant (home), Dashboard, Vitals & Timeline, Visits, Medications, Reports, Share.
- [ ] Dashboard:
  - a "Needs attention" strip at the top (alerts, recurring patterns, open medication findings, critical report values, overdue tests and follow-ups),
  - stat cards with sparklines,
  - AI insights with their evidence,
  - a timeline of recent events.
- [ ] Charts:
  - padded y-axis,
  - typical-range bands labeled "typical range, not a diagnosis",
  - proper titles and units,
  - markers for medication changes and doctor visits along the time axis.
- [ ] Data entry: BP as one field ("147/92"), and glucose quick-add with a fasting / after-meal option.
- [ ] Medications page: one row per medicine with brand and generic name, prescriber, 14 adherence dots, and dose-change history. Add a "Safety" panel with findings by level. This replaces the cramped calendar.
- [ ] Reports: a list page plus the full report page with the explainer side panel (Phase 4).
- [ ] Story page: a good LLM story with the date it was generated and what it's based on. Only show the fallback badge when generation actually failed.
- [ ] Empty states that explain each feature (Reports, Visits, Medication safety).
- [ ] Demo mode: three patient cards (Harsh, Priya, Ramesh) on the login page for one-click login.
- [ ] Polish: consistent casing and copy, loading and error states, and a check at both laptop and projector resolution.
- [ ] Keep one design source of truth for colors, spacing, and type in `tailwind.config.js` and `components/ui.tsx`.

---

## Phase 7: Demo patients (~2–3 days)

### Shared machinery
- [ ] **Story scripts** in `backend/scripts/demo/patients/{harsh,priya,ramesh}.yaml`. Each one covers:
  - profile, conditions, and doctors,
  - medicines (brand and generic) with change dates and prescribers,
  - logging habits,
  - planted episodes,
  - reports (dates and values),
  - visits,
  - the live "climax" inputs and what the reply should do.
- [ ] **Generator** (`scripts/demo/generate.py`) expands a script into 6–9 months of data:
  - entries in the patient's own voice (written by Sonnet once),
  - vitals with realistic noise and times of day,
  - dose logs with adherence gaps,
  - lab PDFs (ReportLab, Indian lab layout, fictional lab name),
  - report files kept aside for live uploads (one as a phone-style photo),
  - visit recaps.
- [ ] **Replay** (`scripts/demo/replay.py`) feeds everything through the real pipeline in date order, with the clock set to each entry's date (`app/core/clock.py`). That way problems, trends, clusters, observations, and embeddings all come from our own code.
- [ ] **Cache** every LLM output, keyed by an input hash, in `scripts/demo/cache/*.json`. Also cache the openFDA labels and RxClass lookups. Reseeding then runs offline, costs nothing, and gives identical results.
- [ ] **Reset:** `uv run python -m scripts.demo reset` wipes and reloads all three patients.
- [ ] Keep all dates relative to today, so the data is always fresh on demo day.

### Harsh: recurring pattern and the visit loop
- 52, software manager in Bengaluru, type 2 diabetes for 8 years. Endocrinologist: Dr. Rao.
- Medicines: metformin 500 mg twice daily; glimepiride raised from 1 mg to 2 mg about 5 months ago.
- HbA1c across three reports: 8.4 → 7.6 → 6.9.
- **Planted pattern:** three episodes (shaky, sweaty, dizzy, heart racing) about 4, 3, and 1.5 months ago.
  - Each was on a day he logged skipping or delaying lunch after his morning dose.
  - Two had readings of 62 and 66 mg/dL.
  - All came after the dose increase.
- **Visit note** from the dose-increase visit: Dr. Rao said not to skip meals, to watch for low sugars, and what to do if his sugar is low.
- **Live 1:** "feeling shaky and sweaty, skipped lunch, meetings all day". The reply should:
  - recall all three dates,
  - point out the shared skipped-lunch and morning-dose pattern,
  - note that the episodes began after the dose increase,
  - quote Dr. Rao's instruction,
  - ask him to check and log his sugar,
  - suggest raising the pattern at his next visit.
- **Live 2:** "how have my sugars been since the dose change?"
- **Live 3 (visit recap):** record a 30-second recap. For example: "Saw Dr. Rao today, she reduced glimepiride back to 1 mg because of the lows, asked me to keep a sugar diary, review in 6 weeks." The note appears; confirming it updates the medicine, logs the dose change, and creates the follow-up reminder. This closes the loop: pattern spotted, discussed with the doctor, dose adjusted.

### Priya: report explainer and a clash between doctors
- 31, hypothyroid for 4 years, on Thyronorm 75 (levothyroxine). TSH has been stable at about 2.0.
- An orthopaedist (a different doctor) starts her on Shelcal (calcium + vitamin D3). She logs taking it together with her thyroid tablet at 7 am.
- About 6 weeks later: tiredness, feeling cold, hair fall, and +2 kg.
- **Memory link:** last year she logged the same cluster of symptoms before her dose was raised (TSH was 7.2 then).
- **Live 1:** "so tired lately, always cold, hair falling a lot". The reply should:
  - recall last year's similar phase,
  - note the timing relative to when she started Shelcal,
  - mention the timing finding from the label.
- **Live 2 (report explainer):** upload her new thyroid report as a phone photo.
  - The explainer opens on its own and says TSH is 6.8, above the range and up from about 2.0.
  - It explains what TSH measures and notes she's logged related symptoms over the past 6 weeks.
  - Tap "What should I ask my doctor?" and save the questions.
- **Live 3:** open the Medications safety panel. It shows the brand → generic matches and the levothyroxine + calcium finding, with its level and quote. Then open the pre-visit brief for her endocrinologist, which shows the symptoms, the new TSH, the timing finding, and her saved questions.
- [ ] Check whether levothyroxine + calcium carbonate is in your DDInter table. If it is, it shows as Verified; if not, it should come through the label level.

### Ramesh: side-effect awareness and safety escalation
- 63, hypertension. Amlodipine raised from 5 mg to 10 mg about 2 months ago; also on atorvastatin.
- Ankle swelling logged repeatedly, starting about 3 weeks after the increase. BP is improving.
- **Live 1:** "ankles swollen again". The reply:
  - recalls when the swelling started relative to the dose change,
  - notes that ankle swelling is listed in amlodipine's official label (the side-effect check),
  - suggests raising it with his doctor.
- **Live 2:** "chest felt tight climbing stairs again, a bit breathless" (the second time this week). The red-flag banner appears instead of a casual reply, and the app offers the doctor summary PDF or share link.

### Demo script
- [ ] Write `DEMO_SCRIPT.md`: the order, exact inputs, expected replies, and what to click (about 12–15 minutes total). Include a backup plan (cached replies, Groq fallback) in case the network or proxy fails.
- [ ] Rehearse end to end at least 3 times, starting from a fresh reset each time.

---

## Phase 8: Testing and evaluation (~1–2 days)

- [ ] Keep the existing pytest suite green (34 tests, run against the separate `phia_test` database).
- [ ] Unit tests for:
  - the recurrence detector,
  - the onset / backdating parser,
  - symptom name normalization,
  - the new clustering,
  - problem trend,
  - missing-info resolution,
  - the single BP alert,
  - the language guard (blocks diagnoses; allows "you have logged…" and attributed doctor quotes),
  - critical-value rules.
- [ ] Tests for the chat endpoint, using a stubbed LLM.
- [ ] **Medication safety tests:**
  - the AI never produces an all-clear,
  - a label quote that isn't in the label text is discarded,
  - DDInter always wins over the label and AI levels,
  - a brand → generic match is never used until the user confirms it,
  - missing data gives the exact "no known interaction found" wording.
- [ ] **LLM eval set** in `tests/eval/golden.yaml`: 30–40 questions across the three patients, covering the assistant, the report explainer, and medicine questions. Each lists facts the reply must contain (dates, values, quotes) and things it must not say. Run it before every demo and put the pass rate in the report.
- [ ] **Safety tests:**
  - every red-flag input escalates,
  - every critical report value shows the banner,
  - no reply cites an entry that doesn't exist,
  - no diagnosis wording gets through.

---

## Phase 9: Docs, report, and viva prep (~1–2 days)

- [ ] README: setup steps, LiteLLM and openFDA environment variables, demo accounts, and the reset command.
- [ ] `memory.md`: log the new decisions (D15 onward):
  - LiteLLM routing,
  - `occurred_at` and the clock,
  - the assistant design,
  - visit recaps,
  - the recurrence detector,
  - the report explainer,
  - the three-level medication rule and its data sources.
- [ ] Architecture diagram: add the router and assistant nodes, the visit pipeline, and the medication safety sources.
- [ ] Credit DDInter 2.0 and openFDA in the app footer, the README, and the report.
- [ ] Project report:
  - replace the screenshots (the current ones show the `None` bug and the offline story),
  - add sections on the assistant, visit recaps, the report explainer, medication safety, evaluation results, cost per interaction, and limitations.
- [ ] Viva prep: have short answers ready for these questions:
  - "Is this diagnosing?"
  - "How do you stop hallucinations?"
  - "What if the AI is wrong?"
  - "Why not let the AI decide drug interactions?" The answer is the asymmetric rule: the AI can raise a concern but never clear a pair.
  - "What happens for a drug pair that isn't in your database?"
  - "Why LangGraph, and why agents at all?"
  - "What about privacy and consent for recordings?"
  - "What does it cost per user?"
  - "What happens if there's no internet or the provider is down?"

---

## Suggested order

1. **Phase 0 → Phase 1.** Everyone works together at first, then split up.
2. **Phase 2 together with Harsh from Phase 7.** You need the patient data to test the assistant.
3. **Phase 4 (report explainer).** It reuses the assistant, so it's a quick win.
4. **Phase 5 (medication safety)**, then **Phase 3 (visit recaps)**, which uses it.
5. **Priya and Ramesh**, once Phases 3–5 exist.
6. **Phase 6 (UI)** runs alongside from step 2. **Phases 8 and 9** come last.

**For a team of three:**
- **A, backend and AI:** Phases 1, 2, and 5, plus the backend of Phases 3 and 4.
- **B, frontend:** Phase 6, plus the UI for Phases 2–5.
- **C, data, demo, and docs:**
  - the lab glossary and critical-value list (Phase 4),
  - label and class caching (Phase 5),
  - Phase 7, the Phase 8 eval set, and Phase 9.

---

## Definition of done (demo-ready checklist)

- [ ] A fresh clone plus one command gives you the app with all three demo patients loaded.
- [ ] Each live moment in the demo script works 5 times in a row.
- [ ] Uploading a report opens the explainer with correct values, comparisons, and context.
- [ ] Every medication finding shows its level and source, and nothing ever says "safe".
- [ ] No raw keys, `None`, or placeholder text anywhere on screen.
- [ ] It still works on the Groq fallback and the cached labels if LiteLLM or the internet is down.
- [ ] The eval set and safety tests pass.
- [ ] Report and slides are updated, and the demo has been rehearsed 3 times.

## Out of scope (don't spend time on these)

- Hosting or deployment (we demo locally).
- Real patient data (synthetic only).
- Diagnoses, treatment advice, or dosing suggestions.
- Using the AI as the authority on whether drugs are safe together.
- Doctor accounts or hospital-system (EHR) integration.
- A mobile app.

---

## Budget notes (LiteLLM key, $250 limit)

- List prices as of Nov 2026: Sonnet 5.5 is $2 in / $10 out per million tokens, and Haiku 5.5 is $0.10 / $0.50. Check which versions your proxy exposes. Older ones cost more (Sonnet 4.5/4.6: $3 / $15; Haiku 4.5: $1 / $5).
- Expected app usage for building, testing, and demos: roughly **$20–50** in total. The report explainer and label reading add a little on top of the original estimate.
- The biggest risk is using the key with a coding agent, which resends large chunks of the codebase every turn. Watch your spend daily if you do.
- Log tokens per call (Phase 1) and check the key's spend after each testing day.
- Cache the demo data, labels, and class lookups, and don't regenerate the patients over and over.
- openFDA, RxNorm, RxClass, and Groq's Whisper are free.
