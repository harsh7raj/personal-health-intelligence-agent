# Viva prep: short answers

**"Is this diagnosing?"**
No. It observes and explains the patient's own records. Code finds the patterns (counts, dates, ranges,
recurrences); the model only words what it is handed, and every reply goes through checks: red flags first
(fixed escalation, no AI), every cited id must exist in the evidence, a language guard blocks diagnosis,
cause and treatment wording, and medicine all-clears are blocked. A doctor's diagnosis can appear only
as the doctor's words ("Dr. Rao said ..."), from a visit note the patient confirmed.

**"How do you stop hallucinations?"**
The model never sees the whole database; code builds an evidence pack where every fact has an id
(E entry, V reading, R report, M medicine change, D visit, G glossary, F finding). The reply must cite those
ids, the UI turns them into dated chips the user can click, and a reply citing anything outside the pack is
thrown away and replaced by a plain list of the facts. Numbers that matter (how far outside a range, the
change since last time, critical values, label quotes) are computed or verified in code. A label quote is
accepted only if it is word-for-word in the cached FDA label.

**"What if the AI is wrong?"**
Its job is narrow, so the damage is bounded: it can word a fact badly, not invent one (cited ids are checked).
When anything fails a check, the user gets the code-built fact list instead. Medicines: it can only add a
concern, never remove one (DDInter wins, and the AI can't clear a pair). The eval set (33 demo questions with
required and forbidden content) measures it: see `tests/eval/results.md`.

**"Why not let the AI decide drug interactions?"**
The asymmetric rule: a missed interaction is far worse than an extra question to the pharmacist. So
interactions come from sources first: Verified (DDInter 2.0), then Official label (openFDA text, quoted and
checked by code). The AI can only raise a third-level "AI flag (unverified)", switched off by default, and can
never return "no interaction" or "safe". Any such wording is replaced automatically.

**"What happens for a drug pair that isn't in your database?"**
It falls to the label level: code searches each drug's FDA label for the other drug's name or one of its
classes (RxClass, e.g. "CYP3A4 inhibitors") and quotes the sentence. If nothing is found anywhere, the app
says exactly: "No known interaction found in our sources. Confirm with your pharmacist." Never "safe".
Indian brands (Thyronorm, Shelcal) are mapped to generics by an AI suggestion the user must confirm, each
generic checked in RxNorm.

**"Why LangGraph, and why agents at all?"**
Each step has one job (route, parse, retrieve, reason, respond) and a fixed edge to the next: the order is
decided by code, not by a model, so it's predictable and testable node by node. LangGraph gives the shared
state, the branching (logs vs questions) and room to grow without a hand-written state machine. "Agents"
here means focused steps over shared state, not autonomous tool-choosing loops, on purpose.

**"What about privacy and consent for recordings?"**
It runs locally; data stays in the user's Postgres and Chroma. The default is a self-recap (the patient
tells the story after the visit). Recording the consultation shows "Ask your doctor before recording" and the
API refuses it unless the user ticks that the doctor agreed. Audio goes to Whisper only to transcribe. The
usage log never stores prompt text. The doctor link is read-only, time-limited and revocable.

**"What does it cost per user?"**
Measured from the usage log (LiteLLM's own cost header): a question about $0.015 (Sonnet), a log about $0.02
(Haiku parsing + Sonnet reply + background observations), a report about $0.02 ($0.03 as a photo), a visit
recap about $0.004 plus free Whisper on Groq. An active user (5 logs and 2 questions a day) is about $0.14 a
day, roughly $4 a month. The whole v2 build and testing used about $2 of model calls.

**"What happens if there's no internet or the provider is down?"**
LiteLLM down: every call fails over to Groq automatically. No model at all: the app still runs; replies
become the code-built fact lists, red flags and all calculations still work. No internet: demo data replays
from the committed AI cache, FDA labels and drug classes are cached in the database, so the Medications page
works offline. Only new free-text parsing and new uploads need a model.

**Limitations to state honestly**
Fictional demo data, not a clinical trial. Label matching is text-based (it can quote a class-level sentence
that applies weakly). Critical-value thresholds and helpline numbers need a doctor's review. Speech-to-text can
mishear medicine names (flagged, but not caught 100%). English only. DDInter is non-commercial; openFDA labels
are U.S. labels. No deployment or multi-user hardening in v2.
