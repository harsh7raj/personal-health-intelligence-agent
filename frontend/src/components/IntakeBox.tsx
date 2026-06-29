import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import * as ep from "@/lib/endpoints"
import { Button, Card, CardContent, CardHeader, CardTitle, Textarea } from "@/components/ui"

export function IntakeBox({ patientId }: { patientId: number }) {
  const qc = useQueryClient()
  const [text, setText] = useState("")
  const [question, setQuestion] = useState<string | null>(null)
  const [answer, setAnswer] = useState("")
  const [status, setStatus] = useState("")

  const refreshAll = () => qc.invalidateQueries()

  const submit = useMutation({
    mutationFn: () => ep.postIntake(patientId, text),
    onSuccess: (res) => {
      if (res.status === "clarification_needed") {
        setQuestion(res.question ?? "Can you add a bit more detail?")
        setStatus("")
      } else {
        setStatus("Logged ✓ — your snapshot has been updated.")
        setQuestion(null)
        setText("")
        refreshAll()
      }
    },
    onError: () => setStatus("Something went wrong."),
  })

  const sendAnswer = useMutation({
    mutationFn: () => ep.postIntakeAnswer(patientId, text, answer),
    onSuccess: (res) => {
      if (res.status === "clarification_needed") {
        setQuestion(res.question ?? "A little more detail?")
      } else {
        setStatus("Logged ✓ — your snapshot has been updated.")
        setQuestion(null)
        setText("")
        setAnswer("")
        refreshAll()
      }
    },
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle>Log something</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <Textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Describe a symptom, vital, or note — e.g. 'throbbing headache for 2 days, about 6/10'"
        />
        {question && (
          <div className="space-y-2 rounded-md border border-amber-300 bg-amber-50 p-3">
            <p className="text-sm font-medium">{question}</p>
            <Textarea
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              placeholder="Your answer…"
            />
            <Button onClick={() => sendAnswer.mutate()} disabled={sendAnswer.isPending || !answer.trim()}>
              Send answer
            </Button>
          </div>
        )}
        <div className="flex items-center gap-3">
          <Button onClick={() => submit.mutate()} disabled={submit.isPending || !text.trim()}>
            {submit.isPending ? "Sending…" : "Log"}
          </Button>
          {status && <span className="text-sm text-green-600">{status}</span>}
        </div>
      </CardContent>
    </Card>
  )
}
