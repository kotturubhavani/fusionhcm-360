import { expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AuthClient } from './auth'
import { CoreHrClient } from './core-hr/api'
import { Navigation } from './App'
import { PayrollClient } from './payroll/api'
import type {
  Definition,
  Period,
  Run,
  Result,
  ResultDetail,
  RunDetail,
} from './payroll/api'
import {
  Definitions,
  Periods,
  RunPage,
  MyPayroll,
  PayrollRoutes,
  ResultPage,
} from './payroll/pages'
import { salary } from './core-hr/types'
const definition: Definition = {
  id: 'd',
  code: 'IN_MONTHLY',
  name: 'Asterion India Monthly Payroll',
  legal_employer_id: 'employer',
  country_code: 'IN',
  currency: 'INR',
  frequency: 'MONTHLY',
  is_active: true,
  retirement_rate: '0.05',
  withholding_rate: '0.10',
  standard_allowance: '1000.00',
}
const period: Period = {
  id: 'p',
  payroll_definition_id: 'd',
  period_name: '2025-01',
  period_start: '2025-01-01',
  period_end: '2025-01-31',
  payment_date: '2025-01-31',
  status: 'OPEN',
}
const run: Run = {
  id: 'r',
  pay_period_id: 'p',
  run_number: 1,
  status: 'COMPLETED',
  started_at: '2026-10-06T00:00:00Z',
  completed_at: '2026-10-06T00:01:00Z',
  failure_reason: null,
  excluded_assignment_count: 0,
  unpaid_day_count: 0,
  rules_snapshot: { version: 'DEMO_MONTHLY_V1' },
}
const result: Result = {
  id: 'result',
  payroll_run_id: 'r',
  worker_name: 'Sai Kiran Reddy',
  person_number: 'P01',
  assignment_number: 'A01',
  gross_pay: '11000.00',
  total_deductions: '1600.00',
  net_pay: '9400.00',
  currency: 'INR',
  eligible_days: 31,
  period_days: 31,
  calculation_snapshot: [
    {
      from: '2025-01-01',
      to: '2025-01-31',
      days: 31,
      annual_base_salary: '120000.00',
      currency: 'INR',
      status: 'ACTIVE',
    },
  ],
}
const detail: ResultDetail = {
  result,
  period,
  definition_name: definition.name,
  lines: [
    {
      id: 'line',
      line_type: 'EARNING',
      code: 'BASE_PAY',
      name: 'Basic Pay',
      amount: '10000.00',
    },
  ],
}
function setup() {
  const auth = new AuthClient('http://localhost:8000')
  const api = new PayrollClient(auth)
  const hr = new CoreHrClient(auth)
  vi.spyOn(api, 'definitions').mockResolvedValue([definition])
  vi.spyOn(api, 'periods').mockResolvedValue([period])
  vi.spyOn(api, 'runs').mockResolvedValue([run])
  vi.spyOn(hr, 'all').mockResolvedValue([
    {
      id: 'employer2',
      name: 'Asterion Business Services Payroll',
      is_active: true,
      code: 'EMP2',
    },
  ])
  return { api, hr }
}
const fill = (name: string, value: string) =>
  fireEvent.change(screen.getByLabelText(name, { exact: true }), {
    target: { value },
  })
it.each([true, false])('payroll navigation follows role (%s)', (staff) => {
  render(
    <MemoryRouter>
      <Navigation staff={staff} />
    </MemoryRouter>,
  )
  expect(screen.queryByRole('link', { name: 'Payroll' }) !== null).toBe(staff)
  expect(screen.queryByRole('link', { name: 'My payroll' }) !== null).toBe(
    !staff,
  )
})
it('lists and creates definitions with decimal strings', async () => {
  const { api, hr } = setup()
  const save = vi.spyOn(api, 'request').mockResolvedValue(definition)
  render(
    <MemoryRouter>
      <Definitions api={api} hr={hr} />
    </MemoryRouter>,
  )
  await screen.findByText('Asterion India Monthly Payroll')
  fireEvent.click(screen.getByText('Create definition'))
  fill('Code *', 'SECOND')
  fill('Name *', 'Second payroll')
  fill('Legal employer *', 'employer2')
  fill('Country code *', 'IN')
  fill('Currency *', 'INR')
  fill('Monthly standard allowance *', '123.45')
  fireEvent.submit(screen.getByText('Save definition').closest('form')!)
  await waitFor(() =>
    expect(save).toHaveBeenCalledWith(
      '/definitions',
      expect.objectContaining({
        standard_allowance: '123.45',
        retirement_rate: '0.05',
        withholding_rate: '0.10',
      }),
    ),
  )
})
it('lists and creates pay periods', async () => {
  const { api } = setup()
  const save = vi.spyOn(api, 'request').mockResolvedValue(period)
  render(
    <MemoryRouter>
      <Periods api={api} />
    </MemoryRouter>,
  )
  await screen.findByText('Create period')
  fireEvent.click(screen.getByText('Create period'))
  fill('Payroll definition *', 'd')
  fill('Period name *', '2025-02')
  fill('Period start *', '2025-02-01')
  fill('Period end *', '2025-02-28')
  fill('Payment date *', '2025-02-28')
  fireEvent.submit(screen.getByText('Save period').closest('form')!)
  await waitFor(() =>
    expect(save).toHaveBeenCalledWith('/periods', {
      payroll_definition_id: 'd',
      period_name: '2025-02',
      period_start: '2025-02-01',
      period_end: '2025-02-28',
      payment_date: '2025-02-28',
    }),
  )
})
it('processing requires confirmation and disables duplicate submit while pending', async () => {
  const { api } = setup()
  let resolve: (value: Run) => void = () => {}
  const process = vi.spyOn(api, 'process').mockImplementation(
    () =>
      new Promise((r) => {
        resolve = r
      }),
  )
  render(
    <MemoryRouter>
      <Periods api={api} />
    </MemoryRouter>,
  )
  fireEvent.click(
    await screen.findByRole('button', { name: 'Process 2025-01 · IN_MONTHLY' }),
  )
  expect(screen.getByRole('checkbox')).toBeRequired()
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.submit(screen.getByText('Confirm processing').closest('form')!)
  expect(screen.getByText('Processing…')).toBeDisabled()
  expect(process).toHaveBeenCalledOnce()
  resolve(run)
  await waitFor(() =>
    expect(screen.queryByText('Processing…')).not.toBeInTheDocument(),
  )
})
it('completed periods have no process action', async () => {
  const { api } = setup()
  vi.mocked(api.periods).mockResolvedValue([{ ...period, status: 'PROCESSED' }])
  render(
    <MemoryRouter>
      <Periods api={api} />
    </MemoryRouter>,
  )
  await screen.findByText('Processed')
  expect(
    screen.queryByRole('button', { name: /^Process / }),
  ).not.toBeInTheDocument()
})
it('renders run metadata totals and result table', async () => {
  const { api } = setup()
  vi.spyOn(api, 'request').mockResolvedValue({
    run,
    period,
    definition_name: 'Asterion India Monthly Payroll',
    currency: 'INR',
    result_count: 1,
    gross_pay: '11000.00',
    total_deductions: '1600.00',
    net_pay: '9400.00',
  } satisfies RunDetail)
  vi.spyOn(api, 'all').mockResolvedValue([result])
  render(
    <MemoryRouter initialEntries={['/runs/r']}>
      <Routes>
        <Route path="/runs/:id" element={<RunPage api={api} />} />
      </Routes>
    </MemoryRouter>,
  )
  await screen.findByText('Sai Kiran Reddy')
  expect(screen.getAllByText('INR 9,400.00')).toHaveLength(2)
  expect(screen.getByRole('link', { name: 'View result' })).toHaveAttribute(
    'href',
    '/payroll/results/result',
  )
})
it('employee management deep links redirect to own payroll without management requests', async () => {
  const { api, hr } = setup()
  const all = vi.spyOn(api, 'all').mockResolvedValue([detail])
  render(
    <MemoryRouter initialEntries={['/payroll/definitions']}>
      <Routes>
        <Route
          path="/payroll/*"
          element={<PayrollRoutes api={api} hr={hr} staff={false} />}
        />
      </Routes>
    </MemoryRouter>,
  )
  await screen.findByRole('heading', { name: 'My payroll' })
  await screen.findByText('INR 9,400.00')
  expect(all).toHaveBeenCalledWith('/me')
  expect(api.definitions).not.toHaveBeenCalled()
  expect(screen.queryByText('Create definition')).not.toBeInTheDocument()
})
it('employee detail uses the self-service endpoint and shows lines', async () => {
  const { api } = setup()
  const request = vi.spyOn(api, 'request').mockResolvedValue(detail)
  render(
    <MemoryRouter initialEntries={['/me/result']}>
      <Routes>
        <Route path="/me/:id" element={<ResultPage api={api} self />} />
      </Routes>
    </MemoryRouter>,
  )
  await screen.findByText('Basic Pay')
  expect(screen.queryByText('BASE_PAY')).not.toBeInTheDocument()
  expect(request).toHaveBeenCalledWith('/me/result')
  expect(screen.getByText('INR 9,400.00')).toBeInTheDocument()
})
it('shows loading then safe errors with retry', async () => {
  const { api } = setup()
  let reject: (reason: Error) => void = () => {}
  vi.spyOn(api, 'all').mockImplementation(
    () =>
      new Promise((_, r) => {
        reject = r
      }),
  )
  render(
    <MemoryRouter>
      <MyPayroll api={api} />
    </MemoryRouter>,
  )
  expect(screen.getByRole('status')).toHaveTextContent('Loading')
  reject(new Error('No person is linked to this account.'))
  await screen.findByRole('alert')
  expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
})
it('preserves large decimal money formatting', () => {
  expect(salary('99999999999999.99', 'INR')).toBe('INR 99,999,999,999,999.99')
})
