import { AnalyticsClient } from './analytics/api'
import { expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AuthClient } from './auth'
import { Navigation, Workspace } from './App'
import { CoreHrClient } from './core-hr/api'
import { FbpClient } from './fbp/api'
import { PayrollClient } from './payroll/api'
import { ImportsClient } from './imports/api'
import type { ImportJob, ImportRow } from './imports/api'
import { ImportDashboard, NewImport, ImportDetail } from './imports/pages'
const job: ImportJob = {
  id: 'job',
  object_type: 'WORKER_HIRE',
  original_filename: 'synthetic.csv',
  status: 'VALIDATED',
  total_rows: 2,
  valid_rows: 1,
  invalid_rows: 1,
  processed_rows: 0,
  failed_rows: 0,
  created_at: '2026-01-01T00:00:00Z',
  validated_at: '2026-01-01T00:01:00Z',
  processed_at: null,
  created_by_user_id: 'uploader',
}
const row: ImportRow = {
  id: 'row',
  row_number: 2,
  status: 'INVALID',
  raw_data: { person_number: 'SAMPLE' },
  normalized_data: null,
  error_code: 'INVALID_DATE',
  error_message: 'start_date must use YYYY-MM-DD.',
  created_record_reference: null,
}
function api() {
  return new ImportsClient(new AuthClient('http://localhost:8000'))
}
function detail(client: ImportsClient) {
  render(
    <MemoryRouter initialEntries={['/imports/job']}>
      <Routes>
        <Route path="/imports/:id" element={<ImportDetail api={client} />} />
      </Routes>
    </MemoryRouter>,
  )
}
it.each([true, false])('import navigation staff=%s', (staff) => {
  render(
    <MemoryRouter>
      <Navigation staff={staff} />
    </MemoryRouter>,
  )
  expect(Boolean(screen.queryByRole('link', { name: 'Data Imports' }))).toBe(
    staff,
  )
})
it('renders history and pagination', async () => {
  const client = api()
  const list = vi.spyOn(client, 'jobs').mockResolvedValue([job])
  render(
    <MemoryRouter>
      <ImportDashboard api={client} />
    </MemoryRouter>,
  )
  expect(
    await screen.findByRole('link', { name: 'synthetic.csv' }),
  ).toBeTruthy()
  expect(list).toHaveBeenCalledWith(0)
  expect(
    (screen.getByRole('button', { name: 'Next jobs' }) as HTMLButtonElement)
      .disabled,
  ).toBe(true)
})
it('uploads multipart only after explicit submission and handles template download', async () => {
  const client = api()
  vi.spyOn(client, 'templates').mockResolvedValue([
    {
      object_type: 'WORKER_HIRE',
      columns: ['person_number'],
      required: ['person_number'],
    },
  ])
  const upload = vi.spyOn(client, 'upload').mockResolvedValue(job)
  vi.spyOn(client, 'template').mockResolvedValue('person_number\r\n')
  const create = vi.fn().mockReturnValue('blob:test')
  vi.stubGlobal(
    'URL',
    Object.assign(URL, { createObjectURL: create, revokeObjectURL: vi.fn() }),
  )
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  render(
    <MemoryRouter>
      <Routes>
        <Route path="/" element={<NewImport api={client} />} />
        <Route path="/imports/:id" element={<p>Uploaded job</p>} />
      </Routes>
    </MemoryRouter>,
  )
  fireEvent.click(
    await screen.findByRole('button', { name: 'Download template' }),
  )
  await waitFor(() => expect(create).toHaveBeenCalled())
  const file = new File(['person_number\nSYNTH'], 'sample.csv', {
    type: 'text/csv',
  })
  fireEvent.change(screen.getByLabelText('CSV file'), {
    target: { files: [file] },
  })
  expect(upload).not.toHaveBeenCalled()
  fireEvent.submit(
    screen.getByRole('button', { name: 'Upload CSV' }).closest('form')!,
  )
  await screen.findByText('Uploaded job')
  expect(upload).toHaveBeenCalledWith('WORKER_HIRE', file)
})
it('shows errors, filters, validates and requires process confirmation', async () => {
  const client = api()
  vi.spyOn(client, 'job').mockResolvedValue(job)
  const rows = vi.spyOn(client, 'rows').mockResolvedValue([row])
  const action = vi.spyOn(client, 'action').mockResolvedValue(job)
  detail(client)
  await screen.findByText('INVALID_DATE')
  fireEvent.change(screen.getByLabelText('Row status'), {
    target: { value: 'INVALID' },
  })
  await waitFor(() => expect(rows).toHaveBeenCalledWith('job', 'INVALID', 0))
  fireEvent.click(screen.getByRole('button', { name: 'Validate / dry run' }))
  await waitFor(() => expect(action).toHaveBeenCalledWith('job', 'validate'))
  await waitFor(() =>
    expect(
      (
        screen.getByRole('button', {
          name: 'Validate / dry run',
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(false),
  )
  const process = screen.getByRole('button', {
    name: 'Process valid rows',
  }) as HTMLButtonElement
  expect(process.disabled).toBe(true)
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.click(process)
  await waitFor(() => expect(action).toHaveBeenCalledWith('job', 'process'))
})
it('locks completed jobs and shows normalized values', async () => {
  const client = api()
  vi.spyOn(client, 'job').mockResolvedValue({ ...job, status: 'COMPLETED' })
  vi.spyOn(client, 'rows').mockResolvedValue([
    {
      ...row,
      status: 'PROCESSED',
      normalized_data: { annual_base_salary: '100.25' },
      error_code: null,
      error_message: null,
    },
  ])
  detail(client)
  await screen.findByText(/This job is locked/)
  expect(
    screen.queryByRole('button', { name: 'Process valid rows' }),
  ).toBeNull()
  expect(await screen.findByText('Normalized values')).toBeTruthy()
})
it('shows loading and safe request errors', async () => {
  const client = api()
  vi.spyOn(client, 'jobs').mockRejectedValue(
    new Error('Connection unavailable'),
  )
  render(
    <MemoryRouter>
      <ImportDashboard api={client} />
    </MemoryRouter>,
  )
  expect(screen.getByRole('status')).toBeTruthy()
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Connection unavailable',
  )
})
it.each(['/imports/job', '/reports/new', '/extracts/new'])(
  'employee cannot open management path %s',
  async (path) => {
    const auth = new AuthClient('http://localhost:8000')
    const hr = new CoreHrClient(auth)
    vi.spyOn(hr, 'worker').mockRejectedValue(new Error('No linked person'))
    render(
      <MemoryRouter initialEntries={[path]}>
        <Workspace
          integrations={{} as import('./integrations/api').IntegrationsClient}
          analytics={
            new AnalyticsClient(new AuthClient('http://localhost:8000'))
          }
          user={{
            id: 'u',
            email: 'synthetic@example.com',
            first_name: 'Synthetic',
            last_name: 'Employee',
            roles: ['EMPLOYEE'],
          }}
          api={hr}
          payroll={new PayrollClient(auth)}
          fbp={new FbpClient(auth)}
          imports={new ImportsClient(auth)}
          logout={() => {}}
          busy={false}
        />
      </MemoryRouter>,
    )
    expect(screen.queryByRole('link', { name: 'Data Imports' })).toBeNull()
    expect(screen.queryByRole('heading', { name: 'Import detail' })).toBeNull()
    await screen.findByText(/No linked person/)
  },
)
