import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, Route, Routes, useNavigate, useParams } from 'react-router-dom'
import { useLoad } from '../components/useLoad'
import { Badge, LoadState, Notice, PageTitle } from '../components/ui'
import { ImportsClient, downloadCsv } from './api'

const message = (e: unknown) =>
  e instanceof Error ? e.message : 'The request could not be completed.'
export function ImportsRoutes({ api }: { api: ImportsClient }) {
  return (
    <>
      <p className="notice mb-6">
        HCM bulk import simulation · Our CSV format; no Oracle HDL
        compatibility. Use synthetic data only.
      </p>
      <Routes>
        <Route index element={<ImportDashboard api={api} />} />
        <Route path="new" element={<NewImport api={api} />} />
        <Route path=":id" element={<ImportDetail api={api} />} />
      </Routes>
    </>
  )
}
export function ImportDashboard({ api }: { api: ImportsClient }) {
  const [offset, setOffset] = useState(0)
  const loaded = useLoad(() => api.jobs(offset), [api, offset])
  return (
    <>
      <PageTitle
        title="Imports"
        description="Upload, validate and process Core HR changes."
      >
        <Link className="primary" to="/imports/new">
          New import
        </Link>
      </PageTitle>
      <LoadState {...loaded} />
      {loaded.data && (
        <section className="panel">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>File / type</th>
                  <th>Status</th>
                  <th>Rows</th>
                  <th>Valid / invalid</th>
                  <th>Processed / failed</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {loaded.data.map((j) => (
                  <tr key={j.id}>
                    <td>
                      <Link className="link" to={`/imports/${j.id}`}>
                        {j.original_filename}
                      </Link>
                      <p className="hint">{j.object_type}</p>
                    </td>
                    <td>
                      <Badge>{j.status}</Badge>
                    </td>
                    <td>{j.total_rows}</td>
                    <td>
                      {j.valid_rows} / {j.invalid_rows}
                    </td>
                    <td>
                      {j.processed_rows} / {j.failed_rows}
                    </td>
                    <td>{new Date(j.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!loaded.data.length && <p>No import jobs yet.</p>}
          <div className="flex gap-3 mt-4">
            <button
              className="secondary"
              disabled={!offset}
              onClick={() => setOffset(offset - 50)}
            >
              Previous jobs
            </button>
            <button
              className="secondary"
              disabled={loaded.data.length < 50}
              onClick={() => setOffset(offset + 50)}
            >
              Next jobs
            </button>
          </div>
        </section>
      )}
    </>
  )
}
export function NewImport({ api }: { api: ImportsClient }) {
  const loaded = useLoad(() => api.templates(), [api])
  const navigate = useNavigate()
  const [kind, setKind] = useState('WORKER_HIRE')
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const selected = loaded.data?.find((t) => t.object_type === kind)
  async function download() {
    setError('')
    try {
      downloadCsv(await api.template(kind), `${kind}.csv`)
    } catch (e) {
      setError(message(e))
    }
  }
  async function upload(event: FormEvent) {
    event.preventDefault()
    if (!file) return
    setBusy(true)
    setError('')
    try {
      const job = await api.upload(kind, file)
      navigate(`/imports/${job.id}`)
    } catch (e) {
      setError(message(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <PageTitle
        title="New import"
        description="Uploading saves a preview job; it does not change workers."
      >
        <Link className="link" to="/imports">
          Import history
        </Link>
      </PageTitle>
      <LoadState {...loaded} />
      {error && <Notice error>{error}</Notice>}
      {selected && (
        <section className="panel">
          <form onSubmit={upload} className="space-y-5">
            <fieldset disabled={busy} className="space-y-5">
              <label className="field">
                Object type
                <select value={kind} onChange={(e) => setKind(e.target.value)}>
                  {loaded.data?.map((t) => (
                    <option key={t.object_type}>{t.object_type}</option>
                  ))}
                </select>
              </label>
              <button type="button" className="secondary" onClick={download}>
                Download template
              </button>
              <p className="hint">
                UTF-8 CSV. Default limits: 5 MB, 5,000 rows. One operation per
                target per file. References must already exist.
              </p>
              <p>
                <strong>Required:</strong> {selected.required.join(', ')}
              </p>
              <p className="hint">
                Optional:{' '}
                {selected.columns
                  .filter((c) => !selected.required.includes(c))
                  .join(', ') || 'None'}
              </p>
              <p className="hint">
                Dates: YYYY-MM-DD. Salary: decimal text without separators.
                PERSON_UPDATE blanks leave values unchanged; &lt;CLEAR&gt;
                clears optional fields. Assignment changes are complete
                snapshots; blank grade/manager clears that relationship.
              </p>
              <label className="field">
                CSV file
                <input
                  type="file"
                  accept=".csv,text/csv"
                  required
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                />
              </label>
              <button className="primary" disabled={!file}>
                {busy ? 'Uploading…' : 'Upload CSV'}
              </button>
            </fieldset>
          </form>
        </section>
      )}
    </>
  )
}
export function ImportDetail({ api }: { api: ImportsClient }) {
  const { id = '' } = useParams()
  const [filter, setFilter] = useState('')
  const [offset, setOffset] = useState(0)
  const loaded = useLoad(() => api.job(id), [api, id])
  const items = useLoad(
    () => api.rows(id, filter, offset),
    [api, id, filter, offset],
  )
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  async function act(action: 'validate' | 'process') {
    setBusy(true)
    setError('')
    try {
      await api.action(id, action)
      setConfirmed(false)
      loaded.reload()
      items.reload()
    } catch (e) {
      setError(message(e))
    } finally {
      setBusy(false)
    }
  }
  async function errors() {
    setError('')
    try {
      downloadCsv(await api.errors(id), `import-${id}-errors.csv`)
    } catch (e) {
      setError(message(e))
    }
  }
  const job = loaded.data
  return (
    <>
      <PageTitle
        title="Import detail"
        description="Review row outcomes before processing."
      >
        <Link className="link" to="/imports">
          Import history
        </Link>
      </PageTitle>
      <LoadState {...loaded} />
      {error && <Notice error>{error}</Notice>}
      {job && (
        <>
          <section className="panel space-y-4">
            <h2>{job.original_filename}</h2>
            <p>
              {job.object_type} · <Badge>{job.status}</Badge>
            </p>
            <dl className="grid gap-4 sm:grid-cols-5">
              {[
                ['Total', job.total_rows],
                ['Valid', job.valid_rows],
                ['Invalid', job.invalid_rows],
                ['Processed', job.processed_rows],
                ['Failed', job.failed_rows],
              ].map(([k, v]) => (
                <div key={k}>
                  <dt>{k}</dt>
                  <dd className="text-xl font-semibold">{v}</dd>
                </div>
              ))}
            </dl>
            <p className="hint">
              Uploaded {new Date(job.created_at).toLocaleString()} · Uploader{' '}
              {job.created_by_user_id ?? 'Deleted account'}
              <br />
              Validated{' '}
              {job.validated_at
                ? new Date(job.validated_at).toLocaleString()
                : 'Not yet'}{' '}
              · Processed{' '}
              {job.processed_at
                ? new Date(job.processed_at).toLocaleString()
                : 'Not yet'}
            </p>
            {['UPLOADED', 'VALIDATED'].includes(job.status) && (
              <button
                className="secondary"
                disabled={busy}
                onClick={() => act('validate')}
              >
                Validate / dry run
              </button>
            )}
            {job.status === 'VALIDATED' && job.valid_rows > 0 && (
              <div className="space-y-3">
                <label className="flex gap-2">
                  <input
                    type="checkbox"
                    checked={confirmed}
                    onChange={(e) => setConfirmed(e.target.checked)}
                  />
                  I confirm processing {job.valid_rows} valid rows will change
                  Core HR records.
                </label>
                <button
                  className="primary"
                  disabled={!confirmed || busy}
                  onClick={() => act('process')}
                >
                  Process valid rows
                </button>
              </div>
            )}
            {!['UPLOADED', 'VALIDATED'].includes(job.status) && (
              <Notice>
                This job is locked. To correct rows, upload a new file;
                successful rows must not be repeated.
              </Notice>
            )}
            <button className="secondary" disabled={busy} onClick={errors}>
              Download errors CSV
            </button>
            {busy && <Notice>Working… Keep this page open.</Notice>}
          </section>
          <section className="panel mt-6">
            <h2>Row results</h2>
            <label className="field my-4">
              Row status
              <select
                value={filter}
                onChange={(e) => {
                  setFilter(e.target.value)
                  setOffset(0)
                }}
              >
                {['', 'PENDING', 'VALID', 'INVALID', 'PROCESSED', 'FAILED'].map(
                  (s) => (
                    <option key={s} value={s}>
                      {s || 'All'}
                    </option>
                  ),
                )}
              </select>
            </label>
            <LoadState {...items} />
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>CSV record</th>
                    <th>Status</th>
                    <th>Outcome</th>
                    <th>Values</th>
                  </tr>
                </thead>
                <tbody>
                  {items.data?.map((row) => (
                    <tr key={row.id}>
                      <td>{row.row_number}</td>
                      <td>
                        <Badge>{row.status}</Badge>
                      </td>
                      <td>
                        <strong>{row.error_code}</strong>
                        <p>{row.error_message}</p>
                        {row.created_record_reference && (
                          <pre className="whitespace-pre-wrap break-all">
                            {JSON.stringify(
                              row.created_record_reference,
                              null,
                              2,
                            )}
                          </pre>
                        )}
                      </td>
                      <td>
                        <details>
                          <summary>Raw values</summary>
                          <pre className="whitespace-pre-wrap break-all">
                            {JSON.stringify(row.raw_data, null, 2)}
                          </pre>
                        </details>
                        {row.normalized_data && (
                          <details>
                            <summary>Normalized values</summary>
                            <pre className="whitespace-pre-wrap break-all">
                              {JSON.stringify(row.normalized_data, null, 2)}
                            </pre>
                          </details>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex gap-3 mt-4">
              <button
                className="secondary"
                disabled={!offset || items.busy}
                onClick={() => setOffset(offset - 100)}
              >
                Previous rows
              </button>
              <button
                className="secondary"
                disabled={!items.data || items.data.length < 100 || items.busy}
                onClick={() => setOffset(offset + 100)}
              >
                Next rows
              </button>
            </div>
          </section>
        </>
      )}
    </>
  )
}
