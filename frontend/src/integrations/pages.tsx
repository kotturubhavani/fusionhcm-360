import { useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { Link, Route, Routes, useNavigate, useParams } from 'react-router-dom'
import { Badge, LoadState, Notice, PageTitle } from '../components/ui'
import { useLoad } from '../components/useLoad'
import { saveBlob } from '../analytics/api'
import type {
  Config,
  Definition,
  DefinitionInput,
  IntegrationsClient,
  Run,
} from './api'
const outbound = ['WORKER_EXPORT', 'PAYROLL_EXPORT', 'FBP_EXPORT']
const inbound = ['PERSON_UPDATE', 'ASSIGNMENT_CHANGE', 'COMPENSATION_CHANGE']
const message = (e: unknown) =>
  e instanceof Error ? e.message : 'Operation could not be completed.'
const date = (value: string | null) =>
  value ? new Date(value).toLocaleString() : '—'
function Input({
  label,
  value,
  onChange,
  required = false,
  type = 'text',
  maxLength = 150,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  required?: boolean
  type?: string
  maxLength?: number
}) {
  return (
    <label className="field">
      {label}
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        type={type}
        maxLength={maxLength}
      />
    </label>
  )
}
function Choice({
  label,
  value,
  onChange,
  options,
  disabled = false,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  options: string[]
  disabled?: boolean
}) {
  return (
    <label className="field">
      {label}
      <select
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((o) => (
          <option key={o}>{o}</option>
        ))}
      </select>
    </label>
  )
}
function Pages({
  offset,
  setOffset,
  count,
}: {
  offset: number
  setOffset: (n: number) => void
  count: number
}) {
  return (
    <div className="flex gap-3 mt-4">
      <button
        className="secondary"
        disabled={!offset}
        onClick={() => setOffset(offset - 50)}
      >
        Previous
      </button>
      <span>Page {offset / 50 + 1}</span>
      <button
        className="secondary"
        disabled={count < 50}
        onClick={() => setOffset(offset + 50)}
      >
        Next
      </button>
    </div>
  )
}
function RunTable({ runs }: { runs: Run[] }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Integration</th>
            <th>Status</th>
            <th>Read / succeeded / failed</th>
            <th>Started</th>
            <th>Completed</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.id}>
              <td>
                <Link to={'/integrations/runs/' + r.id}>
                  {r.definition_snapshot.name}
                </Link>
              </td>
              <td>
                <Badge>{r.status}</Badge>
              </td>
              <td>
                {r.records_read} / {r.records_succeeded} / {r.records_failed}
              </td>
              <td>{date(r.started_at)}</td>
              <td>{date(r.completed_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {!runs.length && <Notice>No runs yet.</Notice>}
    </div>
  )
}
export function Dashboard({ api }: { api: IntegrationsClient }) {
  const [offset, setOffset] = useState(0)
  const defs = useLoad(() => api.list(offset), [api, offset])
  const runs = useLoad(() => api.runs(), [api])
  return (
    <>
      <PageTitle
        title="Integration Center"
        description="Exchange synthetic workforce data and monitor delivery."
      >
        <Link className="primary" to="/integrations/new">
          Create integration
        </Link>
        <Link className="secondary" to="/integrations/history">
          Run history
        </Link>
      </PageTitle>
      <section className="panel">
        <h2>Definitions</h2>
        <LoadState {...defs} />
        {defs.data && (
          <>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Name / code</th>
                    <th>Direction / type</th>
                    <th>Transport</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {defs.data.map((d) => (
                    <tr key={d.id}>
                      <td>
                        <Link to={'/integrations/' + d.id}>{d.name}</Link>
                        <p className="hint">{d.code}</p>
                      </td>
                      <td>
                        {d.direction}
                        <p className="hint">{d.integration_type}</p>
                      </td>
                      <td>{d.transport_type}</td>
                      <td>{d.is_active ? 'Active' : 'Inactive'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!defs.data.length && <Notice>No integrations defined.</Notice>}
            <Pages
              offset={offset}
              setOffset={setOffset}
              count={defs.data.length}
            />
          </>
        )}
      </section>
      <section className="panel mt-5">
        <h2>Recent runs</h2>
        <LoadState {...runs} />
        {runs.data && <RunTable runs={runs.data.slice(0, 10)} />}
      </section>
    </>
  )
}
const blank: DefinitionInput = {
  code: '',
  name: '',
  description: null,
  direction: 'OUTBOUND',
  integration_type: 'WORKER_EXPORT',
  transport_type: 'FILE',
  endpoint_url: null,
  http_method: null,
  output_format: 'JSON',
  configuration: { auth_type: 'NONE', active_workers_only: true },
  is_active: true,
}
export function DefinitionForm({
  api,
  existing,
}: {
  api: IntegrationsClient
  existing?: Definition
}) {
  const [value, setValue] = useState<DefinitionInput>(
    existing
      ? {
          code: existing.code,
          name: existing.name,
          description: existing.description,
          direction: existing.direction,
          integration_type: existing.integration_type,
          transport_type: existing.transport_type,
          endpoint_url: existing.endpoint_url,
          http_method: existing.http_method,
          output_format: existing.output_format,
          configuration: existing.configuration,
          is_active: existing.is_active,
        }
      : blank,
  )
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('')
  const navigate = useNavigate()
  const isInbound = value.direction === 'INBOUND',
    http = value.transport_type === 'HTTP_REST'
  function change(patch: Partial<DefinitionInput>) {
    setValue((v) => ({ ...v, ...patch }))
  }
  function config(patch: Partial<Config>) {
    setValue((v) => ({ ...v, configuration: { ...v.configuration, ...patch } }))
  }
  function mode(
    direction: DefinitionInput['direction'],
    transport: DefinitionInput['transport_type'],
    kind: string,
  ) {
    const auth = direction === 'INBOUND' ? 'BEARER_ENV' : 'NONE'
    change({
      direction,
      transport_type: transport,
      integration_type: kind,
      endpoint_url: null,
      http_method:
        direction === 'OUTBOUND' && transport === 'HTTP_REST' ? 'POST' : null,
      output_format:
        direction === 'INBOUND' && transport === 'FILE' ? 'CSV' : 'JSON',
      configuration: { auth_type: auth, active_workers_only: true },
    })
  }
  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const saved = await api.save(value, existing?.id)
      navigate('/integrations/' + saved.id)
    } catch (e) {
      setError(message(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <PageTitle
        title={existing ? 'Edit integration' : 'Create integration'}
        description="Use synthetic data. Credential references are configured by the local application operator."
      />
      <form onSubmit={submit} className="panel space-y-5">
        {error && <Notice error>{error}</Notice>}
        <fieldset disabled={busy} className="space-y-5">
          <div className="grid gap-4 md:grid-cols-2">
            <Input
              label="Code"
              value={value.code}
              onChange={(code) => change({ code })}
              required
              maxLength={30}
            />
            <Input
              label="Name"
              value={value.name}
              onChange={(name) => change({ name })}
              required
            />
            <Input
              label="Description"
              value={value.description ?? ''}
              onChange={(description) =>
                change({ description: description || null })
              }
              maxLength={2000}
            />
            <Choice
              label="Direction"
              value={value.direction}
              options={['OUTBOUND', 'INBOUND']}
              disabled={!!existing}
              onChange={(d) =>
                mode(
                  d as DefinitionInput['direction'],
                  value.transport_type,
                  d === 'INBOUND' ? inbound[0] : outbound[0],
                )
              }
            />
            <Choice
              label="Integration type"
              value={value.integration_type}
              options={isInbound ? inbound : outbound}
              disabled={!!existing}
              onChange={(kind) =>
                mode(value.direction, value.transport_type, kind)
              }
            />
            <Choice
              label="Transport"
              value={value.transport_type}
              options={['FILE', 'HTTP_REST']}
              onChange={(t) =>
                mode(
                  value.direction,
                  t as DefinitionInput['transport_type'],
                  value.integration_type,
                )
              }
            />
            {http && !isInbound && (
              <>
                <Input
                  label="Endpoint URL"
                  value={value.endpoint_url ?? ''}
                  required
                  type="url"
                  maxLength={2000}
                  onChange={(endpoint_url) => change({ endpoint_url })}
                />
                <Choice
                  label="HTTP method"
                  value="POST"
                  options={['POST']}
                  onChange={() => {}}
                />
              </>
            )}
            <Choice
              label={isInbound ? 'Input format' : 'Output format'}
              value={value.output_format}
              options={http ? ['JSON'] : isInbound ? ['CSV'] : ['JSON', 'CSV']}
              onChange={(f) => change({ output_format: f as 'JSON' | 'CSV' })}
            />
            {(http || isInbound) && (
              <>
                <Choice
                  label="Authentication"
                  value={value.configuration.auth_type}
                  options={isInbound ? ['BEARER_ENV'] : ['NONE', 'BEARER_ENV']}
                  onChange={(a) =>
                    config({
                      auth_type: a as Config['auth_type'],
                      credential_env_key: null,
                    })
                  }
                />
                {value.configuration.auth_type === 'BEARER_ENV' && (
                  <Input
                    label="Credential environment key"
                    value={value.configuration.credential_env_key ?? ''}
                    required
                    maxLength={82}
                    onChange={(credential_env_key) =>
                      config({ credential_env_key })
                    }
                  />
                )}
              </>
            )}
            {value.integration_type === 'WORKER_EXPORT' && (
              <>
                <Input
                  label="As of date"
                  type="date"
                  value={value.configuration.as_of ?? ''}
                  onChange={(v) => config({ as_of: v || null })}
                />
                {(
                  [
                    'legal_employer_code',
                    'business_unit_code',
                    'department_code',
                  ] as const
                ).map((key) => (
                  <Input
                    key={key}
                    label={key.replaceAll('_', ' ')}
                    maxLength={30}
                    value={value.configuration[key] ?? ''}
                    onChange={(v) => config({ [key]: v || null })}
                  />
                ))}
                <label>
                  <input
                    type="checkbox"
                    checked={value.configuration.active_workers_only ?? true}
                    onChange={(e) =>
                      config({ active_workers_only: e.target.checked })
                    }
                  />{' '}
                  Active workers only
                </label>
              </>
            )}
            {value.integration_type === 'PAYROLL_EXPORT' && (
              <>
                <Input
                  label="Payroll definition code"
                  value={value.configuration.payroll_definition_code ?? ''}
                  onChange={(v) =>
                    config({ payroll_definition_code: v || null })
                  }
                  maxLength={30}
                />
                <Input
                  label="Period name"
                  value={value.configuration.period_name ?? ''}
                  onChange={(v) => config({ period_name: v || null })}
                  maxLength={100}
                />
                <Input
                  label="Completed run number"
                  value={String(value.configuration.completed_run_number ?? '')}
                  type="number"
                  onChange={(v) =>
                    config({ completed_run_number: v ? Number(v) : null })
                  }
                />
              </>
            )}
            {value.integration_type === 'FBP_EXPORT' && (
              <Input
                label="FBP plan code"
                value={value.configuration.fbp_plan_code ?? ''}
                onChange={(v) => config({ fbp_plan_code: v || null })}
                maxLength={30}
              />
            )}
          </div>
          <label>
            <input
              type="checkbox"
              checked={value.is_active}
              onChange={(e) => change({ is_active: e.target.checked })}
            />{' '}
            Active
          </label>
          <p className="hint">
            Enter an allowlisted INTEGRATION_TOKEN_ reference, never its secret
            value. Private HTTP destinations are blocked unless explicitly
            enabled for local QA.
          </p>
          <div className="flex gap-3">
            <button className="primary">
              {busy ? 'Saving…' : 'Save integration'}
            </button>
            <Link
              className="secondary"
              to={existing ? '/integrations/' + existing.id : '/integrations'}
            >
              Cancel
            </Link>
          </div>
        </fieldset>
      </form>
    </>
  )
}
function LoadedDefinition({
  api,
  children,
}: {
  api: IntegrationsClient
  children: (d: Definition) => ReactNode
}) {
  const { id = '' } = useParams()
  const loaded = useLoad(() => api.definition(id), [api, id])
  return loaded.data ? <>{children(loaded.data)}</> : <LoadState {...loaded} />
}
export function DefinitionDetail({
  api,
  definition: d,
}: {
  api: IntegrationsClient
  definition: Definition
}) {
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [confirmed, setConfirmed] = useState(false),
    [record, setRecord] = useState<Record<string, string>>({}),
    [csv, setCsv] = useState<string | null>(null)
  const [key] = useState(() => crypto.randomUUID())
  const templates = useLoad(
    () => (d.direction === 'INBOUND' ? api.templates() : Promise.resolve([])),
    [api, d.direction],
  )
  const template = templates.data?.find(
    (t) => t.object_type === d.integration_type,
  )
  async function execute(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const run = await api.run(d.id, {
        request_key: key,
        ...(d.direction === 'OUTBOUND'
          ? {}
          : d.transport_type === 'FILE'
            ? { csv_content: csv ?? '' }
            : { records: [record] }),
      })
      navigate('/integrations/runs/' + run.id)
    } catch (e) {
      setError(message(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <PageTitle
        title={d.name}
        description={`${d.code} · ${d.direction} · ${d.integration_type}`}
      >
        <Link className="secondary" to={'/integrations/' + d.id + '/edit'}>
          Edit integration
        </Link>
        <Link className="secondary" to="/integrations/history">
          Run history
        </Link>
      </PageTitle>
      <section className="panel">
        <Badge>{d.is_active ? 'Active' : 'Inactive'}</Badge>
        <p>{d.description}</p>
        <dl className="facts">
          {Object.entries({
            Transport: d.transport_type,
            Format: d.output_format,
            Endpoint:
              d.endpoint_url ??
              (d.direction === 'INBOUND'
                ? '/integrations/inbound/' + d.code
                : 'Local file'),
            Method: d.http_method ?? '—',
            'Credential reference':
              d.configuration.credential_env_key ?? 'None',
            Authentication: d.configuration.auth_type,
          }).map(([k, v]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
        <h2>Configuration</h2>
        <dl className="facts">
          {Object.entries(d.configuration)
            .filter(
              ([k, v]) =>
                v !== null && !['auth_type', 'credential_env_key'].includes(k),
            )
            .map(([k, v]) => (
              <div key={k}>
                <dt>{k.replaceAll('_', ' ')}</dt>
                <dd>{String(v)}</dd>
              </div>
            ))}
        </dl>
      </section>
      <form onSubmit={execute} className="panel mt-5 space-y-4">
        <h2>Run integration</h2>
        {error && <Notice error>{error}</Notice>}
        <LoadState {...templates} />
        <fieldset disabled={busy || !d.is_active} className="space-y-4">
          {d.direction === 'INBOUND' &&
            (d.transport_type === 'FILE' ? (
              <label className="field">
                CSV input
                <input
                  type="file"
                  accept=".csv,text/csv"
                  required
                  onChange={async (e) => {
                    setCsv(null)
                    setError('')
                    const file = e.target.files?.[0]
                    if (file) {
                      if (file.size > 1000000) {
                        setError('CSV must be at most 1 MB.')
                        return
                      }
                      try {
                        setCsv(await file.text())
                      } catch {
                        setError('Could not read CSV.')
                      }
                    }
                  }}
                />
                <span className="hint">
                  Columns: {template?.columns.join(', ')}. Use the Data Imports
                  template.
                </span>
              </label>
            ) : (
              <div className="grid gap-4 md:grid-cols-2">
                {template?.columns.map((column) => (
                  <Input
                    key={column}
                    label={column.replaceAll('_', ' ')}
                    value={record[column] ?? ''}
                    onChange={(v) => setRecord((r) => ({ ...r, [column]: v }))}
                    required={template.required.includes(column)}
                    maxLength={10000}
                  />
                ))}
              </div>
            ))}
          <p className="hint">
            {d.direction === 'INBOUND'
              ? 'Apply changes to existing synthetic workers through the same validation as Core HR.'
              : 'Export matching records. HTTP runs send one request per record to the configured destination.'}{' '}
            Runs process at most 100 records.
          </p>
          <label>
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
            />{' '}
            I confirm this local synthetic integration run.
          </label>
          <div>
            <button
              className="primary"
              disabled={
                !confirmed ||
                templates.busy ||
                (d.direction === 'INBOUND' &&
                  (!template || (d.transport_type === 'FILE' && csv === null)))
              }
            >
              {busy ? 'Running…' : 'Run Now'}
            </button>
          </div>
        </fieldset>
      </form>
    </>
  )
}
function History({ api }: { api: IntegrationsClient }) {
  const [offset, setOffset] = useState(0)
  const loaded = useLoad(() => api.runs(offset), [api, offset])
  return (
    <>
      <PageTitle title="Integration run history" />
      <LoadState {...loaded} />
      {loaded.data && (
        <section className="panel">
          <RunTable runs={loaded.data} />
          <Pages
            offset={offset}
            setOffset={setOffset}
            count={loaded.data.length}
          />
        </section>
      )}
    </>
  )
}
export function RunDetail({ api }: { api: IntegrationsClient }) {
  const { id = '' } = useParams(),
    navigate = useNavigate()
  const loaded = useLoad(
    async () => ({ run: await api.result(id), items: await api.items(id) }),
    [api, id],
  )
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [confirm, setConfirm] = useState(false),
    [key, setKey] = useState(() => crypto.randomUUID())
  const run = loaded.data?.run
  async function action(retry: boolean) {
    setBusy(true)
    setError('')
    try {
      if (retry) {
        const r = await api.retry(id, key)
        setKey(crypto.randomUUID())
        setConfirm(false)
        navigate('/integrations/runs/' + r.id)
      } else if (run) {
        saveBlob(
          await api.download(id),
          run.output_filename ?? 'integration.json',
        )
      }
    } catch (e) {
      setError(message(e))
    } finally {
      setBusy(false)
    }
  }
  if (!run) return <LoadState {...loaded} />
  return (
    <>
      <PageTitle
        title={run.definition_snapshot.name}
        description="Integration run detail"
      >
        <Link className="secondary" to="/integrations/history">
          Run history
        </Link>
      </PageTitle>
      {error && <Notice error>{error}</Notice>}
      <section className="panel space-y-4">
        <Badge>{run.status}</Badge>
        <p>
          {run.records_read} read · {run.records_succeeded} succeeded ·{' '}
          {run.records_failed} failed
        </p>
        <p>
          Started {date(run.started_at)} · Completed {date(run.completed_at)}
        </p>
        <p className="hint">
          Trigger: {run.trigger_type} · Requested by:{' '}
          {run.requested_by_user_id ?? 'Integration credential'} · Request key:{' '}
          {run.request_key}
        </p>
        {run.retry_of_run_id && (
          <p>
            Retry of{' '}
            <Link to={'/integrations/runs/' + run.retry_of_run_id}>
              {run.retry_of_run_id}
            </Link>
          </p>
        )}
        {run.safe_error_message && (
          <Notice error>{run.safe_error_message}</Notice>
        )}
        <h2>Safe request / response metadata</h2>
        <pre className="overflow-auto text-sm">
          {JSON.stringify(
            { request: run.request_metadata, response: run.response_metadata },
            null,
            2,
          )}
        </pre>
        {run.output_filename && run.status === 'COMPLETED' && (
          <button
            className="primary"
            disabled={busy}
            onClick={() => action(false)}
          >
            Download output
          </button>
        )}
        {['FAILED', 'COMPLETED_WITH_ERRORS'].includes(run.status) &&
          run.records_failed > 0 &&
          run.retry_depth < 3 && (
            <div className="space-y-3">
              <p className="hint">
                Retries create a new run containing failed items only. Delivery
                may already have reached a partner; verify their receipt before
                retrying.
              </p>
              <label>
                <input
                  type="checkbox"
                  checked={confirm}
                  onChange={(e) => setConfirm(e.target.checked)}
                />{' '}
                I have checked failed items and partner receipts.
              </label>
              <div>
                <button
                  className="primary"
                  disabled={busy || !confirm}
                  onClick={() => action(true)}
                >
                  Retry failed items
                </button>
              </div>
            </div>
          )}
      </section>
      <section className="panel mt-5">
        <h2>Item results</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Sequence</th>
                <th>Business reference</th>
                <th>Status</th>
                <th>HTTP status</th>
                <th>Error</th>
              </tr>
            </thead>
            <tbody>
              {loaded.data?.items.map((item) => (
                <tr key={item.id}>
                  <td>{item.sequence_number}</td>
                  <td>{item.business_reference}</td>
                  <td>{item.status}</td>
                  <td>{item.response_status ?? '—'}</td>
                  <td>{item.safe_error_message ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  )
}
export function IntegrationsRoutes({ api }: { api: IntegrationsClient }) {
  return (
    <Routes>
      <Route index element={<Dashboard api={api} />} />
      <Route path="new" element={<DefinitionForm api={api} />} />
      <Route path="history" element={<History api={api} />} />
      <Route path="runs/:id" element={<RunDetail api={api} />} />
      <Route
        path=":id/edit"
        element={
          <LoadedDefinition api={api}>
            {(d) => <DefinitionForm key={d.id} api={api} existing={d} />}
          </LoadedDefinition>
        }
      />
      <Route
        path=":id"
        element={
          <LoadedDefinition api={api}>
            {(d) => <DefinitionDetail key={d.id} api={api} definition={d} />}
          </LoadedDefinition>
        }
      />
    </Routes>
  )
}
