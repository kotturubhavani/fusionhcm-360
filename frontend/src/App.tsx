import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { AuthClient, AuthError } from './auth'
import type { User } from './auth'

const auth = new AuthClient(import.meta.env.VITE_API_BASE_URL ?? '')
const button = 'w-full rounded-xl bg-teal-700 px-4 py-3 font-semibold text-white transition hover:bg-teal-800 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-teal-600 disabled:cursor-wait disabled:opacity-60'
const input = 'mt-2 w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-slate-900 outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-600/20'

export default function App() {
  const [user, setUser] = useState<User | null>(null)
  const [restoring, setRestoring] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [logoutFailed, setLogoutFailed] = useState(false)
  const operation = useRef(0)
  const signedIn = Boolean(user)

  useEffect(() => {
    let active = true
    auth.me().then(current => { if (active) setUser(current) }).catch(reason => {
      if (active && !(reason instanceof AuthError && reason.status === 401)) setError(reason.message)
    }).finally(() => { if (active) setRestoring(false) })
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (!signedIn || busy) return
    let active = true
    let checking = false
    const currentOperation = operation.current
    const checkSession = async () => {
      if (checking || document.visibilityState === 'hidden') return
      checking = true
      try {
        const current = await auth.me()
        if (active && currentOperation === operation.current) { setUser(current); setError('') }
      } catch (reason) {
        if (active && currentOperation === operation.current) {
          if (reason instanceof AuthError && reason.status === 401) setUser(null)
          setError(reason instanceof Error ? reason.message : 'Unable to check your session.')
        }
      } finally { checking = false }
    }
    window.addEventListener('focus', checkSession)
    const timer = window.setInterval(checkSession, 60_000)
    return () => { active = false; window.clearInterval(timer); window.removeEventListener('focus', checkSession) }
  }, [signedIn, busy])

  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const data = new FormData(form)
    operation.current++
    setBusy(true)
    setError('')
    try {
      setUser(await auth.login(String(data.get('email')).trim(), String(data.get('password'))))
      form.reset()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to sign in.')
    } finally { setBusy(false) }
  }

  async function logout() {
    operation.current++
    setBusy(true)
    setUser(null)
    setError('')
    try {
      await auth.logout()
      setLogoutFailed(false)
    } catch {
      setLogoutFailed(true)
      setError('Signed out locally, but the server could not clear your session cookie. Retry signing out before leaving this device.')
    } finally { setBusy(false) }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-100 px-5 py-12 text-slate-900">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-teal-700 text-lg font-bold text-white" aria-hidden="true">F</div>
          <p className="text-xl font-bold tracking-tight">FusionHCM 360</p>
          <p className="mt-1 text-sm text-slate-500">People. Connected.</p>
        </div>
        <section aria-label="Account" aria-busy={busy || restoring} className="rounded-3xl border border-slate-200 bg-white p-7 shadow-sm sm:p-9">
          {restoring ? <p role="status" className="py-8 text-center text-slate-600">Checking your session…</p> : <>
            <h1 className="text-2xl font-semibold tracking-tight">{user ? `Welcome, ${user.first_name}` : 'Sign in'}</h1>
            <p className="mt-2 text-sm text-slate-500">{user ? 'You are signed in to your account.' : 'Use your account to access FusionHCM 360.'}</p>
            {error && <p role="alert" className="mt-5 rounded-xl bg-red-50 p-3 text-sm text-red-800">{error}</p>}
            {user ? <div className="mt-7 space-y-6">
              <dl className="space-y-4 text-sm">
                <div><dt className="text-slate-500">Name</dt><dd className="mt-1 font-medium">{user.first_name} {user.last_name}</dd></div>
                <div><dt className="text-slate-500">Email</dt><dd className="mt-1 break-all font-medium">{user.email}</dd></div>
                <div><dt className="text-slate-500">Roles</dt><dd className="mt-2 flex flex-wrap gap-2">{user.roles.map(role => <span key={role} className="rounded-full bg-teal-50 px-3 py-1 text-xs font-semibold text-teal-800">{role}</span>)}</dd></div>
              </dl>
              <button type="button" disabled={busy} onClick={logout} className={button}>Sign out</button>
            </div> : logoutFailed ? <button className={`${button} mt-6`} disabled={busy} onClick={logout}>{busy ? 'Signing out…' : 'Retry sign out'}</button> : <form onSubmit={login} className="mt-7 space-y-5">
              <div><label htmlFor="email" className="text-sm font-medium">Email address</label><input className={input} id="email" name="email" type="email" autoComplete="username" placeholder="you@company.com" required disabled={busy} /></div>
              <div><label htmlFor="password" className="text-sm font-medium">Password</label><input className={input} id="password" name="password" type="password" autoComplete="current-password" required maxLength={128} disabled={busy} /></div>
              <button className={button} disabled={busy} type="submit">{busy ? 'Please wait…' : 'Sign in'}</button>
            </form>}
          </>}
        </section>
        <p className="mt-6 text-center text-xs text-slate-500">Enterprise Human Capital Management</p>
      </div>
    </main>
  )
}
