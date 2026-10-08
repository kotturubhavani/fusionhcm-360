import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, Routes, Route, useNavigate, useParams } from 'react-router-dom'
import { useLoad } from '../components/useLoad'
import { label } from '../core-hr/types'
import { Badge, LoadState, Notice, PageTitle } from '../components/ui'
import { AnalyticsClient, saveBlob } from './api'
import type { Definition, FieldMeta, Filter, Metadata } from './api'
const domainMap: Record<string, string> = {
  WORKER_SNAPSHOT: 'CORE_HR_WORKERS',
  WORKER_CHANGES: 'CORE_HR_WORKERS',
  PAYROLL_RESULTS: 'PAYROLL_RESULTS',
  FBP_ELECTIONS: 'FBP_ALLOCATIONS',
}
const failure = (e: unknown) =>
  e instanceof Error ? e.message : 'The request failed.'
const base = (extract: boolean) => (extract ? '/extracts' : '/reports')
export function AnalyticsRoutes({
  api,
  extract = false,
}: {
  api: AnalyticsClient
  extract?: boolean
}) {
  return (
    <>
      <p className="notice mb-6">
        Synthetic HCM{' '}
        {extract
          ? 'extract simulator · Application timestamps, not CDC. No Oracle Extract compatibility.'
          : 'reporting · Controlled fields and filters.'}
      </p>
      <Routes>
        <Route index element={<Definitions api={api} extract={extract} />} />
        <Route
          path="new"
          element={<EditorLoader api={api} extract={extract} />}
        />
        <Route
          path=":id/edit"
          element={<EditorLoader api={api} extract={extract} edit />}
        />
        <Route
          path="runs"
          element={<RunHistory api={api} extract={extract} />}
        />
        <Route
          path="runs/:id"
          element={<RunDetail api={api} extract={extract} />}
        />
      </Routes>
    </>
  )
}
export function Definitions({
  api,
  extract,
}: {
  api: AnalyticsClient
  extract: boolean
}) {
  const [offset, setOffset] = useState(0)
  const loaded = useLoad(
    () => api.list(extract, offset),
    [api, extract, offset],
  )
  return (
    <>
      <PageTitle
        title={extract ? 'Extract definitions' : 'Saved reports'}
        description="Saved definitions and run history."
      >
        <Link className="primary" to={`${base(extract)}/new`}>
          New {extract ? 'extract' : 'report'}
        </Link>
        <Link className="secondary" to={`${base(extract)}/runs`}>
          Run history
        </Link>
      </PageTitle>
      <LoadState {...loaded} />
      {loaded.data && (
        <section className="panel">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Domain / type</th>
                  <th>Status</th>
                  {extract && <th>Watermark</th>}
                </tr>
              </thead>
              <tbody>
                {loaded.data.map((d) => (
                  <tr key={d.id}>
                    <td>
                      <Link
                        className="link"
                        to={`${base(extract)}/${d.id}/edit`}
                      >
                        {d.name}
                      </Link>
                      <p className="hint">{d.code}</p>
                    </td>
                    <td>{label(d.domain ?? d.extract_type)}</td>
                    <td>
                      <Badge>{d.is_active ? 'Active' : 'Inactive'}</Badge>
                    </td>
                    {extract && (
                      <td>
                        {d.last_successful_run_at
                          ? new Date(d.last_successful_run_at).toLocaleString()
                          : '—'}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!loaded.data.length && <p>No definitions yet.</p>}
          <button
            className="secondary"
            disabled={!offset}
            onClick={() => setOffset(offset - 50)}
          >
            Previous
          </button>
          <button
            className="secondary ml-3"
            disabled={loaded.data.length < 50}
            onClick={() => setOffset(offset + 50)}
          >
            Next
          </button>
        </section>
      )}
    </>
  )
}
export function Filters({
  fields,
  values,
  onChange,
}: {
  fields: FieldMeta[]
  values: Filter[]
  onChange: (f: Filter[]) => void
}) {
  const change = (i: number, value: Filter) =>
    onChange(values.map((f, n) => (n === i ? value : f)))
  return (
    <fieldset className="space-y-3">
      <legend className="font-semibold">Filters (all must match)</legend>
      {values.map((f, i) => (
        <div className="grid gap-3 sm:grid-cols-4" key={i}>
          <label className="field">
            Filter field {i + 1}
            <select
              value={f.field}
              onChange={(e) =>
                change(i, {
                  field: e.target.value,
                  operator: 'equals',
                  value: '',
                })
              }
            >
              {fields.map((c) => (
                <option key={c.key} value={c.key}>
                  {c.label}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            Operator {i + 1}
            <select
              value={f.operator}
              onChange={(e) =>
                change(i, {
                  ...f,
                  operator: e.target.value,
                  value: e.target.value === 'in' ? [] : '',
                })
              }
            >
              {fields
                .find((c) => c.key === f.field)
                ?.operators.map((op) => (
                  <option key={op}>{op}</option>
                ))}
            </select>
          </label>
          <label className="field">
            Value {i + 1}
            <input
              value={Array.isArray(f.value) ? f.value.join('|') : f.value}
              onChange={(e) =>
                change(i, {
                  ...f,
                  value:
                    f.operator === 'in'
                      ? e.target.value.split('|')
                      : e.target.value,
                })
              }
            />
          </label>
          <button
            type="button"
            className="secondary"
            onClick={() => onChange(values.filter((_, n) => i !== n))}
          >
            Remove filter {i + 1}
          </button>
        </div>
      ))}
      <p className="hint">
        IN values use | separators. Dates use YYYY-MM-DD; timestamps include a
        timezone. Blank source values do not match filters.
      </p>
      <button
        className="secondary"
        type="button"
        disabled={values.length >= 20}
        onClick={() =>
          onChange([
            ...values,
            { field: fields[0].key, operator: 'equals', value: '' },
          ])
        }
      >
        Add filter
      </button>
    </fieldset>
  )
}
function EditorLoader({
  api,
  extract,
  edit = false,
}: {
  api: AnalyticsClient
  extract: boolean
  edit?: boolean
}) {
  const { id = '' } = useParams()
  const loaded = useLoad(
    async () => ({
      metadata: await api.metadata(),
      definition: edit ? await api.definition(extract, id) : null,
    }),
    [api, extract, id, edit],
  )
  return loaded.data ? (
    <DefinitionEditor
      key={id || 'new'}
      api={api}
      extract={extract}
      metadata={loaded.data.metadata}
      initial={loaded.data.definition}
    />
  ) : (
    <LoadState {...loaded} />
  )
}
export function DefinitionEditor({
  api,
  extract,
  metadata,
  initial,
}: {
  api: AnalyticsClient
  extract: boolean
  metadata: Metadata
  initial: Definition | null
}) {
  const navigate = useNavigate()
  const [code, setCode] = useState(initial?.code ?? '')
  const [name, setName] = useState(initial?.name ?? '')
  const [description, setDescription] = useState(initial?.description ?? '')
  const [kind, setKind] = useState(
    initial?.extract_type ??
      initial?.domain ??
      (extract ? 'WORKER_SNAPSHOT' : 'CORE_HR_WORKERS'),
  )
  const [columns, setColumns] = useState(
    initial?.selected_columns ??
      metadata.CORE_HR_WORKERS.map((c) => c.key).slice(0, 5),
  )
  const [filters, setFilters] = useState(
    initial?.configuration?.filters ?? initial?.filters ?? [],
  )
  const [sort, setSort] = useState(initial?.sort_definition?.[0]?.field ?? '')
  const [direction, setDirection] = useState(
    initial?.sort_definition?.[0]?.direction ?? 'asc',
  )
  const [format, setFormat] = useState(initial?.output_format ?? 'CSV')
  const [active, setActive] = useState(initial?.is_active ?? true)
  const [mode, setMode] = useState('FULL')
  const [asOf, setAsOf] = useState(() => new Date().toISOString().slice(0, 10))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(initial?.id ?? '')
  const [dirty, setDirty] = useState(false)
  const fields = metadata[extract ? domainMap[kind] : kind]
  const payload = extract
    ? {
        code,
        name,
        extract_type: kind,
        output_format: format,
        is_active: active,
        configuration: { filters },
      }
    : {
        code,
        name,
        description: description || null,
        domain: kind,
        selected_columns: columns,
        filters,
        sort_definition: sort ? [{ field: sort, direction }] : [],
        is_active: active,
      }
  async function save(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const d = await api.save(extract, payload, saved || undefined)
      setSaved(d.id)
      setDirty(false)
    } catch (e) {
      setError(failure(e))
    } finally {
      setBusy(false)
    }
  }
  async function run() {
    setBusy(true)
    setError('')
    try {
      const r = await api.run(
        extract,
        saved,
        extract ? { mode } : { as_of: asOf },
      )
      navigate(`${base(extract)}/runs/${r.id}`)
    } catch (e) {
      setError(failure(e))
    } finally {
      setBusy(false)
    }
  }
  function move(i: number, step: number) {
    const next = [...columns]
    ;[next[i], next[i + step]] = [next[i + step], next[i]]
    setColumns(next)
    setDirty(true)
  }
  return (
    <>
      <PageTitle
        title={`${initial ? 'Edit' : 'New'} ${extract ? 'extract' : 'report'}`}
        description="Save the definition before running it."
      >
        <Link className="link" to={base(extract)}>
          Back to definitions
        </Link>
      </PageTitle>
      {error && <Notice error>{error}</Notice>}
      <section className="panel">
        <form
          onSubmit={save}
          onChange={() => setDirty(true)}
          className="space-y-5"
        >
          <fieldset disabled={busy} className="space-y-5">
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="field">
                Code
                <input
                  required
                  maxLength={30}
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                />
              </label>
              <label className="field">
                Name
                <input
                  required
                  maxLength={150}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </label>
            </div>
            <label className="field">
              {extract ? 'Extract type' : 'Domain'}
              <select
                value={kind}
                onChange={(e) => {
                  setKind(e.target.value)
                  setFilters([])
                  setSort('')
                  setColumns(
                    metadata[
                      extract ? domainMap[e.target.value] : e.target.value
                    ]
                      .map((c) => c.key)
                      .slice(0, 5),
                  )
                }}
              >
                {Object.keys(extract ? domainMap : metadata).map((d) => (
                  <option key={d}>{d}</option>
                ))}
              </select>
            </label>
            {!extract && (
              <>
                <label className="field">
                  Description
                  <input
                    maxLength={2000}
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                  />
                </label>
                <fieldset>
                  <legend className="font-semibold">
                    Columns (selection order is export order)
                  </legend>
                  <div className="grid gap-2 sm:grid-cols-3">
                    {fields.map((c) => (
                      <label key={c.key} className="flex gap-2">
                        <input
                          type="checkbox"
                          checked={columns.includes(c.key)}
                          onChange={(e) =>
                            setColumns(
                              e.target.checked
                                ? [...columns, c.key]
                                : columns.filter((x) => x !== c.key),
                            )
                          }
                        />
                        {c.label}
                      </label>
                    ))}
                  </div>
                  <ol className="mt-3 space-y-2">
                    {columns.map((c, i) => (
                      <li key={c}>
                        {i + 1}. {fields.find((f) => f.key === c)?.label}{' '}
                        <button
                          type="button"
                          className="link ml-2"
                          disabled={!i}
                          onClick={() => move(i, -1)}
                        >
                          Move {c} up
                        </button>
                        <button
                          type="button"
                          className="link ml-2"
                          disabled={i === columns.length - 1}
                          onClick={() => move(i, 1)}
                        >
                          Move {c} down
                        </button>
                      </li>
                    ))}
                  </ol>
                </fieldset>
              </>
            )}
            <Filters
              fields={fields}
              values={filters}
              onChange={(f) => {
                setFilters(f)
                setDirty(true)
              }}
            />
            {extract ? (
              <label className="field">
                Output format
                <select
                  value={format}
                  onChange={(e) => setFormat(e.target.value)}
                >
                  <option>CSV</option>
                  <option>JSON</option>
                </select>
              </label>
            ) : (
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="field">
                  Sort field
                  <select
                    value={sort}
                    onChange={(e) => setSort(e.target.value)}
                  >
                    <option value="">Stable record order</option>
                    {fields.map((c) => (
                      <option key={c.key} value={c.key}>
                        {c.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  Direction
                  <select
                    value={direction}
                    onChange={(e) => setDirection(e.target.value)}
                  >
                    <option value="asc">Ascending</option>
                    <option value="desc">Descending</option>
                  </select>
                </label>
              </div>
            )}
            <label className="flex gap-2">
              <input
                type="checkbox"
                checked={active}
                onChange={(e) => setActive(e.target.checked)}
              />
              Active
            </label>
            <button className="primary">Save definition</button>
          </fieldset>
        </form>
      </section>
      {saved && (
        <section className="panel mt-6">
          <h2>Run {extract ? 'extract' : 'report preview'}</h2>
          {dirty && <Notice>Save your changes before running.</Notice>}
          {extract ? (
            <>
              <label className="field my-4">
                Mode
                <select value={mode} onChange={(e) => setMode(e.target.value)}>
                  <option>FULL</option>
                  <option>INCREMENTAL</option>
                </select>
              </label>
              <p className="hint mb-4">
                First incremental run includes all eligible records. Later runs
                use the last successful watermark. Changing scope after a
                successful run requires a new definition.
              </p>
            </>
          ) : (
            <label className="field my-4">
              As-of date (Core HR)
              <input
                type="date"
                required
                value={asOf}
                onChange={(e) => setAsOf(e.target.value)}
              />
            </label>
          )}
          <button
            className="primary"
            disabled={busy || dirty || !active}
            onClick={run}
          >
            {busy ? 'Running…' : 'Run now'}
          </button>
        </section>
      )}
    </>
  )
}
export function RunHistory({
  api,
  extract,
}: {
  api: AnalyticsClient
  extract: boolean
}) {
  const [offset, setOffset] = useState(0)
  const loaded = useLoad(
    () => api.runs(extract, offset),
    [api, extract, offset],
  )
  return (
    <>
      <PageTitle title="Run history">
        <Link to={base(extract)} className="link">
          Definitions
        </Link>
      </PageTitle>
      <LoadState {...loaded} />
      {loaded.data && (
        <section className="panel">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Status</th>
                  <th>Rows</th>
                  <th>Mode</th>
                  <th>Started</th>
                </tr>
              </thead>
              <tbody>
                {loaded.data.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <Link
                        className="link"
                        to={`${base(extract)}/runs/${r.id}`}
                      >
                        {String(r.definition_snapshot.name)}
                      </Link>
                    </td>
                    <td>{r.status}</td>
                    <td>{r.row_count}</td>
                    <td>{r.mode ?? 'Report'}</td>
                    <td>{r.started_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button
            className="secondary"
            disabled={!offset}
            onClick={() => setOffset(offset - 50)}
          >
            Previous
          </button>
          <button
            className="secondary ml-3"
            disabled={loaded.data.length < 50}
            onClick={() => setOffset(offset + 50)}
          >
            Next
          </button>
        </section>
      )}
    </>
  )
}
export function RunDetail({
  api,
  extract,
}: {
  api: AnalyticsClient
  extract: boolean
}) {
  const { id = '' } = useParams()
  const [offset, setOffset] = useState(0)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const loaded = useLoad(async () => {
    const run = await api.result(extract, id)
    return {
      run,
      results:
        !extract && run.status === 'COMPLETED'
          ? await api.rows(id, offset)
          : null,
    }
  }, [api, extract, id, offset])
  async function download(format = 'csv') {
    setBusy(true)
    setError('')
    try {
      const blob = await api.download(extract, id, format)
      saveBlob(
        blob,
        extract
          ? (loaded.data?.run.output_filename ?? 'extract.csv')
          : `report-${id}.${format}`,
      )
    } catch (e) {
      setError(failure(e))
    } finally {
      setBusy(false)
    }
  }
  const run = loaded.data?.run
  const results = loaded.data?.results
  return (
    <>
      <PageTitle title={extract ? 'Extract run' : 'Report results'}>
        <Link className="link" to={`${base(extract)}/runs`}>
          Run history
        </Link>
      </PageTitle>
      <LoadState {...loaded} />
      {error && <Notice error>{error}</Notice>}
      {run && (
        <section className="panel space-y-4">
          <h2>{String(run.definition_snapshot.name)}</h2>
          <Badge>{run.status}</Badge>
          <p>
            {run.row_count} rows · Completed {run.completed_at ?? 'Not yet'}
          </p>
          {run.error_message && <Notice error>{run.error_message}</Notice>}
          {extract && (
            <dl>
              <dt>Mode</dt>
              <dd>{run.mode}</dd>
              <dt>Watermark from (exclusive)</dt>
              <dd>{run.watermark_from ?? 'Initial baseline'}</dd>
              <dt>Watermark to (inclusive)</dt>
              <dd>{run.watermark_to}</dd>
            </dl>
          )}
          {run.status === 'COMPLETED' && (
            <div className="flex gap-3">
              <button
                className="secondary"
                disabled={busy}
                onClick={() => download()}
              >
                {extract ? 'Download output' : 'Export CSV'}
              </button>
              {!extract && (
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() => download('xlsx')}
                >
                  Export XLSX
                </button>
              )}
            </div>
          )}
        </section>
      )}
      {results && (
        <section className="panel mt-6">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  {results.columns.map((c) => (
                    <th key={c}>{c.replaceAll('_', ' ')}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {results.rows.map((row, i) => (
                  <tr key={i}>
                    {results.columns.map((c) => (
                      <td key={c}>{row[c] === null ? '—' : String(row[c])}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p>{results.total} total rows</p>
          <button
            className="secondary"
            disabled={!offset}
            onClick={() => setOffset(offset - 100)}
          >
            Previous rows
          </button>
          <button
            className="secondary ml-3"
            disabled={offset + 100 >= results.total}
            onClick={() => setOffset(offset + 100)}
          >
            Next rows
          </button>
        </section>
      )}
    </>
  )
}
