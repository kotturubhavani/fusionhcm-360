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
import { cents, decimal } from './api'
import type {
  FbpClient,
  Plan,
  Component,
  Budget,
  Summary,
  PlanView,
} from './api'
export function FbpRoutes({
  api,
  hr,
  staff,
}: {
  api: FbpClient
  hr: CoreHrClient
  staff: boolean
}) {
  return (
    <>
      <p className="mb-6 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
        Benefits planning simulation · Synthetic allocations only; no statutory,
        tax or payroll treatment.
      </p>
      <Routes>
        {staff ? (
          <>
            <Route index element={<PlansPage api={api} hr={hr} />} />
            <Route path="plans/:id" element={<PlanPage api={api} />} />
          </>
        ) : (
          <>
            <Route path="me" element={<MyBenefits api={api} />} />
            <Route path="me/:id" element={<MyPlan api={api} />} />
          </>
        )}
        <Route
          path="*"
          element={<Navigate to={staff ? '/fbp' : '/fbp/me'} replace />}
        />
      </Routes>
    </>
  )
}
export function PlansPage({ api, hr }: { api: FbpClient; hr: CoreHrClient }) {
  const load = useLoad(async () => {
    const [plans, employers] = await Promise.all([
      api.all<Plan>('/plans'),
      hr.all<Reference>('/reference/legal-employers'),
    ])
    const summaries = await Promise.all(
      plans.map((p) => api.request<Summary>(`/plans/${p.id}/summary`)),
    )
    return { plans, employers, summaries }
  }, [api, hr])
  const [defaultYear] = useState(() => String(new Date().getFullYear()))
  const [creating, setCreating] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('')
  const navigate = useNavigate()
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError('')
    const data = Object.fromEntries(new FormData(event.currentTarget))
    const year = Number(data.plan_year)
    try {
      const plan = await api.request<Plan>('/plans', 'POST', {
        ...data,
        plan_year: year,
        effective_from: `${year}-01-01`,
        effective_to: `${year}-12-31`,
      })
      navigate('/fbp/plans/' + plan.id)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to create plan.')
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <PageTitle
        title="Flexible benefits"
        description="Annual plans and worker allocation progress."
      />
      <LoadState {...load} />
      {error && <Notice error>{error}</Notice>}
      {load.data && (
        <section className="panel space-y-5">
          <button
            className="primary"
            disabled={busy}
            onClick={() => setCreating(true)}
          >
            Create plan
          </button>
          {creating && (
            <form onSubmit={submit}>
              <fieldset disabled={busy} className="space-y-5">
                <div className="form-grid">
                  <Field label="Code" name="code" required maxLength={30} />
                  <Field
                    label="Plan name"
                    name="name"
                    required
                    maxLength={150}
                  />
                  <Select
                    label="Legal employer"
                    name="legal_employer_id"
                    required
                    defaultValue=""
                  >
                    <option value="">Select employer</option>
                    {load.data.employers
                      .filter((e) => e.is_active)
                      .map((e) => (
                        <option key={e.id} value={e.id}>
                          {e.name}
                        </option>
                      ))}
                  </Select>
                  <Field
                    label="Plan year"
                    name="plan_year"
                    type="number"
                    min={1900}
                    max={9998}
                    required
                    value={defaultYear}
                  />
                  <Field
                    label="Currency"
                    name="currency"
                    required
                    maxLength={3}
                    pattern="[A-Za-z]{3}"
                  />
                  <Field
                    label="Salary share (0–1)"
                    name="budget_rate"
                    required
                    value="0.10"
                    inputMode="decimal"
                    pattern="(0\.[0-9]{1,4}|1(\.0{1,4})?)"
                  />
                </div>
                <p className="hint">
                  Plans cover January 1 to December 31. Budget = annual base
                  salary at January 1 × salary share. 0.10 means 10%; salary is
                  not treated as CTC.
                </p>
                <div className="actions">
                  <button className="primary">
                    {busy ? 'Saving…' : 'Save plan'}
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
          {load.data.plans.length ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Plan</th>
                    <th>Employer</th>
                    <th>Status</th>
                    <th>Workers / budgets</th>
                    <th>Allocation progress</th>
                  </tr>
                </thead>
                <tbody>
                  {load.data.plans.map((p, index) => (
                    <tr key={p.id}>
                      <td>
                        <Link
                          className="link font-semibold"
                          to={'/fbp/plans/' + p.id}
                        >
                          {p.name}
                        </Link>
                        <p className="hint">
                          {p.plan_year} · {p.code}
                        </p>
                      </td>
                      <td>
                        {load.data!.employers.find(
                          (e) => e.id === p.legal_employer_id,
                        )?.name ?? 'Not available'}
                      </td>
                      <td>
                        <Badge>{label(p.status)}</Badge>
                      </td>
                      <td>
                        {load.data!.summaries[index].workers} /{' '}
                        {load.data!.summaries[index].budgets}
                      </td>
                      <td>
                        {load.data!.summaries[index].open} open ·{' '}
                        {load.data!.summaries[index].submitted} submitted ·{' '}
                        {load.data!.summaries[index].finalized} finalized
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Notice>No benefit plans yet.</Notice>
          )}
        </section>
      )}
    </>
  )
}
export function ComponentForm({
  api,
  planId,
  initial,
  onDone,
  onCancel,
}: {
  api: FbpClient
  planId: string
  initial?: Component
  onDone: () => void
  onCancel: () => void
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('')
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError('')
    const form = new FormData(event.currentTarget)
    const data = Object.fromEntries(form)
    try {
      await api.request(
        initial ? '/components/' + initial.id : `/plans/${planId}/components`,
        initial ? 'PATCH' : 'POST',
        {
          ...data,
          description: data.description || null,
          display_order: Number(data.display_order),
          is_active: form.get('is_active') === 'on',
        },
      )
      onDone()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to save component.')
    } finally {
      setBusy(false)
    }
  }
  return (
    <form className="rounded-xl border border-teal-200 p-5" onSubmit={submit}>
      <h2>{initial ? 'Edit component' : 'Add component'}</h2>
      <fieldset disabled={busy} className="space-y-5">
        <div className="form-grid">
          <Field
            label="Component code"
            name="code"
            required
            value={initial?.code}
            maxLength={30}
          />
          <Field
            label="Component name"
            name="name"
            required
            value={initial?.name}
            maxLength={150}
          />
          <Select
            label="Component type"
            name="component_type"
            defaultValue={initial?.component_type ?? 'BENEFIT'}
          >
            {['ALLOWANCE', 'BENEFIT', 'REIMBURSEMENT'].map((v) => (
              <option key={v} value={v}>
                {label(v)}
              </option>
            ))}
          </Select>
          <Field
            label="Description"
            name="description"
            value={initial?.description ?? ''}
            maxLength={2000}
          />
          <Field
            label="Minimum amount"
            name="min_amount"
            required
            value={initial?.min_amount ?? '0.00'}
            pattern="[0-9]{1,12}(\.[0-9]{1,2})?"
            inputMode="decimal"
          />
          <Field
            label="Maximum amount"
            name="max_amount"
            required
            value={initial?.max_amount ?? '999999999999.99'}
            pattern="[0-9]{1,12}(\.[0-9]{1,2})?"
            inputMode="decimal"
          />
          <Field
            label="Suggested amount"
            name="default_amount"
            required
            value={initial?.default_amount ?? '0.00'}
            pattern="[0-9]{1,12}(\.[0-9]{1,2})?"
            inputMode="decimal"
          />
          <Field
            label="Display order"
            name="display_order"
            type="number"
            min={0}
            max={10000}
            required
            value={String(initial?.display_order ?? 0)}
          />
        </div>
        <label className="flex gap-2 text-sm">
          <input
            name="is_active"
            type="checkbox"
            defaultChecked={initial?.is_active ?? true}
          />
          Active
        </label>
        <p className="hint">
          Zero means not selected. Positive allocations must meet the minimum.
          Include a zero-minimum flexible component large enough to cover each
          full budget.
        </p>
        {error && <Notice error>{error}</Notice>}
        <div className="actions">
          <button className="primary">
            {busy ? 'Saving…' : 'Save component'}
          </button>
          <button type="button" className="secondary" onClick={onCancel}>
            Cancel
          </button>
        </div>
      </fieldset>
    </form>
  )
}
export function PlanPage({ api }: { api: FbpClient }) {
  const { id } = useParams()
  const load = useLoad(async () => {
    const [plan, components, workers, summary] = await Promise.all([
      api.request<Plan>('/plans/' + id),
      api.request<Component[]>(`/plans/${id}/components`),
      api.all<Budget>(`/plans/${id}/workers`),
      api.request<Summary>(`/plans/${id}/summary`),
    ])
    return { plan, components, workers, summary }
  }, [api, id])
  const [editing, setEditing] = useState<Component | 'new' | null>(null),
    [editPlan, setEditPlan] = useState(false),
    [action, setAction] = useState(''),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [notice, setNotice] = useState('')
  async function transition(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await api.request(`/plans/${id}/${action}`, 'POST')
      setNotice(
        action === 'generate-budgets'
          ? 'Worker budgets generated.'
          : 'Plan updated.',
      )
      setAction('')
      load.reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to update plan.')
    } finally {
      setBusy(false)
    }
  }
  async function patch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError('')
    const data = new FormData(event.currentTarget)
    try {
      await api.request('/plans/' + id, 'PATCH', {
        name: String(data.get('name')),
        budget_rate: String(data.get('budget_rate')),
        is_active: data.get('is_active') === 'on',
      })
      setEditPlan(false)
      load.reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to update plan.')
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <PageTitle
        title={load.data?.plan.name ?? 'Benefit plan'}
        description="Plan settings, components and worker allocations."
      />
      <Link className="link" to="/fbp">
        Back to plans
      </Link>
      <LoadState {...load} />
      {error && <Notice error>{error}</Notice>}
      {notice && <Notice>{notice}</Notice>}
      {load.data && (
        <div className="space-y-6 mt-5">
          <section className="panel">
            <div className="flex justify-between gap-3 mb-5">
              <h2>{load.data.plan.code}</h2>
              <Badge>{label(load.data.plan.status)}</Badge>
            </div>
            <Facts
              items={[
                ['Plan year', String(load.data.plan.plan_year)],
                [
                  'Dates',
                  `${load.data.plan.effective_from} to ${load.data.plan.effective_to}`,
                ],
                ['Currency', load.data.plan.currency],
                ['Salary share', load.data.plan.budget_rate],
                ['Active', load.data.plan.is_active ? 'Yes' : 'No'],
                [
                  'Budget snapshot',
                  load.data.plan.budgets_generated_at
                    ? new Date(
                        load.data.plan.budgets_generated_at,
                      ).toLocaleString()
                    : 'Not generated',
                ],
              ]}
            />
            <div className="actions mt-5">
              {load.data.plan.status === 'DRAFT' && (
                <>
                  <button
                    className="secondary"
                    onClick={() => setEditPlan(true)}
                  >
                    Edit draft plan
                  </button>
                  <button className="primary" onClick={() => setAction('open')}>
                    Open plan
                  </button>
                </>
              )}
              {load.data.plan.status === 'OPEN' && (
                <>
                  <button
                    className="primary"
                    disabled={busy || !!load.data.plan.budgets_generated_at}
                    onClick={() => setAction('generate-budgets')}
                  >
                    Generate budgets
                  </button>
                  <button
                    className="secondary"
                    disabled={
                      busy ||
                      load.data.summary.budgets === 0 ||
                      load.data.summary.submitted !== load.data.summary.budgets
                    }
                    onClick={() => setAction('close')}
                  >
                    Close and finalize
                  </button>
                </>
              )}
            </div>
            <p className="hint">
              Opening freezes configuration. Generation snapshots all eligible
              assignments once. Closing requires every budget to be submitted
              and makes allocations permanently read-only.
            </p>
            {editPlan && (
              <form onSubmit={patch}>
                <fieldset disabled={busy} className="space-y-4">
                  <Field
                    label="Plan name"
                    name="name"
                    required
                    maxLength={150}
                    value={load.data.plan.name}
                  />
                  <Field
                    label="Salary share"
                    name="budget_rate"
                    required
                    value={load.data.plan.budget_rate}
                  />
                  <label className="flex gap-2">
                    <input
                      name="is_active"
                      type="checkbox"
                      defaultChecked={load.data.plan.is_active}
                    />
                    Active
                  </label>
                  <div className="actions">
                    <button className="primary">Save draft plan</button>
                    <button
                      className="secondary"
                      type="button"
                      onClick={() => setEditPlan(false)}
                    >
                      Cancel
                    </button>
                  </div>
                </fieldset>
              </form>
            )}
            {action && (
              <form
                className="mt-5 rounded-lg border border-amber-200 p-4"
                onSubmit={transition}
              >
                <fieldset disabled={busy}>
                  <label className="flex items-start gap-3 text-sm mb-4">
                    <input type="checkbox" required />I confirm:{' '}
                    {action === 'open'
                      ? 'open this plan and freeze its settings'
                      : action === 'close'
                        ? 'close this plan and finalize all submitted allocations'
                        : 'generate budgets from eligible assignments and salary at the plan start date'}
                    .
                  </label>
                  <div className="actions">
                    <button className="primary">
                      {busy ? 'Working…' : 'Confirm action'}
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => setAction('')}
                    >
                      Cancel
                    </button>
                  </div>
                </fieldset>
              </form>
            )}
          </section>
          <section className="panel">
            <div className="flex justify-between gap-3">
              <h2>Components</h2>
              {load.data.plan.status === 'DRAFT' && (
                <button className="secondary" onClick={() => setEditing('new')}>
                  Add component
                </button>
              )}
            </div>
            {editing && (
              <ComponentForm
                api={api}
                planId={id!}
                initial={editing === 'new' ? undefined : editing}
                key={editing === 'new' ? 'new' : editing.id}
                onDone={() => {
                  setEditing(null)
                  load.reload()
                }}
                onCancel={() => setEditing(null)}
              />
            )}
            <div className="table-wrap mt-4">
              <table>
                <thead>
                  <tr>
                    <th>Component</th>
                    <th>Type</th>
                    <th>Minimum / maximum</th>
                    <th>Suggested</th>
                    <th>Status</th>
                    {load.data.plan.status === 'DRAFT' && <th>Action</th>}
                  </tr>
                </thead>
                <tbody>
                  {load.data.components.map((c) => (
                    <tr key={c.id}>
                      <td>
                        {c.name}
                        <p className="hint">
                          {c.code} · {c.description}
                        </p>
                      </td>
                      <td>{label(c.component_type)}</td>
                      <td>
                        {salary(c.min_amount, load.data!.plan.currency)} /{' '}
                        {salary(c.max_amount, load.data!.plan.currency)}
                      </td>
                      <td>
                        {salary(c.default_amount, load.data!.plan.currency)}
                      </td>
                      <td>
                        <Badge>{c.is_active ? 'Active' : 'Inactive'}</Badge>
                      </td>
                      {load.data!.plan.status === 'DRAFT' && (
                        <td>
                          <button
                            className="link"
                            onClick={() => setEditing(c)}
                          >
                            Edit {c.name}
                          </button>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!load.data.components.length && (
              <Notice>No components yet.</Notice>
            )}
          </section>
          <section className="panel">
            <h2>Worker allocations</h2>
            <Facts
              items={[
                ['Budgets', String(load.data.summary.budgets)],
                [
                  'Open / submitted / finalized',
                  `${load.data.summary.open} / ${load.data.summary.submitted} / ${load.data.summary.finalized}`,
                ],
                [
                  'Total budget',
                  salary(
                    load.data.summary.eligible_budget,
                    load.data.plan.currency,
                  ),
                ],
                [
                  'Allocated',
                  salary(load.data.summary.allocated, load.data.plan.currency),
                ],
                [
                  'Remaining',
                  salary(load.data.summary.remaining, load.data.plan.currency),
                ],
              ]}
            />
            {load.data.workers.length ? (
              <div className="table-wrap mt-5">
                <table>
                  <thead>
                    <tr>
                      <th>Worker</th>
                      <th>Assignment</th>
                      <th>Budget</th>
                      <th>Allocated</th>
                      <th>Remaining</th>
                      <th>Status / elections</th>
                    </tr>
                  </thead>
                  <tbody>
                    {load.data.workers.map((w) => (
                      <tr key={w.id}>
                        <td>
                          {w.worker_name}
                          <p className="hint">{w.person_number}</p>
                        </td>
                        <td>{w.assignment_number}</td>
                        <td>{salary(w.eligible_budget, w.currency)}</td>
                        <td>{salary(w.allocated, w.currency)}</td>
                        <td>{salary(w.remaining, w.currency)}</td>
                        <td>
                          <Badge>{label(w.status)}</Badge>
                          <details className="mt-2">
                            <summary className="link cursor-pointer">
                              View allocations
                            </summary>
                            {w.elections.map((e) => (
                              <p className="text-xs mt-2" key={e.component_id}>
                                {
                                  load.data!.components.find(
                                    (c) => c.id === e.component_id,
                                  )?.name
                                }
                                : {salary(e.amount, w.currency)}
                              </p>
                            ))}
                          </details>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Notice>No worker budgets have been generated.</Notice>
            )}
          </section>
        </div>
      )}
    </>
  )
}
export function MyBenefits({ api }: { api: FbpClient }) {
  const load = useLoad(() => api.all<PlanView>('/me'), [api])
  return (
    <>
      <PageTitle
        title="My benefits"
        description="Your eligible annual plans and saved allocations."
      />
      <LoadState {...load} />
      {load.data &&
        (load.data.length ? (
          <div className="space-y-5">
            {load.data.map((v) => (
              <section className="panel" key={v.plan.id}>
                <div className="flex justify-between gap-3">
                  <h2>
                    <Link className="link" to={'/fbp/me/' + v.plan.id}>
                      {v.plan.name}
                    </Link>
                  </h2>
                  <Badge>{label(v.plan.status)}</Badge>
                </div>
                <p className="hint">
                  {v.plan.effective_from} to {v.plan.effective_to} ·{' '}
                  {v.plan.currency}
                </p>
                {v.budgets.map((b) => (
                  <p className="text-sm mt-2" key={b.id}>
                    {b.assignment_number} ·{' '}
                    {salary(b.eligible_budget, b.currency)} budget ·{' '}
                    {label(b.status)}
                  </p>
                ))}
              </section>
            ))}
          </div>
        ) : (
          <Notice>No eligible benefit plan is linked to you.</Notice>
        ))}
    </>
  )
}
export function ElectionEditor({
  api,
  view,
  budget,
  onDone,
}: {
  api: FbpClient
  view: PlanView
  budget: Budget
  onDone: () => void
}) {
  const [amounts, setAmounts] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      view.components.map((c) => [
        c.id,
        budget.elections.find((e) => e.component_id === c.id)?.amount ?? '0.00',
      ]),
    ),
  )
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [dirty, setDirty] = useState(false),
    [confirm, setConfirm] = useState(false)
  const editable =
    view.plan.status === 'OPEN' &&
    view.plan.is_active &&
    budget.status === 'OPEN'
  const parsed = Object.values(amounts).map(cents)
  const valid = parsed.every((v) => v !== null)
  const allocated = parsed.reduce<bigint>((sum, v) => sum + (v ?? 0n), 0n)
  const remaining = (cents(budget.eligible_budget) ?? 0n) - allocated
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await api.request(`/me/${view.plan.id}/elections`, 'POST', {
        worker_budget_id: budget.id,
        expected_revision: budget.revision,
        elections: view.components.map((c) => ({
          component_id: c.id,
          amount: amounts[c.id],
        })),
      })
      onDone()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to save elections.')
    } finally {
      setBusy(false)
    }
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await api.request(`/me/${view.plan.id}/submit`, 'POST', {
        worker_budget_id: budget.id,
        expected_revision: budget.revision,
      })
      onDone()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to submit elections.')
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="panel">
      <div className="flex justify-between gap-3">
        <h2>Assignment · {budget.assignment_number}</h2>
        <Badge>{label(budget.status)}</Badge>
      </div>
      <Facts
        items={[
          [
            'Annual base salary snapshot',
            salary(budget.annual_base_salary, budget.currency),
          ],
          ['Salary share', budget.budget_rate],
          [
            'Annual benefit budget',
            salary(budget.eligible_budget, budget.currency),
          ],
        ]}
      />
      <p className="hint">
        Salary is not CTC. Zero leaves a component unselected. Save a draft
        before submitting; submission requires exact allocation and makes your
        choices read-only.
      </p>
      {!editable && <Notice>This allocation is read-only.</Notice>}
      <form onSubmit={save}>
        <fieldset disabled={busy || !editable}>
          <div className="space-y-4">
            {view.components.map((c) => (
              <div
                key={c.id}
                className="grid gap-3 rounded-lg border border-slate-200 p-4 sm:grid-cols-2"
              >
                <div>
                  <h3 className="text-sm font-semibold">{c.name}</h3>
                  <p className="hint">{c.description}</p>
                  <p className="hint">
                    {label(c.component_type)} · Positive amount:{' '}
                    {salary(c.min_amount, budget.currency)} to{' '}
                    {salary(c.max_amount, budget.currency)} · Suggested{' '}
                    {salary(c.default_amount, budget.currency)}
                  </p>
                </div>
                <label className="field">
                  {c.name} amount
                  <input
                    value={amounts[c.id]}
                    inputMode="decimal"
                    pattern="[0-9]{1,12}(\.[0-9]{1,2})?"
                    required
                    onChange={(e) => {
                      setAmounts({ ...amounts, [c.id]: e.target.value })
                      setDirty(true)
                      setConfirm(false)
                    }}
                  />
                </label>
              </div>
            ))}
          </div>
        </fieldset>
        <div className="mt-5">
          <Facts
            items={[
              [
                'Allocated',
                valid
                  ? salary(decimal(allocated), budget.currency)
                  : 'Enter valid amounts',
              ],
              [
                'Remaining',
                valid
                  ? salary(decimal(remaining), budget.currency)
                  : 'Enter valid amounts',
              ],
            ]}
          />
        </div>
        {!valid && (
          <Notice error>
            Use non-negative decimal amounts with at most two decimal places.
          </Notice>
        )}
        {valid && remaining < 0n && (
          <Notice error>Total allocations exceed your budget.</Notice>
        )}
        {error && <Notice error>{error}</Notice>}
        {editable && (
          <div className="actions mt-5">
            <button
              className="primary"
              disabled={busy || !valid || remaining < 0n}
            >
              {busy ? 'Saving…' : 'Save draft'}
            </button>
            <button
              className="secondary"
              type="button"
              disabled={busy || dirty || remaining !== 0n || !valid}
              onClick={() => setConfirm(true)}
            >
              Submit allocation
            </button>
          </div>
        )}
      </form>
      {editable && confirm && (
        <form className="mt-5" onSubmit={submit}>
          <fieldset disabled={busy}>
            <label className="flex gap-3 text-sm">
              <input type="checkbox" required />I confirm these saved
              allocations. They cannot be edited after submission.
            </label>
            <button className="primary mt-4">
              {busy ? 'Submitting…' : 'Confirm submission'}
            </button>
          </fieldset>
        </form>
      )}
    </section>
  )
}
export function MyPlan({ api }: { api: FbpClient }) {
  const { id } = useParams()
  const load = useLoad(() => api.request<PlanView>('/me/' + id), [api, id])
  return (
    <>
      <PageTitle
        title={load.data?.plan.name ?? 'My benefit plan'}
        description="Allocate your annual synthetic benefit budget."
      />
      <Link className="link" to="/fbp/me">
        Back to my benefits
      </Link>
      <LoadState {...load} />
      {load.data && (
        <div className="space-y-6 mt-5">
          {load.data.budgets.map((b) => (
            <ElectionEditor
              key={b.id + '-' + b.revision}
              api={api}
              view={load.data!}
              budget={b}
              onDone={load.reload}
            />
          ))}
        </div>
      )}
    </>
  )
}
