import { useEffect, useState } from 'react'

type BackendStatus = 'loading' | 'connected' | 'unavailable'

const API_BASE = import.meta.env.VITE_API_BASE_URL as string

export default function App() {
  const [backendStatus, setBackendStatus] = useState<BackendStatus>('loading')

  useEffect(() => {
    fetch(`${API_BASE}/health`)
      .then((res) => {
        if (!res.ok) throw new Error()
        setBackendStatus('connected')
      })
      .catch(() => setBackendStatus('unavailable'))
  }, [])

  return (
    <main className="min-h-screen bg-slate-950 flex items-center justify-center">
      <div className="text-center space-y-4">
        <h1 className="text-4xl font-bold text-white tracking-tight">
          FusionHCM 360
        </h1>
        <p className="text-slate-400 text-lg">
          Enterprise Human Capital Management Platform
        </p>
        <div className="space-y-1 pt-2 text-sm font-medium">
          <p className="text-emerald-400">Frontend: Running</p>
          <p className={
            backendStatus === 'loading'     ? 'text-slate-400' :
            backendStatus === 'connected'   ? 'text-emerald-400' :
                                              'text-red-400'
          }>
            {backendStatus === 'loading'     && 'Backend: Checking…'}
            {backendStatus === 'connected'   && 'Backend: Connected'}
            {backendStatus === 'unavailable' && 'Backend: Unavailable'}
          </p>
        </div>
      </div>
    </main>
  )
}
