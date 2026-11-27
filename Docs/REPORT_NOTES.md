# Project report: material for the v2 chapters

Drop-in text and numbers for the report. Decisions are detailed in `memory.md` (D15–D38).

## Screenshots to replace

The old screenshots show the `None` bug and the offline story. Retake from a fresh reset
(`uv run python -m scripts.demo reset`), as each demo patient:

1. Assistant: Harsh's "feeling shaky and sweaty, skipped lunch" reply with date chips and the Dr. Rao quote.
2. Report page: Priya's TSH photo report with range bars and the explainer beside it.
3. Medications: Priya's safety panel (Verified DDInter finding + Official label timing quote).
4. Visit review screen (Harsh): a medicine change with "please check", and the clash preview.
5. Pre-visit brief for Dr. Menon (Priya), print view.
6. Ramesh: the side-effect reply, and the red-flag banner.

## New sections

### The assistant with memory
One chat for logging and asking. A router labels each message (log / question / both; the model is called
only for unclear messages). Logs go through intake (parse, onset date, context tags, canonical symptom names)
and reasoning; questions go straight to memory. Code builds an evidence pack (logged entry, recurrence with
shared circumstances, related entries, readings, medicine changes, reports, confirmed visit notes, medication
findings), each fact with an id. Sonnet writes a short plain reply citing ids; the UI shows them as dated
chips. Checks before anything is shown: red flags first (fixed escalation, no AI), unknown ids, diagnosis
wording (language guard), medicine all-clear or stop wording. Any failure gives a code-built fact list instead.

### The recurrence detector
For a symptom, code finds every earlier episode (including logs that name it alongside another symptom),
the gaps between them, circumstances shared by most episodes (a skipped meal within 6 hours, a dose marked
taken that day, a low reading within 24 hours), and any medicine change that all episodes came after.

### Doctor visit recaps
Typed or spoken (Whisper on Groq) recap → Sonnet structures it with the doctor's words attributed → code
counts dates, checks every medicine name (RxNorm; misheard names like glipizide vs glimepiride flagged) and
previews clashes with other doctors' medicines → the user edits and confirms → medicine changes applied as
that doctor's, reminders, saved questions, embedding, medication safety re-check. Pre-visit brief per doctor,
built in code, printable and on the doctor link. Recording a consultation requires the doctor's agreement.

### The report explainer
PDF, scan or phone photo (vision model) → values extracted → code decides everything about them: canonical
test names (48-test glossary with aliases), numeric ranges, flags, critical values, how far outside, the
previous value and the change. The explanation and follow-ups cite all of it; "is this bad?" gets no
verdict, "why could it be high?" gets general reasons from the glossary only.

### Medication safety
Three levels per ingredient pair: Verified (DDInter 2.0, always wins) → Official label (code finds sentences in
the openFDA label naming the other drug or its RxClass class; the AI picks and explains one; code accepts the
quote only if it is verbatim in the cached label) → AI flag (unverified, off by default). Never "safe":
nothing found reads exactly "No known interaction found in our sources. Confirm with your pharmacist."
Patient-aware checks: same class from different doctors, dose times closer than a label's "N hours", label
warnings matching the record (low sugars, kidney, liver, potassium), side effects first logged after a start
or dose change, alcohol. Brand names (Thyronorm, Shelcal) map to generics only after the user confirms.

### Evaluation
- **Offline test suite:** all tests stub every LLM and external API (DDInter, RxNorm, openFDA, Groq) and run on
  a separate database. Includes a safety sweep: 14 red-flag messages always escalate before any model call,
  every critical value leads the explanation, invented citations / diagnoses / all-clears are always replaced.
- **LLM eval set** (`backend/tests/eval/golden.yaml`, `python -m scripts.eval_golden`): 33 questions across the
  three demo patients (assistant, report explainer, medicine questions, escalations). Each lists what the reply
  must contain (values, names, cited evidence kinds, evidence older than N days) and must not say.
  **Result: 33/33 (100%) on the final run** (runs while fixing: 82% → 91% → 94% → 100%; model replies vary, so run it before every demo) (see `backend/tests/eval/results.md`).
- **What the eval caught and we fixed:** a self-harm message held back by a clarifying question (red flags now
  skip clarification); chest pain with arm numbness not escalating (new rule); a reply claiming "no low sugar
  readings" when there were two (the question now pulls readings, and the model may not claim absence);
  "whether you have X" flagged as a diagnosis; clear symptom logs sometimes asked a clarifying question.

### Cost per interaction (measured, LiteLLM cost header)

| Interaction | Calls | Cost |
|---|---|---|
| A question | assistant (Sonnet) | ~$0.015 |
| A log | intake (Haiku) + assistant (Sonnet) + background observations (Sonnet) | ~$0.021 |
| A lab report (PDF) | extract (Haiku) + summary + explainer (Sonnet) | ~$0.02 (+$0.012 as a photo) |
| A visit recap | structuring (Sonnet) + Whisper (Groq, free tier) | ~$0.004 |
| Doctor questions for a report | Sonnet | ~$0.009 |

An active user (5 logs and 2 questions a day) is about $0.14/day, roughly $4/month. Building and testing all
of v2 used about $2 of model calls in total. Latency: questions ~5–7 s, logs ~9–10 s, report explanation ~10 s.

### Limitations
Fictional demo data, not a clinical evaluation. Label matching is text-based and can quote a class-level
sentence that applies weakly. Critical-value thresholds and helpline numbers need a doctor's review.
Speech-to-text can mishear medicine names (flagged for review, not always caught). English only. DDInter is
CC BY-NC-SA (non-commercial); openFDA labels are U.S. labels. A local single-user demo: no deployment, no
multi-user hardening. The model can still word things imperfectly; checks catch the dangerous cases (invented
evidence, diagnosis, all-clear), not every awkward sentence.
