import { expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { AuthClient } from './auth'
import { Navigation } from './App'
import { CoreHrClient } from './core-hr/api'
import { FbpClient, cents, decimal } from './fbp/api'
import type { Plan, Component, Budget, PlanView, Summary } from './fbp/api'
import {
  PlansPage,
  PlanPage,
  ComponentForm,
  ElectionEditor,
  FbpRoutes,
  MyBenefits,
} from './fbp/pages'
const plan: Plan = {
  id: 'plan',
  code: 'SYNTH',
  name: 'Annual Benefits',
  legal_employer_id: 'employer',
  plan_year: 2026,
  effective_from: '2026-01-01',
  effective_to: '2026-12-31',
  currency: 'INR',
  budget_rate: '0.10',
  status: 'OPEN',
  is_active: true,
  budgets_generated_at: '2026-01-01T00:00:00Z',
}
const component: Component = {
  id: 'component',
  plan_id: 'plan',
  code: 'FLEX',
  name: 'Flexible benefit',
  description: 'Annual allowance',
  component_type: 'BENEFIT',
  min_amount: '0.00',
  max_amount: '999999.99',
  default_amount: '0.00',
  display_order: 0,
  is_active: true,
}
const budget: Budget = {
  id: 'budget',
  plan_id: 'plan',
  person_id: 'person',
  assignment_id: 'assignment',
  person_number: 'P01',
  worker_name: 'Nikhil Varma',
  assignment_number: 'A01',
  annual_base_salary: '120000.00',
  budget_rate: '0.10',
  eligible_budget: '12000.00',
  currency: 'INR',
  status: 'OPEN',
  revision: 0,
  allocated: '0.00',
  remaining: '12000.00',
  elections: [],
  submitted_at: null,
  finalized_at: null,
}
const view: PlanView = { plan, components: [component], budgets: [budget] }
const summary: Summary = {
  workers: 1,
  budgets: 1,
  open: 1,
  submitted: 0,
  finalized: 0,
  eligible_budget: '12000.00',
  allocated: '0.00',
  remaining: '12000.00',
  currency: 'INR',
}
function setup() {
  const auth = new AuthClient('http://localhost:8000')
  const api = new FbpClient(auth),
    hr = new CoreHrClient(auth)
  vi.spyOn(hr, 'all').mockResolvedValue([
    {
      id: 'employer',
      name: 'Asterion Digital Technologies Pvt. Ltd.',
      code: 'EMP',
      is_active: true,
    },
  ])
  return { api, hr }
}
const fill = (name: string, value: string) =>
  fireEvent.change(screen.getByLabelText(name, { exact: true }), {
    target: { value },
  })
it.each([true, false])(
  'benefits navigation follows staff flag (%s)',
  (staff) => {
    render(
      <MemoryRouter>
        <Navigation staff={staff} />
      </MemoryRouter>,
    )
    expect(!!screen.queryByRole('link', { name: 'Benefits' })).toBe(
      staff,
    )
    expect(!!screen.queryByRole('link', { name: 'My benefits' })).toBe(!staff)
  },
)
it('lists plans and creates a calendar-year plan with string rate', async () => {
  const { api, hr } = setup()
  vi.spyOn(api, 'all').mockResolvedValue([plan])
  const request = vi.spyOn(api, 'request').mockResolvedValue(summary)
  render(
    <MemoryRouter>
      <PlansPage api={api} hr={hr} />
    </MemoryRouter>,
  )
  await screen.findByText(plan.name)
  fireEvent.click(screen.getByText('Create plan'))
  fill('Code *', 'NEW')
  fill('Plan name *', 'Annual Benefits 2027')
  fill('Legal employer *', 'employer')
  fill('Plan year *', '2027')
  fill('Currency *', 'INR')
  fireEvent.submit(screen.getByText('Save plan').closest('form')!)
  await waitFor(() =>
    expect(request).toHaveBeenCalledWith(
      '/plans',
      'POST',
      expect.objectContaining({
        plan_year: 2027,
        effective_from: '2027-01-01',
        effective_to: '2027-12-31',
        budget_rate: '0.10',
      }),
    ),
  )
})
it('renders plan detail and worker allocation overview', async () => {
  const { api } = setup()
  vi.spyOn(api, 'all').mockResolvedValue([budget])
  vi.spyOn(api, 'request').mockImplementation(async (path) =>
    path.endsWith('/summary')
      ? summary
      : path.endsWith('/components')
        ? [component]
        : (plan as never),
  )
  render(
    <MemoryRouter initialEntries={['/plans/plan']}>
      <Routes>
        <Route path="/plans/:id" element={<PlanPage api={api} />} />
      </Routes>
    </MemoryRouter>,
  )
  await screen.findByText('Nikhil Varma')
  expect(screen.getByText('A01')).toBeInTheDocument()
  expect(
    screen.getByRole('button', { name: 'Generate budgets' }),
  ).toBeDisabled()
  expect(
    screen.getByRole('button', { name: 'Close and finalize' }),
  ).toBeDisabled()
})
it('creates and edits a component including deactivation', async () => {
  const { api } = setup()
  const request = vi.spyOn(api, 'request').mockResolvedValue(component)
  const done = vi.fn()
  const renderResult = render(
    <ComponentForm api={api} planId="plan" onDone={done} onCancel={() => {}} />,
  )
  fill('Component code *', 'LEARN')
  fill('Component name *', 'Learning')
  fill('Maximum amount *', '12000.25')
  fireEvent.submit(screen.getByText('Save component').closest('form')!)
  await waitFor(() =>
    expect(request).toHaveBeenCalledWith(
      '/plans/plan/components',
      'POST',
      expect.objectContaining({
        max_amount: '12000.25',
        is_active: true,
        display_order: 0,
      }),
    ),
  )
  renderResult.unmount()
  render(
    <ComponentForm
      api={api}
      planId="plan"
      initial={component}
      onDone={done}
      onCancel={() => {}}
    />,
  )
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.submit(screen.getByText('Save component').closest('form')!)
  await waitFor(() =>
    expect(request).toHaveBeenCalledWith(
      '/components/component',
      'PATCH',
      expect.objectContaining({ is_active: false }),
    ),
  )
})
it('confirms budget generation before API call', async () => {
  const { api } = setup()
  vi.spyOn(api, 'all').mockResolvedValue([])
  const request = vi
    .spyOn(api, 'request')
    .mockImplementation(async (path) =>
      path.endsWith('/components')
        ? [component]
        : path.endsWith('/summary')
          ? { ...summary, budgets: 0 }
          : ({ ...plan, budgets_generated_at: null } as never),
    )
  render(
    <MemoryRouter initialEntries={['/plans/plan']}>
      <Routes>
        <Route path="/plans/:id" element={<PlanPage api={api} />} />
      </Routes>
    </MemoryRouter>,
  )
  fireEvent.click(await screen.findByText('Generate budgets'))
  expect(screen.getByRole('checkbox')).toBeRequired()
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.submit(screen.getByText('Confirm action').closest('form')!)
  await waitFor(() =>
    expect(request).toHaveBeenCalledWith(
      '/plans/plan/generate-budgets',
      'POST',
    ),
  )
})
it('employee management deep links resolve to own benefits', async () => {
  const { api, hr } = setup()
  const all = vi.spyOn(api, 'all').mockResolvedValue([view])
  render(
    <MemoryRouter initialEntries={['/fbp/plans/other']}>
      <Routes>
        <Route
          path="/fbp/*"
          element={<FbpRoutes api={api} hr={hr} staff={false} />}
        />
      </Routes>
    </MemoryRouter>,
  )
  await screen.findByRole('heading', { name: 'My benefits' })
  await screen.findByText(plan.name)
  expect(all).toHaveBeenCalledWith('/me')
  expect(hr.all).not.toHaveBeenCalled()
  expect(screen.queryByText('Generate budgets')).not.toBeInTheDocument()
})
it('edits exact decimal elections, rejects excess and saves revision', async () => {
  const { api } = setup()
  const request = vi.spyOn(api, 'request').mockResolvedValue(budget)
  render(
    <ElectionEditor api={api} view={view} budget={budget} onDone={() => {}} />,
  )
  fill('Flexible benefit amount', '12000.01')
  expect(screen.getByRole('alert')).toHaveTextContent('exceed')
  expect(screen.getByText('Save draft')).toBeDisabled()
  fill('Flexible benefit amount', '11999.99')
  expect(screen.getByText('INR 0.01')).toBeInTheDocument()
  expect(screen.getByText('Submit allocation')).toBeDisabled()
  fireEvent.submit(screen.getByText('Save draft').closest('form')!)
  await waitFor(() =>
    expect(request).toHaveBeenCalledWith('/me/plan/elections', 'POST', {
      worker_budget_id: 'budget',
      expected_revision: 0,
      elections: [{ component_id: 'component', amount: '11999.99' }],
    }),
  )
})
it('submits a saved exact allocation after confirmation', async () => {
  const { api } = setup()
  const request = vi.spyOn(api, 'request').mockResolvedValue(budget)
  const allocated = {
    ...budget,
    revision: 1,
    allocated: '12000.00',
    remaining: '0.00',
    elections: [{ component_id: 'component', amount: '12000.00' }],
  }
  render(
    <ElectionEditor
      api={api}
      view={view}
      budget={allocated}
      onDone={() => {}}
    />,
  )
  fireEvent.click(screen.getByText('Submit allocation'))
  expect(screen.getByRole('checkbox')).toBeRequired()
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.submit(screen.getByText('Confirm submission').closest('form')!)
  await waitFor(() =>
    expect(request).toHaveBeenCalledWith('/me/plan/submit', 'POST', {
      worker_budget_id: 'budget',
      expected_revision: 1,
    }),
  )
})
it('finalized allocations are read-only', () => {
  const { api } = setup()
  render(
    <ElectionEditor
      api={api}
      view={{ ...view, plan: { ...plan, status: 'CLOSED' } }}
      budget={{ ...budget, status: 'FINALIZED' }}
      onDone={() => {}}
    />,
  )
  expect(screen.getByLabelText('Flexible benefit amount')).toBeDisabled()
  expect(screen.queryByText('Save draft')).not.toBeInTheDocument()
  expect(screen.getByText('This allocation is read-only.')).toBeInTheDocument()
})
it('shows server validation errors and loading errors', async () => {
  const { api } = setup()
  vi.spyOn(api, 'request').mockRejectedValue(
    new Error(
      'This allocation changed in another session. Reload before saving.',
    ),
  )
  const rendered = render(
    <ElectionEditor api={api} view={view} budget={budget} onDone={() => {}} />,
  )
  fireEvent.submit(screen.getByText('Save draft').closest('form')!)
  await screen.findByRole('alert')
  rendered.unmount()
  let reject: (error: Error) => void = () => {}
  vi.spyOn(api, 'all').mockImplementation(
    () =>
      new Promise((_, r) => {
        reject = r
      }),
  )
  render(<MyBenefits api={api} />)
  expect(screen.getByRole('status')).toHaveTextContent('Loading')
  reject(new Error('Unavailable'))
  await screen.findByRole('alert')
  expect(screen.getByText('Try again')).toBeInTheDocument()
})
it('uses integer cents for exact large money and rejects float-shaped input', () => {
  expect(decimal(cents('999999999999.99')! - cents('0.01')!)).toBe(
    '999999999999.98',
  )
  expect(cents('1e3')).toBeNull()
  expect(cents('1.001')).toBeNull()
  expect(decimal(-1n)).toBe('-0.01')
})
