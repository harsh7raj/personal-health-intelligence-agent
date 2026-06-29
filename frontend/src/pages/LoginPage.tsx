import { useState, type FormEvent } from "react"
import { Link, useNavigate } from "react-router-dom"
import { useAuth } from "@/lib/auth"
import { Button, Card, CardContent, CardHeader, CardTitle, Input, Label } from "@/components/ui"

export default function LoginPage() {
  const { login } = useAuth()
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
      await login(email, password)
      nav("/")
    } catch {
      setError("Invalid email or password")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Sign in</CardTitle>
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
              {busy ? "Signing in…" : "Sign in"}
            </Button>
          </form>
          <p className="mt-4 text-sm text-muted-foreground">
            No account?{" "}
            <Link to="/register" className="text-primary">
              Register
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
