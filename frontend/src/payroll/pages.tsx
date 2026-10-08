import { useState } from 'react'
import type { FormEvent } from 'react'
import {
  Link,
  Navigate,
  Route,
  Routes,
  useNavigate,
  useParams,
} from 'react-router-dom'
import {
  Field,
  Select,
  PageTitle,
  LoadState,
  Notice,
  Badge,
  Facts,
} from '../components/ui'
import { useLoad } from '../components/useLoad'
import { salary, label } from '../core-hr/types'
import type { Reference } from '../core-hr/types'
import type { CoreHrClient } from '../core-hr/api'
import type {
  PayrollClient,
  Definition,
  Period,
  Run,
  Result,
  RunDetail,
  ResultDetail,
} from './api'
export function PayrollRoutes({
  api,
  hr,
  staff,
}: {
  api: PayrollClient
  hr: CoreHrClient
  staff: boolean
}) {
  return (
    <>
      <p className="mb-6 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
        Payroll simulation · Synthetic rules only. These calculations are not
        statutory payroll or tax advice.
      </p>
      <Routes>
        {staff ? (
          <>
            <Route index element={<PayrollDashboard api={api} />} />
            <Route
              path="definitions"
              element={<Definitions api={api} hr={hr} />}
            />
            <Route path="periods" element={<Periods api={api} />} />
            <Route path="runs/:id" element={<RunPage api={api} />} />
            <Route path="results/:id" element={<ResultPage api={api} />} />
          </>
        ) : (
          <>
            <Route path="me" element={<MyPayroll api={api} />} />
            <Route path="me/:id" element={<ResultPage api={api} self />} />
          </>
        )}
        <Route
          path="*"
          element={<Navigate to={staff ? '/payroll' : '/payroll/me'} replace />}
        />
      </Routes>
    </>
  )
}
function PayrollLinks() {
  return (
    <div className="actions mb-6">
      <Link className="secondary" to="/payroll">
        Overview
      </Link>
      <Link className="secondary" to="/payroll/definitions">
        Payroll definitions
      </Link>
      <Link className="secondary" to="/payroll/periods">
        Pay periods
      </Link>
    </div>
  )
}
function PeriodTable({
  periods,
  definitions,
}: {
  periods: Period[]
  definitions: Definition[]
}) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Period</th>
            <th>Payroll</th>
            <th>Dates</th>
            <th>Payment date</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {periods.map((p) => (
            <tr key={p.id}>
              <td>{p.period_name}</td>
              <td>
                {definitions.find((d) => d.id === p.payroll_definition_id)
                  ?.name ?? 'Not available'}
              </td>
              <td>
                {p.period_start} to {p.period_end}
              </td>
              <td>{p.payment_date}</td>
              <td>
                <Badge>{label(p.status)}</Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
function RunTable({ runs, periods }: { runs: Run[]; periods: Period[] }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Run</th>
            <th>Period</th>
            <th>Started</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.id}>
              <td>
                <Link className="link" to={'/payroll/runs/' + run.id}>
                  Run {run.run_number}
                </Link>
              </td>
              <td>
                {periods.find((p) => p.id === run.pay_period_id)?.period_name ??
                  'Not available'}
              </td>
              <td>{new Date(run.started_at).toLocaleString()}</td>
              <td>
                <Badge>{label(run.status)}</Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
export function PayrollDashboard({ api }: { api: PayrollClient }) {
  const load = useLoad(async () => {
    const [definitions, periods, runs] = await Promise.all([
      api.definitions(),
      api.periods(),
      api.runs(),
    ])
    return { definitions, periods, runs }
  }, [api])
  return (
    <>
      <PageTitle
        title="Payroll overview"
        description="Review monthly simulation periods and processing history."
      />
      <PayrollLinks />
      <LoadState {...load} />
      {load.data && (
        <div className="space-y-6">
          <div className="stats">
            {[
              ['Payroll definitions', load.data.definitions.length],
              [
                'Open periods',
                load.data.periods.filter((p) => p.status === 'OPEN').length,
              ],
              [
                'Completed runs',
                load.data.runs.filter((r) => r.status === 'COMPLETED').length,
              ],
            ].map(([name, value]) => (
              <div className="panel" key={name}>
                <p className="text-sm text-slate-500">{name}</p>
                <p className="text-3xl font-semibold mt-3">{value}</p>
              </div>
            ))}
          </div>
          <section className="panel">
            <h2>Latest periods</h2>
            {load.data.periods.length ? (
              <PeriodTable
                periods={load.data.periods.slice(0, 5)}
                definitions={load.data.definitions}
              />
            ) : (
              <Notice>No pay periods yet.</Notice>
            )}
          </section>
          <section className="panel">
            <h2>Latest runs</h2>
            {load.data.runs.length ? (
              <RunTable
                runs={load.data.runs.slice(0, 10)}
                periods={load.data.periods}
              />
            ) : (
              <Notice>No payroll runs yet.</Notice>
            )}
          </section>
        </div>
      )}
    </>
  )
}
export function Definitions({
  api,
  hr,
}: {
  api: PayrollClient
  hr: CoreHrClient
}) {
  const load = useLoad(
    async () => ({
      definitions: await api.definitions(),
      employers: await hr.all<Reference>('/reference/legal-employers'),
    }),
    [api, hr],
  )
  const [creating, setCreating] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('')
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError('')
    const data = Object.fromEntries(new FormData(event.currentTarget))
    try {
      await api.request('/definitions', data)
      setCreating(false)
      load.reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to create definition.')
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <PageTitle
        title="Payroll definitions"
        description="One monthly payroll per legal employer. Rules are fixed when created."
      />
      <PayrollLinks />
      <LoadState {...load} />
      {error && <Notice error>{error}</Notice>}
      {load.data && (
        <section className="panel space-y-5">
          <button
            className="primary"
            onClick={() => setCreating(true)}
            disabled={busy}
          >
            Create definition
          </button>
          {creating && (
            <form onSubmit={submit}>
              <fieldset disabled={busy} className="space-y-5">
                <div className="form-grid">
                  <Field label="Code" name="code" required maxLength={30} />
                  <Field label="Name" name="name" required maxLength={150} />
                  <Select
                    label="Legal employer"
                    name="legal_employer_id"
                    required
                    defaultValue=""
                  >
                    <option value="">Select employer</option>
                    {load.data.employers
                      .filter(
                        (e) =>
                          e.is_active &&
                          !load.data!.definitions.some(
                            (d) => d.legal_employer_id === e.id,
                          ),
                      )
                      .map((e) => (
                        <option key={e.id} value={e.id}>
                          {e.name}
                        </option>
                      ))}
                  </Select>
                  <Field
                    label="Country code"
                    name="country_code"
                    required
                    pattern="[A-Za-z]{2}"
                    maxLength={2}
                  />
                  <Field
                    label="Currency"
                    name="currency"
                    required
                    pattern="[A-Za-z]{3}"
                    maxLength={3}
                  />
                  <Field
                    label="Retirement contribution rate (0–1)"
                    name="retirement_rate"
                    value="0.05"
                    required
                    pattern="(0(\.[0-9]{1,4})?|1(\.0{1,4})?)"
                    inputMode="decimal"
                  />
                  <Field
                    label="Income tax withholding rate (0–1)"
                    name="withholding_rate"
                    value="0.10"
                    required
                    pattern="(0(\.[0-9]{1,4})?|1(\.0{1,4})?)"
                    inputMode="decimal"
                  />
                  <Field
                    label="Monthly standard allowance"
                    name="standard_allowance"
                    value="0.00"
                    required
                    pattern="[0-9]{1,12}(\.[0-9]{1,2})?"
                    inputMode="decimal"
                  />
                </div>
                <p className="hint">
                  Monthly base = annual salary / 12. Rates are fractions: 0.05
                  means 5%. Retirement uses base pay; withholding uses gross
                  pay. Both earnings use calendar-day proration.
                </p>
                <div className="actions">
                  <button className="primary">
                    {busy ? 'Saving…' : 'Save definition'}
                  </button>
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => setCreating(false)}
                  >
                    Cancel
                  </button>
                </div>
              </fieldset>
            </form>
          )}
          {load.data.definitions.length ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Payroll</th>
                    <th>Legal employer</th>
                    <th>Currency</th>
                    <th>Illustrative rates</th>
                    <th>Allowance</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {load.data.definitions.map((d) => (
                    <tr key={d.id}>
                      <td>
                        {d.name}
                        <p className="hint">{d.code} · Monthly</p>
                      </td>
                      <td>
                        {
                          load.data!.employers.find(
                            (e) => e.id === d.legal_employer_id,
                          )?.name
                        }
                      </td>
                      <td>{d.currency}</td>
                      <td>
                        Retirement {d.retirement_rate}
                        <br />
                        Withholding {d.withholding_rate}
                      </td>
                      <td>{salary(d.standard_allowance, d.currency)}</td>
                      <td>
                        <Badge>{d.is_active ? 'Active' : 'Inactive'}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Notice>No payroll definitions yet.</Notice>
          )}
        </section>
      )}
    </>
  )
}
export function Periods({ api }: { api: PayrollClient }) {
  const load = useLoad(async () => {
    const [definitions, periods, runs] = await Promise.all([
      api.definitions(),
      api.periods(),
      api.runs(),
    ])
    return { definitions, periods, runs }
  }, [api])
  const [creating, setCreating] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [selected, setSelected] = useState<Period | null>(null)
  const navigate = useNavigate()
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError('')
    const data = Object.fromEntries(new FormData(event.currentTarget))
    try {
      await api.request('/periods', data)
      setCreating(false)
      load.reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to create period.')
    } finally {
      setBusy(false)
    }
  }
  async function process(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selected) return
    setBusy(true)
    setError('')
    try {
      const run = await api.process(selected.id)
      navigate('/payroll/runs/' + run.id)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to process payroll.')
      setSelected(null)
      load.reload()
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <PageTitle
        title="Pay periods"
        description="Create full calendar-month periods and process each once successfully."
      />
      <PayrollLinks />
      <LoadState {...load} />
      {error && <Notice error>{error}</Notice>}
      {load.data && (
        <section className="panel space-y-5">
          <button
            className="primary"
            disabled={busy}
            onClick={() => {
              setCreating(true)
              setSelected(null)
            }}
          >
            Create period
          </button>
          {creating && (
            <form onSubmit={submit}>
              <fieldset disabled={busy} className="space-y-5">
                <div className="form-grid">
                  <Select
                    label="Payroll definition"
                    name="payroll_definition_id"
                    required
                    defaultValue=""
                  >
                    <option value="">Select payroll</option>
                    {load.data.definitions
                      .filter((d) => d.is_active)
                      .map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.name}
                        </option>
                      ))}
                  </Select>
                  <Field
                    label="Period name"
                    name="period_name"
                    required
                    maxLength={100}
                  />
                  <Field
                    label="Period start"
                    name="period_start"
                    type="date"
                    required
                  />
                  <Field
                    label="Period end"
                    name="period_end"
                    type="date"
                    required
                  />
                  <Field
                    label="Payment date"
                    name="payment_date"
                    type="date"
                    required
                  />
                </div>
                <p className="hint">
                  Use the first and last day of the same month. Payment date
                  must be on or after period end. Overlapping periods are
                  rejected.
                </p>
                <div className="actions">
                  <button className="primary">
                    {busy ? 'Saving…' : 'Save period'}
                  </button>
                  <button
                    className="secondary"
                    type="button"
                    onClick={() => setCreating(false)}
                  >
                    Cancel
                  </button>
                </div>
              </fieldset>
            </form>
          )}
          {selected && (
            <form
              className="rounded-xl border border-amber-200 p-5"
              onSubmit={process}
            >
              <fieldset disabled={busy}>
                <h2>Process {selected.period_name}</h2>
                <p className="text-sm mb-4">
                  This snapshots eligible assignments and their compensation
                  using the configured illustrative rules. Completed results
                  cannot be recalculated. Failed attempts save no partial
                  results and can be retried.
                </p>
                <label className="flex gap-3 text-sm mb-4">
                  <input type="checkbox" required />I confirm processing this
                  payroll simulation.
                </label>
                <div className="actions">
                  <button className="primary">
                    {busy ? 'Processing…' : 'Confirm processing'}
                  </button>
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => setSelected(null)}
                  >
                    Cancel
                  </button>
                </div>
              </fieldset>
            </form>
          )}
          {load.data.periods.length ? (
            <>
              <PeriodTable
                periods={load.data.periods}
                definitions={load.data.definitions}
              />
              <div className="flex flex-wrap gap-3">
                {load.data.periods
                  .filter((p) => p.status === 'OPEN')
                  .map((p) => (
                    <button
                      key={p.id}
                      className="secondary"
                      disabled={busy}
                      onClick={() => {
                        setSelected(p)
                        setCreating(false)
                      }}
                    >
                      Process {p.period_name} ·{' '}
                      {
                        load.data!.definitions.find(
                          (d) => d.id === p.payroll_definition_id,
                        )?.code
                      }
                    </button>
                  ))}
              </div>
            </>
          ) : (
            <Notice>No pay periods yet.</Notice>
          )}
          {load.data.runs.length > 0 && (
            <>
              <h2>Processing history</h2>
              <RunTable runs={load.data.runs} periods={load.data.periods} />
            </>
          )}
        </section>
      )}
    </>
  )
}
function ResultsTable({
  results,
  self = false,
}: {
  results: Result[]
  self?: boolean
}) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>{self ? 'Assignment' : 'Worker'}</th>
            <th>Paid days</th>
            <th>Gross pay</th>
            <th>Deductions</th>
            <th>Net pay</th>
            <th>Details</th>
          </tr>
        </thead>
        <tbody>
          {results.map((r) => (
            <tr key={r.id}>
              <td>
                {self ? r.assignment_number : r.worker_name}
                <p className="hint">
                  {!self && `${r.person_number} · ${r.assignment_number}`}
                </p>
              </td>
              <td>
                {r.eligible_days} / {r.period_days}
              </td>
              <td>{salary(r.gross_pay, r.currency)}</td>
              <td>{salary(r.total_deductions, r.currency)}</td>
              <td className="font-semibold">{salary(r.net_pay, r.currency)}</td>
              <td>
                <Link
                  className="link"
                  to={`/payroll/${self ? 'me' : 'results'}/${r.id}`}
                >
                  View result
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
export function RunPage({ api }: { api: PayrollClient }) {
  const { id } = useParams()
  const load = useLoad(
    async () => ({
      detail: await api.request<RunDetail>('/runs/' + id),
      results: await api.all<Result>('/runs/' + id + '/results'),
    }),
    [api, id],
  )
  return (
    <>
      <PageTitle
        title="Payroll run"
        description="Saved processing status and calculated totals."
      />
      <PayrollLinks />
      <LoadState {...load} />
      {load.data && (
        <div className="space-y-6">
          <section className="panel">
            <h2>
              {load.data.detail.definition_name} ·{' '}
              {load.data.detail.period.period_name} · Run{' '}
              {load.data.detail.run.run_number}
            </h2>
            <Badge>{label(load.data.detail.run.status)}</Badge>
            {load.data.detail.run.failure_reason && (
              <Notice error>
                {load.data.detail.run.failure_reason} The period remains open
                for a corrected retry.
              </Notice>
            )}
            <Facts
              items={[
                [
                  'Started',
                  new Date(load.data.detail.run.started_at).toLocaleString(),
                ],
                [
                  'Completed',
                  load.data.detail.run.completed_at
                    ? new Date(
                        load.data.detail.run.completed_at,
                      ).toLocaleString()
                    : 'In progress',
                ],
                ['Results', String(load.data.detail.result_count)],
                [
                  'Gross pay',
                  salary(load.data.detail.gross_pay, load.data.detail.currency),
                ],
                [
                  'Deductions',
                  salary(
                    load.data.detail.total_deductions,
                    load.data.detail.currency,
                  ),
                ],
                [
                  'Net pay',
                  salary(load.data.detail.net_pay, load.data.detail.currency),
                ],
                [
                  'Excluded assignments',
                  String(load.data.detail.run.excluded_assignment_count),
                ],
                [
                  'Unpaid employment days',
                  String(load.data.detail.run.unpaid_day_count),
                ],
              ]}
            />
            <p className="hint">
              Only active or on-leave assignment days with compensation are
              paid. Suspended days and gaps in assignment/compensation history
              are unpaid. Excluded counts cover overlapping candidate
              assignments only.
            </p>
            <h2 className="mt-5">Applied calculation rules</h2>
            <Facts
              items={Object.entries(load.data.detail.run.rules_snapshot).map(
                ([key, value]) => [
                  label(key),
                  Array.isArray(value) ? value.join(', ') : String(value),
                ],
              )}
            />
          </section>
          <section className="panel">
            <h2>Worker results</h2>
            {load.data.results.length ? (
              <ResultsTable results={load.data.results} />
            ) : (
              <Notice>No results saved for this run.</Notice>
            )}
          </section>
        </div>
      )}
    </>
  )
}
export function ResultPage({
  api,
  self = false,
}: {
  api: PayrollClient
  self?: boolean
}) {
  const { id } = useParams()
  const load = useLoad(
    () => api.request<ResultDetail>(`/${self ? 'me' : 'results'}/${id}`),
    [api, id, self],
  )
  return (
    <>
      <PageTitle
        title={self ? 'My payroll result' : 'Payroll result'}
        description="Saved earnings, deductions and net pay."
      />
      <Link className="link" to={self ? '/payroll/me' : '/payroll'}>
        Back to payroll
      </Link>
      <LoadState {...load} />
      {load.data && (
        <div className="space-y-6 mt-5">
          <section className="panel">
            <h2>
              {load.data.result.worker_name} · {load.data.period.period_name}
            </h2>
            <Facts
              items={[
                ['Person number', load.data.result.person_number],
                ['Assignment', load.data.result.assignment_number],
                ['Payroll', load.data.definition_name],
                [
                  'Period',
                  `${load.data.period.period_start} to ${load.data.period.period_end}`,
                ],
                ['Payment date', load.data.period.payment_date],
                [
                  'Paid days',
                  `${load.data.result.eligible_days} of ${load.data.result.period_days}`,
                ],
              ]}
            />
          </section>
          {(['EARNING', 'DEDUCTION'] as const).map((type) => (
            <section className="panel" key={type}>
              <h2>{type === 'EARNING' ? 'Earnings' : 'Deductions'}</h2>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Line</th>
                      <th>Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {load
                      .data!.lines.filter((l) => l.line_type === type)
                      .map((line) => (
                        <tr key={line.id}>
                          <td>{line.name}</td>
                          <td>
                            {salary(line.amount, load.data!.result.currency)}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </section>
          ))}
          <section className="panel">
            <Facts
              items={[
                [
                  'Gross pay',
                  salary(load.data.result.gross_pay, load.data.result.currency),
                ],
                [
                  'Total deductions',
                  salary(
                    load.data.result.total_deductions,
                    load.data.result.currency,
                  ),
                ],
                [
                  'Net pay',
                  salary(load.data.result.net_pay, load.data.result.currency),
                ],
              ]}
            />
          </section>
          <section className="panel">
            <h2>Proration details</h2>
            <p className="hint">
              Monthly salary is annual base salary / 12. Each paid calendar day
              contributes 1 / total period days. Earnings and each deduction are
              rounded once to two decimal places using half-up rounding.
            </p>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>From</th>
                    <th>To</th>
                    <th>Paid days</th>
                    <th>Annual base salary</th>
                    <th>Assignment status</th>
                  </tr>
                </thead>
                <tbody>
                  {load.data.result.calculation_snapshot.map(
                    (segment, index) => (
                      <tr key={index}>
                        <td>{segment.from}</td>
                        <td>{segment.to}</td>
                        <td>{segment.days}</td>
                        <td>
                          {salary(segment.annual_base_salary, segment.currency)}
                        </td>
                        <td>{label(segment.status)}</td>
                      </tr>
                    ),
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      )}
    </>
  )
}
export function MyPayroll({ api }: { api: PayrollClient }) {
  const load = useLoad(() => api.all<ResultDetail>('/me'), [api])
  return (
    <>
      <PageTitle
        title="My payroll"
        description="Your saved payroll simulation history."
      />
      <LoadState {...load} />
      {load.data &&
        (load.data.length ? (
          <div className="space-y-5">
            {load.data.map((detail) => (
              <section className="panel" key={detail.result.id}>
                <h2>
                  {detail.period.period_name} · {detail.definition_name}
                </h2>
                <p className="hint">
                  {detail.period.period_start} to {detail.period.period_end} ·
                  Payment {detail.period.payment_date}
                </p>
                <ResultsTable self results={[detail.result]} />
              </section>
            ))}
          </div>
        ) : (
          <Notice>
            No payroll results are available for your linked person.
          </Notice>
        ))}
    </>
  )
}
