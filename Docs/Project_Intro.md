# Personal Health Intelligence Agent – Master Design Document

## 1. Executive Summary

The **Personal Health Intelligence Agent** is a multi-agent backend system designed to maintain a *longitudinal PatientHealthState*, rather than serve as a passive health record.  Its goal is to continuously organize, connect, and summarize a patient’s health data over months or years so that both patients and doctors always have meaningful context.  This is **not** an AI doctor or treatment recommender; instead it is a **Health Intelligence Engine** that *observes* and *explains* patient history, improving health continuity (see “Health Continuity” above).  The system demonstrates expertise in LangGraph-based orchestration, multi-agent design, FastAPI backend development, PostgreSQL/ChromaDB storage, and AI integration.  In practice, every new patient input (symptom, vital, report, etc.) flows through a controlled agent pipeline that updates a shared **PatientHealthState** and yields immediate user-facing insights, charts, or summaries.

## 2. Problem Statement

Most consumer health apps today are simple data stores.  They let users log symptoms, vitals, medications, lab reports, etc., but they do *not* actively reason about that information over time.  Consequently:

- **Patients** end up shouldering the burden of remembering their own history (symptom timelines, trends, missing tests) and may miss patterns in their condition.
- **Doctors** must spend consultation time reconstructing past events (asking “When did this start?”, “What treatments have you tried?”, etc.) rather than focusing on the current problem. 

This leads to fragmented care.  The core problem we solve is **health continuity**: preserving and leveraging longitudinal context so that each encounter starts with rich, integrated information.  We explicitly do *not* attempt diagnosis or treatment.  Instead, by focusing on information continuity, we free both patients and clinicians from repetitive history-taking. The system’s outputs (trend charts, contextual summaries) give doctors a jump-start on every visit, and give patients insights during the months between visits.

## 3. Architecture Overview

We implement a **LangGraph-based multi-agent workflow** with one orchestrator (the LangGraph “graph”) and four specialized agents (Intake, Memory, Reasoning, Response).  This is a *sequential orchestration* (pipeline) pattern. The orchestrator calls each agent in turn, passing along shared state (the `PatientHealthState`).  Agents **do not call each other directly**; instead the central workflow manages the sequence, making the architecture modular and debuggable.  

![Sequential Agent Pipeline (Orchestrator-Worker Pattern)](data:image/png;base64,INSERT_PLACEHOLDER)  
*Figure: Sequential orchestration of specialized agents. Each agent performs one task and passes results via shared state.*  

This follows best practices: each agent is **focused on a narrow responsibility**, which improves reliability and performance.  For example, our Intake Agent *only* handles parsing free-text input; the Memory Agent *only* retrieves past context; the Reasoning Agent *only* updates the health state (detecting trends, etc.); and the Response Agent *only* formats outputs. This specialization reduces hallucinations and makes testing each part easier.  It also allows scaling or replacing individual parts without re-engineering the entire workflow.

The workflow is **deterministic**: which agent runs next is defined by design, not chosen by an AI at runtime.  (We rely on LangGraph’s flow control to enforce the sequence.)  This ensures predictable behavior: for instance, after intake and memory retrieval, the Reasoning Agent always runs, then the Response Agent.  The only exception is user interaction during intake (where follow-up questions may branch) and the decision of which output to produce (health snapshot vs. consultation PDF), which are also governed by explicit nodes in the graph.

## 4. PatientHealthState – Data Model

At the core is the **PatientHealthState** – a structured object that represents *everything we know about the patient at the current moment*.  This is the *“state”* in LangGraph terms.  Unlike a raw database, this state is designed to be updated by agents and then rendered in different ways.

We maintain the following sections in PatientHealthState:

- **Identity**: Static demographics (Name, Age, Sex, Height, Weight, Blood Group, Contact).  
- **Medical Background**: Long-term conditions (e.g. Diabetes, Hypertension, Asthma), Allergies, Family History, Surgical History, **Medication List**, and lifestyle (Smoking/Alcohol). These change rarely.  
- **Active Problems**: A current problem list. Each entry is a health issue the patient is experiencing, with attributes: 
  - *Severity* (current level), 
  - *Frequency* (how often symptoms recur), 
  - *Trend* (e.g. worsening/improving), 
  - *Status* (e.g. “active”, “managed”, etc.).  
  For example: “Recurring Headaches – Frequency: 5 episodes in 8 weeks – Severity: moderate – Trend: increasing.”  
- **Resolved Problems**: Previously active issues that are no longer a concern (e.g. “Strep Throat (resolved)”).  We move problems here when they have been quiescent for a set period (for audit/history).  
- **Vital Summary**: Not raw readings, but the system’s understanding of vitals over time. For each vital sign (Blood Pressure, Weight, Heart Rate, Blood Glucose, SpO₂, etc.), we store a summary such as latest values, trends (e.g. increasing or stable), and perhaps averages.  (For instance, “BP: 130/85 → 142/90 over 6 months (rising trend)”.)  
- **Symptom Clusters**: Groups of symptoms that often appear together. For example, the system might note that “Headache + Fatigue + Nausea” occurred 3 times.  This helps identify syndromic patterns.  
- **Trend Analysis**: Overall trends in health markers: “BP increasing”, “Weight stable”, “Sleep quality improving”. These are higher-level patterns distilled from vitals and logs.  
- **AI Observations**: Free-text observations generated by the Reasoning Agent, based on the history. Examples: “Fatigue often follows headache episodes within 2–3 days.”; “Average headache pain has decreased after Vitamin D supplementation.” These **are not diagnoses**, only data-derived insights.  
- **Missing Information**: Gaps identified in the record, e.g. “No blood pressure reading in last 45 days”, or “Chest pain duration not recorded.” This prompts user follow-up.  
- **Suggested Next Actions**: Informational cues like “Log today’s blood pressure” or “Schedule a cholesterol test” – again, not doctor’s orders, just suggestions.  

All of these are encoded in memory (PostgreSQL for structured fields, ChromaDB for semantic pieces like reports or notes) and mirrored in the PatientHealthState in-memory object. When new data arrives (say, a lab report upload or symptom log), the Reasoning Agent updates the relevant parts of PatientHealthState.  For example, adding a “blood pressure reading” updates the Vital Summary (new value and recomputed trend), and possibly triggers an observation if it crosses a threshold.  

In LangGraph terms, **PatientHealthState is the shared state** passed between nodes. Each agent node reads the prior state and may write updates. This aligns with LangGraph’s design: nodes are Python functions that accept and return a shared state object.  By treating this state as a central “notepad”, we ensure every agent works with the same evolving picture of the patient.

## 5. Agent Design

### 5.1 Intake Agent (User Interaction)

**Responsibility:** Ingest and structure new patient input. This includes chat-like entries, form inputs, or file uploads from the user (patient).

- **Input:** User’s free-text or structured input (symptom description, vital values, upload metadata). For example: “I have been having chest pains for 3 days.” or “Uploaded BP: 145/92.”  
- **Processing:** Using LLM prompts (via LangGraph node), the agent parses the input into structured data:
  - Identify *what* the entry is (symptom, vital sign, etc.).
  - Extract relevant attributes (severity, duration, onset, frequency, numeric values).
  - Normalize terms (e.g. map “tummy ache” to “abdominal pain”). 
  - If key fields are missing (e.g. symptom onset date), generate a follow-up question for the user. This may involve a quick back-and-forth conversation until clarity.  
- **Output:** A structured data object or list of facts, e.g.: `{type: "Symptom", name: "Chest pain", severity: "6/10", duration: "3 days", note: "..."} `.  
- **Failure Modes:** If the input is incomprehensible or not medical (e.g. “I feel blah”), the agent politely asks for clarification. If multiple symptoms are mentioned in one message, it may split them into separate structured facts.  

This agent ensures downstream logic sees clean, standardized medical entries.  By focusing *only* on interpretation of user input, it adheres to the single-responsibility principle.

### 5.2 Memory Agent (Context Retrieval)

**Responsibility:** Gather relevant historical context to inform reasoning. It avoids passing the entire health record to the next step by retrieving only what matters.

- **Input:** The structured new data from Intake plus the current PatientHealthState (or its key fields).  
- **Processing:** Decide which past records are relevant. For example, if a symptom “headache” was just logged, retrieve prior “headache” entries (via semantic search on ChromaDB) and related vitals (e.g. past blood pressure readings).  Also retrieve any active conditions (“History of migraines”) or past observations related to the new data. In practice, this may involve:
  - Querying **PostgreSQL** for structured data (e.g. get latest vitals, medication list).
  - Querying **ChromaDB vector store** for similar symptom descriptions or notes.  
  - Possibly summarizing or filtering results (e.g. pick last 3 episodes, or events in last 6 months).
- **Output:** A context bundle for the Reasoning Agent, for example: “Recent context: 4 headaches in 3 months, average BP history, current meds, last lab report.” This might be a text prompt or data structure that combines key facts from the history.  
- **Failure Modes:** If the patient has no history (new user), the agent simply returns an empty context or default. If a relevant record cannot be found (e.g. user asks about a symptom never logged before), it notes that context is absent.

This agent exemplifies the **retrieval-based memory** pattern: it fetches salient information instead of blindly copying all history. This mitigates context overload and “long history passing” issues.  The agent effectively answers, “What does the Reasoning Agent need to know from the past?”

### 5.3 Reasoning Agent (Health State Update)

**Responsibility:** The core intelligence; updates the PatientHealthState using the new input plus retrieved context. Importantly, it *does not diagnose or prescribe* – it only analyzes.

- **Input:** New structured patient data (from Intake) and the context bundle (from Memory), along with the current PatientHealthState.
- **Processing:** This agent recalculates trends, patterns, and flags in the health state. Key tasks include:
  - **Active/Resolved Problems:** If a symptom matches an existing active problem, increment its frequency and possibly adjust severity/trend. If it’s a new issue, add a new active problem. Check if any active problem should be marked “resolved” (e.g. no occurrence for X months).  
  - **Trend Detection:** For numeric vitals (BP, weight, etc.), incorporate the new data point into the Vital Summary and update trend (e.g. detect that BP is rising by fitting a linear trend or comparing recent averages).  
  - **Recurring Patterns:** Identify if certain events co-occur or follow each other. For example, if fatigue logs often come within 2 days after headache logs, record that pattern.  
  - **Observations Generation:** Using the up-to-date state, articulate any noteworthy observations. For example: “Headaches have occurred 3 times in 2 months (trend: increasing), typically preceded by poor sleep.”  These are generated via LLM prompt(s) using the state (ensuring we follow data, not hallucinate).  
  - **Missing Info:** Check for expected data gaps (e.g. if no BP readings in 60 days, or a known condition lacks recent lab tests) and note them.  
- **Output:** The **updated PatientHealthState**. All sections are potentially modified. For example, Vital Summary may now say “BP trend: up 10%”, Active Problems updated, Observations appended, etc.
- **Failure Modes:** This agent should be robust to noisy data. If contradictory inputs appear (e.g. conflicting symptom reports), it should reconcile by context (e.g. user said “nausea X” then “no nausea” – clarify in next cycle). If an observation LLM call seems uncertain, the agent might skip output rather than hallucinate.

The Reasoning Agent is essentially an orchestrator of internal rules plus LLM-based insights. It implements the “Health State Engine” concept. By focusing on updating state rather than answering user questions, it achieves *modularity* and avoids uncontrolled agent chatter.  It might involve calling multiple LLM prompts (one for trends, one for observations) or using a few-shot prompt to produce a combined insight paragraph, but all outputs feed back into the same state structure.

### 5.4 Response Agent (Presentation Layer)

**Responsibility:** Generate user-facing outputs from the PatientHealthState.

- **Input:** The updated PatientHealthState and context (such as which scenario triggered the response).  
- **Processing:** Depending on the situation, format and present the information:
  - **Health Snapshot:** An interactive or textual summary shown to the patient immediately after input. This includes Active Problems list, Recent Changes, AI Observations, Missing Information, and Suggested Next Steps. For example: 
    > **Today’s Snapshot:** 
    > • *Active:* Recurring headaches (3x last month), Vitamin D deficiency.  
    > • *Recent changes:* Headache severity +20%.  
    > • *Observations:* Headaches now mostly occur in evenings.  
    > • *Missing:* No BP in 45 days. *Next:* Log BP.  
  This response might be generated by templating the state into markdown or by using an LLM to write a friendly summary.  
  - **Health Story:** A narrative overview of the patient’s journey, typically shown on demand (e.g. “View My Health Story” page). It should weave together multiple Active Problems and trends into a coherent timeline description. For example:  
    > *“Over the past 6 months, recurrent headaches emerged as a main issue. Initially monthly, they increased to weekly, often accompanied by fatigue. Your blood pressure also climbed over this period. Recently, after starting vitamin D supplements, headache intensity has started to drop. No major new issues have appeared…”*  
    This is generated by an LLM that “tells the story” using state variables (ensuring it covers all active issues).  
  - **Doctor Consultation Summary (PDF):** A concise report to hand the doctor before a visit. It includes: Active Problems, Important Trends (e.g. lab deltas), Relevant History snippets, Recent Vitals chart, and AI Observations. It can be formatted into a PDF via a template (e.g. LaTeX or HTML→PDF). This is more formal and structured than the patient view.  
- **Output:** Human-readable text (or PDF) tailored to the audience (patient vs doctor). In all cases, the source of truth is the PatientHealthState.
- **Failure Modes:** Ensure no sensitive info leakage; if LLM generates something incorrect in narrative, have a deterministic fallback (e.g. list known facts). The Response Agent should never guess beyond what’s in state.

This agent demonstrates how one underlying state can produce multiple product deliverables: an on-screen snapshot, a written story, and a printed summary. It keeps the UI consistent with the internal model.

## 6. Design Principles & Constraints

- **Immediate Value:** Every user action yields an update to the health state and visible feedback. We never simply reply “Saved”; instead the interface shows new insights. This meets the principle “every interaction provides immediate value” from the blueprint. It creates a **feedback loop** so patients stay engaged.
- **AI vs Deterministic Logic:** We reserve AI (LLMs) for tasks requiring language understanding or generation: parsing user text, reasoning about context, crafting narratives. All other tasks (database updates, fixed rules, formatting) are coded in normal Python. This keeps the system explainable and avoids unnecessary LLM calls. In practice, the Memory Agent and parts of Reasoning use LLMs for semantic search or pattern-finding, but the database schema, update rules, and output templates are standard code.
- **Safety (“What AI Never Does”):** The system is explicitly constrained. It never provides medical advice or predictions. All AI-generated statements are carefully phrased as “observations” or “patterns” (e.g. *“Your BP has been rising over 3 months”* vs *“You have hypertension”*).  
- **Scalability:** Agents and the orchestrator are stateless nodes within LangGraph. The true state is external (Postgres + Chroma + in-memory). This avoids issues of “agents stepping on each other” and simplifies retrying nodes. If a node fails (e.g. LLM timeout), LangGraph can retry just that step without starting over.

## 7. Technical Novelty

The project’s innovation lies in the **combination** of these ideas:

1. **Longitudinal Reasoning:** The system reasons across long time spans. Unlike typical chatbots, it continuously updates a patient model.  Handling long histories is a known challenge – naive LLM prompting fails on tens of thousands of events. We address this via tiered summaries and RAG (Retrieval-Augmented Generation) in the Memory Agent (only relevant slices of history are passed at a time).
2. **Hybrid Memory (Structured + Semantic):** We store structured data (vitals, conditions) in PostgreSQL and unstructured/semantic data (notes, reports) in Chroma (vector DB). This dual-memory design lets us quickly query exact facts (SQL) while also semantically matching patient narratives (Chroma).
3. **Agentic Health State Engine:** The multi-agent LangGraph architecture modularizes reasoning. Each agent is simple (do one job) and the orchestrator (LangGraph) manages flow. This clean division is in line with best practices (focus on specialization, avoid multi-agent unless needed, treat context via retrieval). It also makes the system observable: we know exactly which agent updated which part of state, aiding debugging (unlike a monolithic LLM that does everything).

We are effectively building a **controlled pipeline** of AI and code modules, which is why LangGraph is ideal. Each transition is predetermined: e.g., after Intake always call Memory, after Reasoning always call Response. This eliminates ad-hoc agent loops, ensuring production reliability.

## 8. Deliverables & Deliveries

When complete, the system provides:

- A **FastAPI backend** with endpoints for patient login, data entry (symptoms, vitals, etc.), and retrieval of snapshots and summaries. These APIs call the LangGraph workflow under the hood.
- A **LangGraph workflow** that orchestrates the four agents above, with robust error handling and state management.
- A **PostgreSQL schema** for storing PatientHealthState components (demographics, conditions, vitals, problem list, etc.) and audit log of entries.  
- A **Chroma vector store** of patient entries and reports (to enable semantic search over symptoms, notes).
- **Pydantic models** defining the PatientHealthState and its sub-components, ensuring type safety in code.
- **Front-end templates** (or an example UI) to display the Health Snapshot and Story based on the outputs from the Response Agent.
- **PDF/Report generation** (via a tool like ReportLab or wkhtmltopdf) for the doctor summary.

Each component is well-documented. The design here (this document) serves as the blueprint that another engineer could follow to implement the system.

## 9. Summary

In summary, the **Personal Health Intelligence Agent** is a LangGraph-powered multi-agent application whose sole task is to keep a patient’s health model up to date and useful. By splitting work into specialized agents (Intake, Memory, Reasoning, Response) and using both SQL and vector memory, we achieve a robust system that gives patients insights on the fly and prepares doctors before each visit.  Crucially, we *observe* rather than *diagnose*, thus staying safely within our brief. The agents work together deterministically (as a sequential pipeline), reading and writing a shared PatientHealthState, which is then transformed into user-facing output. This design provides a clear development roadmap and a compelling demonstration of agentic AI and backend engineering, all grounded in real clinical context rather than a contrived “AI doctor” gimmick.

**Sources:** This design leverages best practices from AI agent architecture (specialization, sequential orchestration), LangGraph workflow patterns, and clinical AI research on managing longitudinal patient data. All decisions align with the project’s goal of preserving health continuity without medical diagnosis.