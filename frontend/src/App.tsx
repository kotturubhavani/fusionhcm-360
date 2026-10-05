import { PayrollClient } from './payroll/api'
import { PayrollRoutes } from './payroll/pages'
import { useLoad } from './components/useLoad'
import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import {
  BrowserRouter,
  NavLink,
  Navigate,
  Route,
  Routes,
} from 'react-router-dom'
import { AuthClient, AuthError } from './auth'
import type { User } from './auth'
import { CoreHrClient } from './core-hr/api'
import { Dashboard, Directory, WorkerDetail } from './core-hr/pages'
import { HirePage } from './core-hr/forms'
import { ReferencePage } from './core-hr/reference'
import { Field, LoadState, Notice } from './components/ui'
import type { References } from './core-hr/types'
const auth = new AuthClient(import.meta.env.VITE_API_BASE_URL ?? '')
const isStaff = (user: User) =>
  user.roles.some((role) => role === 'HR' || role === 'ADMIN')
export function Navigation({ staff }: { staff: boolean }) {
  return (
    <nav aria-label="Main navigation">
      {(staff
        ? [
            ['/', 'Dashboard'],
            ['/workers', 'Workers'],
            ['/hire', 'Hire Worker'],
            ['/reference', 'Reference Data'],
            ['/payroll', 'Payroll'],
          ]
        : [
            ['/me', 'My employment'],
            ['/payroll/me', 'My payroll'],
          ]
      ).map(([to, text]) => (
        <NavLink
          key={to}
          to={to}
          end={to === '/'}
          className={({ isActive }) => `nav-link ${isActive ? 'selected' : ''}`}
        >
          {text}
        </NavLink>
      ))}
    </nav>
  )
}
function Management({
  api,
  payroll,
}: {
  api: CoreHrClient
  payroll: PayrollClient
}) {
  const loaded = useLoad(() => api.references(), [api])
  const [refs, setRefs] = useState<References | null>(null)
  const currentRefs = refs ?? loaded.data
  async function reload() {
    setRefs(await api.references())
  }
  if (!currentRefs) return <LoadState {...loaded} />
  return (
    <Routes>
      <Route path="/" element={<Dashboard api={api} refs={currentRefs} />} />
      <Route
        path="/workers"
        element={<Directory api={api} refs={currentRefs} />}
      />
      <Route
        path="/workers/:personId"
        element={<WorkerDetail api={api} refs={currentRefs} />}
      />
      <Route path="/hire" element={<HirePage api={api} refs={currentRefs} />} />
      <Route
        path="/reference"
        element={<ReferencePage api={api} refs={currentRefs} reload={reload} />}
      />
      <Route
        path="/payroll/*"
        element={<PayrollRoutes api={payroll} hr={api} staff />}
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
export function Workspace({
  user,
  api,
  payroll,
  logout,
  busy,
}: {
  user: User
  api: CoreHrClient
  payroll: PayrollClient
  logout: () => void
  busy: boolean
}) {
  const staff = isStaff(user)
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a href="/" className="brand">
          <span className="brand-mark">F</span>
          <span>
            FusionHCM <b>360</b>
            <small>People operations</small>
          </span>
        </a>
        <p className="nav-caption">{staff ? 'WORKSPACE' : 'SELF SERVICE'}</p>
        <Navigation staff={staff} />
        <div className="sidebar-footer">
          Core HR<span>Independent HCM simulation</span>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <span className="font-medium text-slate-600">
            {staff ? 'People & organization' : 'Employee self service'}
          </span>
          <div className="flex items-center gap-4">
            <div className="text-right">
              <p className="text-sm font-semibold">
                {user.first_name} {user.last_name}
              </p>
              <p className="text-xs text-slate-500">{user.roles.join(' · ')}</p>
            </div>
            <button className="secondary" disabled={busy} onClick={logout}>
              Sign out
            </button>
          </div>
        </header>
        <main
          id="main-content"
          className="content"
          key={user.id + user.roles.join(',')}
        >
          {staff ? (
            <Management api={api} payroll={payroll} />
          ) : (
            <Routes>
              <Route path="/me" element={<WorkerDetail api={api} self />} />
              <Route
                path="/payroll/*"
                element={<PayrollRoutes api={payroll} hr={api} staff={false} />}
              />
              <Route path="*" element={<Navigate to="/me" replace />} />
            </Routes>
          )}
        </main>
        <footer className="px-6 pb-6 text-xs text-slate-400">
          FusionHCM 360 · Synthetic data only
        </footer>
      </div>
    </div>
  )
}
export function AuthenticatedApp({ client = auth }: { client?: AuthClient }) {
  const api = useMemo(() => new CoreHrClient(client), [client])
  const payroll = useMemo(() => new PayrollClient(client), [client])
  const [user, setUser] = useState<User | null>(null)
  const [restoring, setRestoring] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [logoutFailed, setLogoutFailed] = useState(false)
  useEffect(() => {
    let active = true
    client.setSessionExpiredHandler(() => {
      if (active) {
        setUser(null)
        setError('Your session has expired. Please sign in again.')
      }
    })
    client
      .me()
      .then((current) => {
        if (active) {
          setUser(current)
          setError('')
        }
      })
      .catch((reason) => {
        if (active)
          setError(
            reason instanceof AuthError && reason.status === 401
              ? ''
              : reason.message,
          )
      })
      .finally(() => {
        if (active) setRestoring(false)
      })
    return () => {
      active = false
      client.setSessionExpiredHandler(undefined)
    }
  }, [client])
  const signedIn = Boolean(user)
  useEffect(() => {
    if (!signedIn || busy) return
    let active = true
    let checking = false
    const check = async () => {
      if (checking || document.visibilityState === 'hidden') return
      checking = true
      try {
        const current = await client.me()
        if (active) setUser(current)
      } catch (reason) {
        if (active && reason instanceof AuthError && reason.status === 401)
          setUser(null)
      } finally {
        checking = false
      }
    }
    const timer = window.setInterval(check, 60_000)
    window.addEventListener('focus', check)
    return () => {
      active = false
      window.clearInterval(timer)
      window.removeEventListener('focus', check)
    }
  }, [client, signedIn, busy])
  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError('')
    const data = new FormData(event.currentTarget)
    try {
      setUser(
        await client.login(
          String(data.get('email')).trim(),
          String(data.get('password')),
        ),
      )
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to sign in.')
    } finally {
      setBusy(false)
    }
  }
  async function logout() {
    setBusy(true)
    setUser(null)
    setError('')
    try {
      await client.logout()
      setLogoutFailed(false)
    } catch {
      setLogoutFailed(true)
      setError(
        'Signed out locally, but the session cookie could not be cleared. Retry signing out before leaving this device.',
      )
    } finally {
      setBusy(false)
    }
  }
  if (user)
    return (
      <Workspace
        user={user}
        api={api}
        payroll={payroll}
        logout={logout}
        busy={busy}
      />
    )
  return (
    <main className="login-page">
      <div className="w-full max-w-md">
        <div className="mb-8">
          <span className="brand-mark mb-4">F</span>
          <p className="text-2xl font-semibold tracking-tight">FusionHCM 360</p>
          <p className="text-slate-500 mt-1">
            A connected view of your workforce.
          </p>
        </div>
        <section className="panel" aria-busy={restoring || busy}>
          {restoring ? (
            <Notice>Checking your session…</Notice>
          ) : (
            <>
              <h1>Sign in</h1>
              <p className="hint">Access your people workspace.</p>
              {error && <Notice error>{error}</Notice>}
              {logoutFailed ? (
                <button
                  className="primary mt-5"
                  disabled={busy}
                  onClick={logout}
                >
                  Retry sign out
                </button>
              ) : (
                <form onSubmit={login} className="space-y-5 mt-6">
                  <fieldset disabled={busy} className="space-y-5">
                    <Field
                      label="Email address"
                      name="email"
                      type="email"
                      autoComplete="username"
                      required
                    />
                    <Field
                      label="Password"
                      name="password"
                      type="password"
                      autoComplete="current-password"
                      required
                      maxLength={128}
                    />
                    <button className="primary w-full">
                      {busy ? 'Signing in…' : 'Sign in'}
                    </button>
                  </fieldset>
                </form>
              )}
            </>
          )}
        </section>
        <p className="mt-6 text-xs text-slate-400">
          Independent HCM simulation · Use synthetic data only
        </p>
      </div>
    </main>
  )
}
export default function App() {
  return (
    <BrowserRouter>
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <AuthenticatedApp />
    </BrowserRouter>
  )
}
