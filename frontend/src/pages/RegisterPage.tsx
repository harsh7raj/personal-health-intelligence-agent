import { useState, type FormEvent } from "react"
import { Link, useNavigate } from "react-router-dom"
import { useAuth } from "@/lib/auth"
import { Button, Card, CardContent, CardHeader, CardTitle, Input, Label } from "@/components/ui"

export default function RegisterPage() {
  const { register } = useAuth()
  const nav = useNavigate()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError("")
    setBusy(true)
    try {
      await register(email, password)
      nav("/onboarding")
    } catch {
      setError("Could not register (email may already be in use)")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Create account</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-1">
              <Label>Email</Label>
              <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </div>
            <div className="space-y-1">
              <Label>Password</Label>
              <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <Button type="submit" disabled={busy} className="w-full">
              {busy ? "Creating…" : "Create account"}
            </Button>
          </form>
          <p className="mt-4 text-sm text-muted-foreground">
            Have an account?{" "}
            <Link to="/login" className="text-primary">
              Sign in
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
