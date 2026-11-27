import { useEffect, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import { useMutation } from "@tanstack/react-query"
import { AlertTriangle, Keyboard, Loader2, Mic, Square, Upload } from "lucide-react"
import { useAuth } from "@/lib/auth"
import * as vi from "@/lib/visits"
import { Button, Card, CardContent, Input, Label, Textarea } from "@/components/ui"
import { cn } from "@/lib/utils"

type Mode = "type" | "voice" | "recording" | "upload"
const MODES: { key: Mode; label: string; icon: typeof Mic; hint: string }[] = [
  { key: "type", label: "Type it", icon: Keyboard, hint: "Write what happened in your own words." },
  { key: "voice", label: "Say it", icon: Mic, hint: "Record yourself telling the story of the visit, after you leave." },
  { key: "recording", label: "Record the visit", icon: Mic, hint: "Record the consultation itself, only if your doctor agrees." },
  { key: "upload", label: "Upload audio", icon: Upload, hint: "An audio file of your recap (mp3, m4a, wav, webm)." },
]

function Recorder({ onDone }: { onDone: (b: Blob | null) => void }) {
  const [rec, setRec] = useState<MediaRecorder | null>(null)
  const [seconds, setSeconds] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const chunks = useRef<Blob[]>([])
  useEffect(() => {
    if (!rec) return
    const t = setInterval(() => setSeconds((s) => s + 1), 1000)
    return () => clearInterval(t)
  }, [rec])
  async function start() {
    setError(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const r = new MediaRecorder(stream)
      chunks.current = []
      r.ondataavailable = (e) => chunks.current.push(e.data)
      r.onstop = () => {
        stream.getTracks().forEach((t) => t.stop())
        onDone(new Blob(chunks.current, { type: r.mimeType || "audio/webm" }))
      }
      r.start()
      setSeconds(0)
      setRec(r)
    } catch {
      setError("Couldn't use the microphone. Allow it in the browser, or type the recap instead.")
    }
  }
  return (
    <div className="space-y-2">
      {rec ? (
        <Button variant="outline" onClick={() => { rec.stop(); setRec(null) }}>
          <Square className="h-4 w-4 text-red-600" /> Stop ({Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, "0")})
        </Button>
      ) : (
        <Button variant="outline" onClick={() => { onDone(null); start() }}>
          <Mic className="h-4 w-4" /> Start recording
        </Button>
      )}
      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  )
}

export default function NewVisitPage() {
  const { patient } = useAuth()
  const pid = patient!.id
  const navigate = useNavigate()
  const [mode, setMode] = useState<Mode>("type")
  const [doctor, setDoctor] = useState("")
  const [specialty, setSpecialty] = useState("")
  const [day, setDay] = useState(new Date().toISOString().slice(0, 10))
  const [text, setText] = useState("")
  const [audio, setAudio] = useState<Blob | null>(null)
  const [consent, setConsent] = useState(false)

  const save = useMutation({
    mutationFn: () => {
      const fd = new FormData()
      fd.append("doctor_name", doctor.trim())
      fd.append("visit_date", day)
      if (specialty.trim()) fd.append("specialty", specialty.trim())
      fd.append("source", mode === "type" ? "typed" : mode === "recording" ? "recording" : "voice")
      if (mode === "recording") fd.append("doctor_consented", String(consent))
      if (mode === "type") fd.append("transcript", text)
      else if (audio) fd.append("audio", audio, audio instanceof File ? audio.name : "recap.webm")
      return vi.createVisit(pid, fd)
    },
    onSuccess: (v) => navigate(`/visits/${v.id}`),
  })
  const ready = doctor.trim().length > 1 && (mode === "type" ? text.trim().length > 10 : !!audio) && (mode !== "recording" || consent)
  const err = (save.error as { response?: { data?: { detail?: string } } } | null)?.response?.data?.detail

  return (
    <div className="max-w-3xl space-y-5">
      <h1 className="text-2xl font-bold tracking-tight text-foreground">New visit recap</h1>
      <Card>
        <CardContent className="space-y-4 pt-5">
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="space-y-1"><Label>Doctor</Label><Input value={doctor} onChange={(e) => setDoctor(e.target.value)} placeholder="Dr. Rao" /></div>
            <div className="space-y-1"><Label>Specialty (optional)</Label><Input value={specialty} onChange={(e) => setSpecialty(e.target.value)} placeholder="Endocrinology" /></div>
            <div className="space-y-1"><Label>Visit date</Label><Input type="date" value={day} onChange={(e) => setDay(e.target.value)} /></div>
          </div>

          <div className="flex flex-wrap gap-2">
            {MODES.map((m) => (
              <button
                key={m.key}
                onClick={() => { setMode(m.key); setAudio(null) }}
                className={cn("inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm",
                  mode === m.key ? "border-primary bg-primary text-primary-foreground" : "border-border hover:bg-muted")}
              >
                <m.icon className="h-3.5 w-3.5" /> {m.label}
              </button>
            ))}
          </div>
          <p className="text-sm text-muted-foreground">{MODES.find((m) => m.key === mode)!.hint}</p>

          {mode === "recording" && (
            <div className="space-y-2 rounded-lg border-2 border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
              <p className="flex items-center gap-2 font-semibold"><AlertTriangle className="h-4 w-4" /> Ask your doctor before recording.</p>
              <p>Recording a consultation without permission isn't fair to your doctor. A recap in your own words afterwards ("Say it") works just as well.</p>
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} /> My doctor agreed to this recording.
              </label>
            </div>
          )}

          {mode === "type" && (
            <Textarea className="min-h-[160px]" value={text} onChange={(e) => setText(e.target.value)}
              placeholder="e.g. Saw Dr. Rao today. She reduced glimepiride back to 1 mg because of the lows, asked me to keep a sugar diary and to come back in 6 weeks." />
          )}
          {(mode === "voice" || (mode === "recording" && consent)) && (
            <Recorder onDone={setAudio} />
          )}
          {mode === "upload" && (
            <Input type="file" accept="audio/*" onChange={(e) => setAudio(e.target.files?.[0] ?? null)} />
          )}
          {audio && mode !== "type" && <audio controls src={URL.createObjectURL(audio)} className="w-full" />}

          <div className="flex items-center gap-3">
            <Button onClick={() => save.mutate()} disabled={!ready || save.isPending}>
              {save.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              {save.isPending ? (mode === "type" ? "Writing the note…" : "Transcribing and writing the note…") : "Create note"}
            </Button>
            <span className="text-xs text-muted-foreground">You'll review everything before anything changes.</span>
          </div>
          {save.isError && <p className="text-sm text-destructive">{err ?? "Couldn't create the note."}</p>}
        </CardContent>
      </Card>
    </div>
  )
}
