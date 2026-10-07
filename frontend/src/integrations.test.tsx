import { expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { AuthClient } from './auth'
import { Navigation, Workspace } from './App'
import { IntegrationsClient } from './integrations/api'
import type { Definition, Run } from './integrations/api'
import {
  Dashboard,
  DefinitionForm,
  DefinitionDetail,
  RunDetail,
  IntegrationsRoutes,
} from './integrations/pages'
import { CoreHrClient } from './core-hr/api'
import { PayrollClient } from './payroll/api'
import { FbpClient } from './fbp/api'
import { ImportsClient } from './imports/api'
import { AnalyticsClient } from './analytics/api'
const definition: Definition = {
  id: 'd',
  code: 'SYNTHETIC',
  name: 'Synthetic integration',
  description: null,
  direction: 'OUTBOUND',
  integration_type: 'WORKER_EXPORT',
  transport_type: 'FILE',
  endpoint_url: null,
  http_method: null,
  output_format: 'JSON',
  configuration: { auth_type: 'NONE' },
  is_active: true,
}
const run: Run = {
  id: 'r',
  integration_definition_id: 'd',
  status: 'COMPLETED',
  retry_of_run_id: null,
  retry_depth: 0,
  requested_by_user_id: 'u',
  trigger_type: 'MANUAL',
  request_key: 'request',
  started_at: '2026-01-01T00:00:00Z',
  completed_at: '2026-01-01T00:00:01Z',
  records_read: 1,
  records_succeeded: 1,
  records_failed: 0,
  safe_error_message: null,
  definition_snapshot: definition,
  request_metadata: { transport: 'FILE' },
  response_metadata: { successful_items: 1 },
  output_filename: 'r.json',
}
const client = () =>
  new IntegrationsClient(new AuthClient('http://localhost:8000'))
it.each([true, false])('integration navigation staff=%s', (staff) => {
  render(
    <MemoryRouter>
      <Navigation staff={staff} />
    </MemoryRouter>,
  )
  expect(
    Boolean(screen.queryByRole('link', { name: 'Integration Center' })),
  ).toBe(staff)
})
it('definitions, recent runs and loading', async () => {
  const api = client()
  vi.spyOn(api, 'list').mockResolvedValue([definition])
  vi.spyOn(api, 'runs').mockResolvedValue([run])
  render(
    <MemoryRouter>
      <Dashboard api={api} />
    </MemoryRouter>,
  )
  expect(screen.getAllByRole('status').length).toBeGreaterThan(0)
  await screen.findByText('COMPLETED')
  expect(
    screen.getAllByRole('link', { name: 'Synthetic integration' }),
  ).toHaveLength(2)
})
it('list failure has retry', async () => {
  const api = client()
  vi.spyOn(api, 'list').mockRejectedValue(new Error('Service unavailable'))
  vi.spyOn(api, 'runs').mockResolvedValue([])
  render(
    <MemoryRouter>
      <Dashboard api={api} />
    </MemoryRouter>,
  )
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Service unavailable',
  )
  expect(screen.getByRole('button', { name: 'Try again' })).toBeTruthy()
})
it('controlled create conditional transport and credential reference', async () => {
  const api = client()
  const save = vi.spyOn(api, 'save').mockResolvedValue(definition)
  render(
    <MemoryRouter>
      <Routes>
        <Route path="/" element={<DefinitionForm api={api} />} />
        <Route path="/integrations/d" element={<p>Saved definition</p>} />
      </Routes>
    </MemoryRouter>,
  )
  expect(screen.queryByLabelText('Endpoint URL')).toBeNull()
  fireEvent.change(screen.getByLabelText('Code'), {
    target: { value: 'SYNTHETIC' },
  })
  fireEvent.change(screen.getByLabelText('Name'), {
    target: { value: 'Synthetic integration' },
  })
  fireEvent.change(screen.getByLabelText('Transport'), {
    target: { value: 'HTTP_REST' },
  })
  fireEvent.change(screen.getByLabelText('Endpoint URL'), {
    target: { value: 'https://partner.example/receive' },
  })
  fireEvent.change(screen.getByLabelText('Authentication'), {
    target: { value: 'BEARER_ENV' },
  })
  fireEvent.change(screen.getByLabelText('Credential environment key'), {
    target: { value: 'INTEGRATION_TOKEN_QA' },
  })
  expect(screen.queryByLabelText('Password')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Save integration' }))
  await screen.findByText('Saved definition')
  expect(save).toHaveBeenCalledWith(
    expect.objectContaining({
      http_method: 'POST',
      output_format: 'JSON',
      configuration: expect.objectContaining({
        credential_env_key: 'INTEGRATION_TOKEN_QA',
      }),
    }),
    undefined,
  )
})
it('edit deactivates and hides inbound endpoint', async () => {
  const api = client()
  const save = vi.spyOn(api, 'save').mockResolvedValue(definition)
  const inbound = {
    ...definition,
    direction: 'INBOUND' as const,
    integration_type: 'PERSON_UPDATE',
    configuration: {
      auth_type: 'BEARER_ENV' as const,
      credential_env_key: 'INTEGRATION_TOKEN_QA',
    },
    transport_type: 'HTTP_REST' as const,
  }
  render(
    <MemoryRouter>
      <DefinitionForm api={api} existing={inbound} />
    </MemoryRouter>,
  )
  expect(screen.queryByLabelText('Endpoint URL')).toBeNull()
  expect(screen.getByLabelText('Direction')).toBeDisabled()
  fireEvent.click(screen.getByLabelText('Active'))
  fireEvent.click(screen.getByRole('button', { name: 'Save integration' }))
  await waitFor(() =>
    expect(save).toHaveBeenCalledWith(
      expect.objectContaining({ is_active: false }),
      'd',
    ),
  )
})
it('run requires confirmation and uses a request key', async () => {
  const api = client()
  const execute = vi.spyOn(api, 'run').mockResolvedValue(run)
  render(
    <MemoryRouter>
      <Routes>
        <Route
          path="/"
          element={<DefinitionDetail api={api} definition={definition} />}
        />
        <Route path="/integrations/runs/r" element={<p>Saved run</p>} />
      </Routes>
    </MemoryRouter>,
  )
  expect(screen.getByRole('button', { name: 'Run Now' })).toBeDisabled()
  fireEvent.click(
    screen.getByLabelText('I confirm this local synthetic integration run.'),
  )
  await waitFor(() =>
    expect(screen.getByRole('button', { name: 'Run Now' })).not.toBeDisabled(),
  )
  fireEvent.click(screen.getByRole('button', { name: 'Run Now' }))
  await screen.findByText('Saved run')
  expect(execute).toHaveBeenCalledWith('d', { request_key: expect.any(String) })
})
it('inbound REST uses typed columns', async () => {
  const api = client()
  vi.spyOn(api, 'templates').mockResolvedValue([
    {
      object_type: 'PERSON_UPDATE',
      columns: ['person_number', 'preferred_name'],
      required: ['person_number'],
    },
  ])
  const execute = vi.spyOn(api, 'run').mockResolvedValue(run)
  render(
    <MemoryRouter>
      <DefinitionDetail
        api={api}
        definition={{
          ...definition,
          direction: 'INBOUND',
          integration_type: 'PERSON_UPDATE',
          transport_type: 'HTTP_REST',
        }}
      />
    </MemoryRouter>,
  )
  fireEvent.change(await screen.findByLabelText('person number'), {
    target: { value: 'SYNTHETIC_P' },
  })
  fireEvent.change(screen.getByLabelText('preferred name'), {
    target: { value: 'Synthetic' },
  })
  fireEvent.click(
    screen.getByLabelText('I confirm this local synthetic integration run.'),
  )
  fireEvent.click(screen.getByRole('button', { name: 'Run Now' }))
  await waitFor(() =>
    expect(execute).toHaveBeenCalledWith('d', {
      request_key: expect.any(String),
      records: [{ person_number: 'SYNTHETIC_P', preferred_name: 'Synthetic' }],
    }),
  )
})
function detail(api: IntegrationsClient) {
  render(
    <MemoryRouter initialEntries={['/integrations/runs/r']}>
      <Routes>
        <Route
          path="/integrations/runs/:id"
          element={<RunDetail api={api} />}
        />
      </Routes>
    </MemoryRouter>,
  )
}
it('run errors and explicit retry', async () => {
  const api = client()
  vi.spyOn(api, 'result').mockResolvedValue({
    ...run,
    status: 'FAILED',
    records_failed: 1,
    records_succeeded: 0,
    output_filename: null,
  })
  vi.spyOn(api, 'items').mockResolvedValue([
    {
      id: 'i',
      sequence_number: 1,
      business_reference: 'SYNTHETIC_P',
      status: 'FAILED',
      response_status: 503,
      safe_error_message: 'Partner rejected delivery.',
    },
  ])
  const retry = vi
    .spyOn(api, 'retry')
    .mockResolvedValue({ ...run, id: 'retry' })
  detail(api)
  await screen.findByText('Partner rejected delivery.')
  expect(
    screen.getByRole('button', { name: 'Retry failed items' }),
  ).toBeDisabled()
  fireEvent.click(
    screen.getByLabelText('I have checked failed items and partner receipts.'),
  )
  fireEvent.click(screen.getByRole('button', { name: 'Retry failed items' }))
  await waitFor(() =>
    expect(retry).toHaveBeenCalledWith('r', expect.any(String)),
  )
})
it('download authenticated artifact and safe metadata only', async () => {
  const api = client()
  vi.spyOn(api, 'result').mockResolvedValue(run)
  vi.spyOn(api, 'items').mockResolvedValue([])
  const download = vi
    .spyOn(api, 'download')
    .mockResolvedValue(new Blob(['synthetic']))
  vi.stubGlobal(
    'URL',
    Object.assign(URL, {
      createObjectURL: vi.fn().mockReturnValue('blob:test'),
      revokeObjectURL: vi.fn(),
    }),
  )
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  detail(api)
  fireEvent.click(
    await screen.findByRole('button', { name: 'Download output' }),
  )
  await waitFor(() => expect(download).toHaveBeenCalledWith('r'))
  expect(screen.queryByText('Authorization')).toBeNull()
})
it('history route', async () => {
  const api = client()
  vi.spyOn(api, 'runs').mockResolvedValue([run])
  render(
    <MemoryRouter initialEntries={['/history']}>
      <IntegrationsRoutes api={api} />
    </MemoryRouter>,
  )
  await screen.findByText('COMPLETED')
  expect(screen.getByText('Integration run history')).toBeTruthy()
})
it('employee direct URL redirects without integration calls', async () => {
  const auth = new AuthClient('http://localhost:8000'),
    api = new CoreHrClient(auth),
    integrations = new IntegrationsClient(auth)
  vi.spyOn(api, 'worker').mockRejectedValue(new Error('No linked worker'))
  const list = vi.spyOn(integrations, 'list')
  render(
    <MemoryRouter initialEntries={['/integrations']}>
      <Workspace
        user={{
          id: 'u',
          email: 'employee@example.test',
          first_name: 'Synthetic',
          last_name: 'Employee',
          roles: ['EMPLOYEE'],
        }}
        api={api}
        payroll={new PayrollClient(auth)}
        fbp={new FbpClient(auth)}
        imports={new ImportsClient(auth)}
        analytics={new AnalyticsClient(auth)}
        integrations={integrations}
        logout={() => {}}
        busy={false}
      />
    </MemoryRouter>,
  )
  await screen.findByText('No linked worker')
  expect(list).not.toHaveBeenCalled()
})
it('inbound FILE reads CSV and sends content without a local path', async () => {
  const api = client()
  vi.spyOn(api, 'templates').mockResolvedValue([
    {
      object_type: 'PERSON_UPDATE',
      columns: ['person_number', 'preferred_name'],
      required: ['person_number'],
    },
  ])
  const execute = vi.spyOn(api, 'run').mockResolvedValue(run)
  render(
    <MemoryRouter>
      <DefinitionDetail
        api={api}
        definition={{
          ...definition,
          direction: 'INBOUND',
          integration_type: 'PERSON_UPDATE',
          output_format: 'CSV',
        }}
      />
    </MemoryRouter>,
  )
  const file = new File(
    ['person_number,preferred_name\nSYNTHETIC_P,Synthetic\n'],
    'synthetic.csv',
    { type: 'text/csv' },
  )
  Object.defineProperty(file, 'text', {
    value: async () => 'person_number,preferred_name\nSYNTHETIC_P,Synthetic\n',
  })
  fireEvent.change(await screen.findByLabelText(/CSV input/), {
    target: { files: [file] },
  })
  fireEvent.click(
    screen.getByLabelText('I confirm this local synthetic integration run.'),
  )
  await waitFor(() =>
    expect(screen.getByRole('button', { name: 'Run Now' })).not.toBeDisabled(),
  )
  fireEvent.submit(screen.getByRole('button', { name: 'Run Now' }).closest('form')!)
  await waitFor(() =>
    expect(execute).toHaveBeenCalledWith('d', {
      request_key: expect.any(String),
      csv_content: 'person_number,preferred_name\nSYNTHETIC_P,Synthetic\n',
    }),
  )
})
