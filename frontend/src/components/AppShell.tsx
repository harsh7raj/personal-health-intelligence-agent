import type { ReactNode } from "react"
import { NavLink } from "react-router-dom"
import {
  Activity,
  BookOpen,
  FileText,
  LayoutDashboard,
  LogOut,
  Pill,
  MessageCircle,
  Share2,
} from "lucide-react"
import { useAuth } from "@/lib/auth"
import { cn } from "@/lib/utils"

const NAV = [
  { to: "/", label: "Assistant", icon: MessageCircle, end: true },
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/vitals", label: "Vitals", icon: Activity },
  { to: "/story", label: "Story", icon: BookOpen },
  { to: "/medications", label: "Medications", icon: Pill },
  { to: "/reports", label: "Reports", icon: FileText },
  { to: "/share", label: "Share", icon: Share2 },
]

export function AppShell({ children }: { children: ReactNode }) {
  const { patient, logout } = useAuth()
  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 flex h-screen w-60 shrink-0 flex-col bg-slate-900 text-slate-300">
        <div className="flex items-center gap-2.5 px-6 py-6">
          <span className="h-2.5 w-2.5 rounded-full bg-primary" />
          <span className="font-semibold tracking-tight text-white">Health Intelligence</span>
        </div>
        <nav className="flex-1 space-y-1 px-3">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition",
                  isActive
                    ? "bg-primary text-white shadow-sm"
                    : "text-slate-300 hover:bg-slate-800 hover:text-white",
                )
              }
            >
              <n.icon className="h-4 w-4" />
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-slate-800 px-5 py-4">
          <p className="truncate text-sm font-medium text-white">{patient?.name}</p>
          <button
            onClick={logout}
            className="mt-1.5 flex items-center gap-1.5 text-xs text-slate-400 transition hover:text-white"
          >
            <LogOut className="h-3.5 w-3.5" /> Sign out
          </button>
        </div>
      </aside>
      <main className="flex-1 bg-background">
        <div className="mx-auto max-w-5xl px-8 py-8">{children}</div>
      </main>
    </div>
  )
}
