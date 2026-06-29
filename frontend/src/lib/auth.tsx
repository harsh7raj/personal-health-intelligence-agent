import { createContext, useContext, useEffect, useState, type ReactNode } from "react"
import { clearToken, getToken, setToken } from "./api"
import * as ep from "./endpoints"
import type { Patient, User } from "./endpoints"

interface AuthState {
  user: User | null
  patient: Patient | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  logout: () => void
  refreshPatient: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [patient, setPatient] = useState<Patient | null>(null)
  const [loading, setLoading] = useState(true)

  async function loadPatient() {
    try {
      setPatient(await ep.getMyPatient())
    } catch {
      setPatient(null)
    }
  }

  useEffect(() => {
    async function boot() {
      if (!getToken()) {
        setLoading(false)
        return
      }
      try {
        setUser(await ep.getMe())
        await loadPatient()
      } catch {
        clearToken()
        setUser(null)
      }
      setLoading(false)
    }
    void boot()
  }, [])

  async function login(email: string, password: string) {
    const token = await ep.login(email, password)
    setToken(token)
    setUser(await ep.getMe())
    await loadPatient()
  }

  async function register(email: string, password: string) {
    await ep.register(email, password)
    await login(email, password)
  }

  function logout() {
    clearToken()
    setUser(null)
    setPatient(null)
    window.location.href = "/login"
  }

  return (
    <AuthContext.Provider
      value={{ user, patient, loading, login, register, logout, refreshPatient: loadPatient }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used within AuthProvider")
  return ctx
}
