# Demo script (about 12–15 minutes)

Three fictional patients, each showing one idea. All data is synthetic and dated relative to today.

## Before the demo (the day before, and again 30 minutes before)

1. Stop the app, then reset the demo data (uses the committed AI cache, so it's offline and free):
   ```powershell
   cd backend
   uv run python -m scripts.demo reset
   ```
   Run it once **online** the day before: the last step fetches the FDA labels and drug classes
   the Medications page needs and stores them locally.
2. Start the app: `uv run python -m scripts.dev` (backend :8001, frontend :5173).
3. Open http://localhost:5173 in a clean browser window. Keep `backend/scripts/demo/generated/priya/tsh_new_photo.jpg` ready to upload.
4. Have a second window logged in as each patient, so switching takes one click.

| Patient | Login | Password |
|---|---|---|
| Harsh Iyer (52, type 2 diabetes) | harsh@demo.phia | demo-harsh-123 |
| Priya Nair (31, hypothyroid) | priya@demo.phia | demo-priya-123 |
| Ramesh Kulkarni (63, hypertension) | ramesh@demo.phia | demo-ramesh-123 |

## 1. Harsh: the assistant remembers (about 5 minutes)

**Point:** it connects today's symptom to months of history, with dates, and quotes the doctor.

1. Assistant page. Type: **`feeling shaky and sweaty, skipped lunch, meetings all day`**
   - Expect: "I've logged this", the three earlier dates (about 4, 3 and 1.5 months ago) as clickable chips,
     the shared skipped meal and morning doses, the two lows (62 and 66), "after the Glimepiride change from
     1 mg to 2 mg", **"Dr. Rao said on … not to skip meals after taking glimepiride"**, check and log your
     sugar, raise it with Dr. Rao.
   - Click a date chip: it opens the original entry.
2. Type: **`how have my sugars been since the dose change?`** Expect readings with dates and the trend.
3. Visits → New visit recap → *Type it* (the default; point out "Ask your doctor before recording" on
   the recording option). Doctor `Dr. Rao`, today, recap:
   **`Saw Dr. Rao today, she reduced glimepiride back to 1 mg because of the lows, asked me to keep a sugar diary, review in 6 weeks.`**
   - Review screen: the medicine change matched to his Glimepiride, the follow-up date counted from today.
   - *Check for clashes*, then *Confirm note*: "Changed Glimepiride", reminder created.
   - Medications page: Glimepiride is now 1 mg, prescribed by Dr. Rao. Loop closed.

## 2. Priya: reports and two doctors (about 5 minutes)

**Point:** reads a phone photo of a report, explains it against her history, and catches a clash between doctors.

1. Assistant. Type: **`so tired lately, always cold, hair falling a lot`**
   - Expect: the same cluster last year (before the dose was raised), the timing relative to starting
     Shelcal 45 days ago, and the label timing finding (levothyroxine and calcium 4 hours apart).
2. Reports → upload `tsh_new_photo.jpg`. Wait about 15 seconds: the report opens by itself.
   - Expect: TSH 6.8 above the 0.4–4.2 range, up from 1.9; what TSH measures; her symptoms of the last
     6 weeks as things to discuss.
   - *What should I ask my doctor?* → *Save to my pre-visit brief*.
3. Medications → Medication safety: calcium carbonate + levothyroxine (Verified, DDInter), the timing note
   quoting the FDA label ("at least 4 hours apart"; her schedule has both at 07:00), each with its
   source link. *Ask about this* opens the assistant with it pinned.
4. Visits → *Brief for Dr. Menon*: symptoms, the new TSH, Dr. Kapoor's Shelcal, the timing finding,
   her saved questions. *Print*.

## 3. Ramesh: side effects and safety (about 3 minutes)

**Point:** it notices a side effect in the official label, and escalates when it should.

1. Assistant. Type: **`ankles swollen again`**
   - Expect: swelling first logged about 3 weeks after amlodipine went from 5 to 10 mg, that ankle
     swelling (edema) is listed in amlodipine's official label, raise it with Dr. Shah,
     "Don't stop or change any medicine on your own".
2. Type: **`chest felt tight climbing stairs again, a bit breathless`**
   - Expect: the red banner instead of a chat reply, Call 112, the doctor summary PDF and the share link.

## Ground rules to say out loud

Observes, never diagnoses · every claim links to its evidence · the doctor's words are labelled as
the doctor's · medicines: never "safe", only sourced concerns · nothing medical is saved without the
user confirming it · runs locally, falls back to Groq.

## Backup plan

- **Proxy down:** the app falls back to Groq automatically (replies may be shorter). Demo data is
  unaffected (it was built from the cache).
- **No internet at all:** the replayed history, charts, reports, briefs and the Medications page (warmed
  the day before) still work. Live chat and the photo upload need a model: show the existing threads
  instead (Harsh's report page has a stored explanation).
- **Something looks wrong:** stop the app, `uv run python -m scripts.demo reset <patient>`, restart.
