import { FbpClient } from './fbp/api'
import { PayrollClient } from './payroll/api'
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AuthenticatedApp, Navigation, Workspace } from './App'
import { AuthClient } from './auth'
import { CoreHrClient } from './core-hr/api'
import { WorkerTable, WorkerDetail } from './core-hr/pages'
import { HirePage, ChangeForm } from './core-hr/forms'
import { ReferencePage } from './core-hr/reference'
import type { References, Worker } from './core-hr/types'
const ref = {
  id: 'ref',
  code: 'SYNTH',
  name: 'Synthetic organization',
  is_active: true,
}
const refs: References = {
  'legal-employers': [ref],
  'business-units': [ref],
  departments: [{ ...ref, business_unit_id: ref.id }],
  jobs: [ref],
  grades: [ref],
  locations: [ref],
}
const person = {
  id: 'person',
  person_number: 'P100',
  first_name: 'Aster',
  last_name: 'Synthetic',
  preferred_name: null,
  personal_email: 'aster@example.test',
  date_of_birth: null,
  phone: null,
  is_active: true,
}
const worker: Worker = {
  person,
  as_of: '2026-10-05',
  placements: [
    {
      work_relationship: {
        id: 'wr',
        person_id: person.id,
        legal_employer_id: ref.id,
        employment_type: 'REGULAR',
        start_date: '2024-01-01',
        end_date: null,
        termination_reason: null,
      },
      assignment: {
        id: 'assignment',
        assignment_number: 'A100',
        work_relationship_id: 'wr',
        start_date: '2024-01-01',
        end_date: null,
      },
      version: {
        id: 'version',
        assignment_id: 'assignment',
        business_unit_id: ref.id,
        department_id: ref.id,
        job_id: ref.id,
        grade_id: null,
        location_id: ref.id,
        manager_assignment_id: null,
        status: 'ACTIVE',
        work_time_type: 'FULL_TIME',
        effective_from: '2024-01-01',
        effective_to: null,
      },
      compensation: {
        effective_from: '2024-01-01',
        effective_to: null,
        annual_base_salary: '999999999999.99',
        currency: 'INR',
      },
      relationship_status: 'ACTIVE',
      business_unit: ref,
      department: ref,
      job: ref,
      grade: null,
      location: ref,
      manager: null,
      manager_assignment: null,
    },
  ],
}
const user = {
  id: 'user',
  first_name: 'Aster',
  last_name: 'Synthetic',
  email: 'aster@example.test',
  roles: ['EMPLOYEE'],
}
function client() {
  const api = new CoreHrClient(new AuthClient('http://localhost:8000'))
  vi.spyOn(api, 'workers').mockResolvedValue([worker])
  vi.spyOn(api, 'worker').mockResolvedValue(worker)
  vi.spyOn(api, 'relationships').mockResolvedValue([
    worker.placements[0].work_relationship,
  ])
  vi.spyOn(api, 'references').mockResolvedValue(refs)
  return api
}
function field(name: string, value: string) {
  fireEvent.change(screen.getByLabelText(new RegExp('^' + name)), {
    target: { value },
  })
}
function organization() {
  field('Business unit', ref.id)
  field('Department', ref.id)
  field('Job', ref.id)
  field('Location', ref.id)
}
describe('role-aware workspace', () => {
  it.each([true, false])('navigation follows staff access (%s)', (staff) => {
    render(
      <MemoryRouter>
        <Navigation staff={staff} />
      </MemoryRouter>,
    )
    expect(screen.queryByText('Hire Worker') !== null).toBe(staff)
    expect(screen.queryByText('My employment') !== null).toBe(!staff)
  })
  it('employee deep links resolve to self service without any directory request or HR controls', async () => {
    const api = client()
    render(
      <MemoryRouter initialEntries={['/workers/someone-else']}>
        <Workspace
          fbp={new FbpClient(new AuthClient('http://localhost:8000'))}
          payroll={new PayrollClient(new AuthClient('http://localhost:8000'))}
          user={user}
          api={api}
          busy={false}
          logout={() => {}}
        />
      </MemoryRouter>,
    )
    await screen.findByText('Personal information')
    expect(api.worker).toHaveBeenCalledWith(undefined, expect.any(String))
    expect(api.workers).not.toHaveBeenCalled()
    expect(api.references).not.toHaveBeenCalled()
    expect(screen.queryByText('Change compensation')).not.toBeInTheDocument()
    expect(screen.queryByText('Hire Worker')).not.toBeInTheDocument()
  })
  it('restores auth then logs out and removes private content', async () => {
    const auth = new AuthClient('http://localhost:8000')
    vi.spyOn(auth, 'me').mockResolvedValue(user)
    vi.spyOn(auth, 'api').mockResolvedValue(worker)
    const logout = vi.spyOn(auth, 'logout').mockResolvedValue()
    render(
      <MemoryRouter>
        <AuthenticatedApp client={auth} />
      </MemoryRouter>,
    )
    await screen.findByText('Personal information')
    fireEvent.click(screen.getByText('Sign out'))
    await screen.findByRole('heading', { name: 'Sign in' })
    expect(logout).toHaveBeenCalledOnce()
    expect(screen.queryByText('Personal information')).not.toBeInTheDocument()
  })
})
it('renders directory names, numbers and assignments', () => {
  render(
    <MemoryRouter>
      <WorkerTable workers={[worker]} refs={refs} />
    </MemoryRouter>,
  )
  expect(screen.getByRole('link', { name: 'Aster Synthetic' })).toHaveAttribute(
    'href',
    '/workers/person?as_of=2026-10-05',
  )
  expect(screen.getByText('P100')).toBeInTheDocument()
  expect(screen.getByText('Active')).toBeInTheDocument()
})
it('renders worker details and exact salary; loads as-of date', async () => {
  const api = client()
  render(
    <MemoryRouter initialEntries={['/workers/person?as_of=2024-02-01']}>
      <Routes>
        <Route
          path="/workers/:personId"
          element={<WorkerDetail api={api} refs={refs} />}
        />
      </Routes>
    </MemoryRouter>,
  )
  await screen.findByText('INR 999,999,999,999.99')
  expect(api.worker).toHaveBeenCalledWith('person', '2024-02-01')
  expect(screen.getByText('No manager assigned')).toBeInTheDocument()
  expect(
    screen.queryByRole('button', { name: 'Rehire worker' }),
  ).not.toBeInTheDocument()
})
it('submits hire with nested identity, filtered department and decimal salary text', async () => {
  const api = client()
  const hire = vi.spyOn(api, 'hire').mockResolvedValue({ person } as never)
  render(
    <MemoryRouter>
      <HirePage api={api} refs={refs} />
    </MemoryRouter>,
  )
  await screen.findByLabelText('Business unit *')
  field('Person number', 'P200')
  field('First name', 'Birch')
  field('Last name', 'Synthetic')
  field('Legal employer', ref.id)
  field('Assignment number', 'A200')
  organization()
  field('Annual base salary', '100000.25')
  field('Currency', 'inr')
  fireEvent.submit(
    screen.getByRole('button', { name: 'Hire worker' }).closest('form')!,
  )
  await waitFor(() => expect(hire).toHaveBeenCalledOnce())
  expect(hire.mock.calls[0][0]).toMatchObject({
    person: { person_number: 'P200', first_name: 'Birch' },
    department_id: ref.id,
    annual_base_salary: '100000.25',
    currency: 'INR',
  })
})
it('assignment changes submit a complete snapshot without compensation fields', async () => {
  const api = client()
  const request = vi.spyOn(api, 'request').mockResolvedValue({})
  const done = vi.fn()
  render(
    <ChangeForm
      api={api}
      refs={refs}
      placement={worker.placements[0]}
      personId="person"
      kind="assignment"
      onDone={done}
      onCancel={() => {}}
    />,
  )
  await screen.findByLabelText('Business unit *')
  fireEvent.input(screen.getByLabelText('Effective date *'), {
    target: { value: '2026-12-01' },
  })
  await screen.findByLabelText('Business unit *')
  field('Assignment status', 'ON_LEAVE')
  fireEvent.submit(
    screen.getByRole('button', { name: 'Confirm change' }).closest('form')!,
  )
  await waitFor(() => expect(done).toHaveBeenCalledOnce())
  expect(request).toHaveBeenCalledWith(
    '/assignments/assignment/changes',
    'POST',
    expect.objectContaining({
      effective_from: '2026-12-01',
      status: 'ON_LEAVE',
      business_unit_id: ref.id,
      manager_assignment_id: null,
    }),
  )
  expect(request.mock.calls[0][2]).not.toHaveProperty('annual_base_salary')
})
it('compensation preserves a large decimal string exactly', async () => {
  const api = client()
  const request = vi.spyOn(api, 'request').mockResolvedValue({})
  render(
    <ChangeForm
      api={api}
      refs={refs}
      placement={worker.placements[0]}
      personId="person"
      kind="compensation"
      onDone={() => {}}
      onCancel={() => {}}
    />,
  )
  fireEvent.submit(
    screen.getByRole('button', { name: 'Confirm change' }).closest('form')!,
  )
  await waitFor(() =>
    expect(request).toHaveBeenCalledWith(
      '/assignments/assignment/compensation',
      'POST',
      expect.objectContaining({ annual_base_salary: '999999999999.99' }),
    ),
  )
})
it('termination requires explicit confirmation', () => {
  render(
    <ChangeForm
      api={client()}
      refs={refs}
      placement={worker.placements[0]}
      personId="person"
      kind="terminate"
      onDone={() => {}}
      onCancel={() => {}}
    />,
  )
  expect(screen.getByRole('checkbox')).toBeRequired()
  expect(screen.getByRole('checkbox')).not.toBeChecked()
})
it('creates, edits and deactivates references through POST/PATCH payloads', async () => {
  const api = client()
  const save = vi.spyOn(api, 'saveReference').mockResolvedValue(ref)
  const reload = vi.fn().mockResolvedValue(undefined)
  render(<ReferencePage api={api} refs={refs} reload={reload} />)
  fireEvent.click(screen.getByText('Add record'))
  field('Code', 'NEW')
  field('Name', 'New Synthetic')
  field('Country code', 'IN')
  fireEvent.submit(screen.getByText('Save record').closest('form')!)
  await waitFor(() =>
    expect(save).toHaveBeenCalledWith(
      'legal-employers',
      {
        code: 'NEW',
        name: 'New Synthetic',
        country_code: 'IN',
        is_active: true,
      },
      undefined,
    ),
  )
  await screen.findByText('Legal employers saved.')
  fireEvent.click(screen.getByLabelText('Edit Synthetic organization'))
  field('Name', 'Updated Synthetic')
  field('Country code', 'IN')
  fireEvent.submit(screen.getByText('Save record').closest('form')!)
  await waitFor(() =>
    expect(save).toHaveBeenCalledWith(
      'legal-employers',
      expect.objectContaining({ name: 'Updated Synthetic' }),
      'ref',
    ),
  )
  await waitFor(() =>
    expect(screen.queryByText('Save record')).not.toBeInTheDocument(),
  )
  fireEvent.click(screen.getByLabelText('Deactivate Synthetic organization'))
  await waitFor(() =>
    expect(save).toHaveBeenCalledWith(
      'legal-employers',
      { is_active: false },
      'ref',
    ),
  )
})
it('fetches every page before reporting directory counts', async () => {
  const api = client()
  const request = vi
    .spyOn(api, 'request')
    .mockResolvedValueOnce(Array(100).fill(worker))
    .mockResolvedValueOnce([worker])
  expect(await api.all('/workers?as_of=2026-10-05')).toHaveLength(101)
  expect(request.mock.calls[1][0]).toContain('offset=100&limit=100')
})
