import type { ReactNode } from "react"
import { NavLink } from "react-router-dom"
import { useAuth } from "@/lib/auth"
import { Button } from "@/components/ui"
import { cn } from "@/lib/utils"

const NAV = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/log", label: "Log" },
  { to: "/vitals", label: "Vitals" },
  { to: "/story", label: "Story" },
  { to: "/share", label: "Share" },
]

export function AppShell({ children }: { children: ReactNode }) {
  const { patient, logout } = useAuth()
  return (
    <div className="min-h-screen">
      <header className="border-b bg-card">
        <div className="mx-auto flex max-w-5xl items-center gap-6 px-4 py-3">
          <span className="font-semibold text-primary">Health Intelligence</span>
          <nav className="flex gap-1 text-sm">
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.end}
                className={({ isActive }) =>
                  cn(
                    "rounded-md px-3 py-1.5 transition",
                    isActive ? "bg-primary text-primary-foreground" : "hover:bg-accent",
                  )
                }
              >
                {n.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3 text-sm text-muted-foreground">
            <span>{patient?.name}</span>
            <Button variant="outline" onClick={logout}>
              Sign out
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-6">{children}</main>
    </div>
  )
}
