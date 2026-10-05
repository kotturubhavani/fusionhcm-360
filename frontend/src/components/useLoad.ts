import { useEffect, useState } from 'react'
import type { DependencyList } from 'react'
export function useLoad<T>(loader: () => Promise<T>, deps: DependencyList) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(true)
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    let active = true
    // Clear stale results when the requested resource changes.
    // eslint-disable-next-line react/set-state-in-effect
    setBusy(true)
    setError('')
    setData(null)
    loader()
      .then((value) => {
        if (active) setData(value)
      })
      .catch((reason) => {
        if (active)
          setError(
            reason instanceof Error ? reason.message : 'Unable to load data.',
          )
      })
      .finally(() => {
        if (active) setBusy(false)
      })
    return () => {
      active = false
    }
    // Callers supply all values captured by their loader.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, revision])
  return { data, error, busy, reload: () => setRevision((value) => value + 1) }
}
