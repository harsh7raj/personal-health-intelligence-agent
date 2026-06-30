import { createBrowserRouter, Navigate, Outlet } from "react-router-dom"
import { AppShell } from "@/components/AppShell"
import { useAuth } from "@/lib/auth"
import LoginPage from "@/pages/LoginPage"
import RegisterPage from "@/pages/RegisterPage"
import OnboardingPage from "@/pages/OnboardingPage"
import DashboardPage from "@/pages/DashboardPage"
import LogPage from "@/pages/LogPage"
import VitalsPage from "@/pages/VitalsPage"
import StoryPage from "@/pages/StoryPage"
import SharePage from "@/pages/SharePage"
import MedicationsPage from "@/pages/MedicationsPage"
import ReportsPage from "@/pages/ReportsPage"
import DoctorViewPage from "@/pages/DoctorViewPage"

function ProtectedLayout() {
  const { user, patient, loading } = useAuth()
  if (loading) return <div className="p-8 text-muted-foreground">Loading…</div>
  if (!user) return <Navigate to="/login" replace />
  if (!patient) return <Navigate to="/onboarding" replace />
  return (
    <AppShell>
      <Outlet />
    </AppShell>
  )
}

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  { path: "/register", element: <RegisterPage /> },
  { path: "/onboarding", element: <OnboardingPage /> },
  { path: "/shared/:token", element: <DoctorViewPage /> },
  {
    element: <ProtectedLayout />,
    children: [
      { path: "/", element: <DashboardPage /> },
      { path: "/log", element: <LogPage /> },
      { path: "/vitals", element: <VitalsPage /> },
      { path: "/story", element: <StoryPage /> },
      { path: "/medications", element: <MedicationsPage /> },
      { path: "/reports", element: <ReportsPage /> },
      { path: "/share", element: <SharePage /> },
    ],
  },
  { path: "*", element: <Navigate to="/" replace /> },
])
