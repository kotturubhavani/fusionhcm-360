import { expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AuthClient } from './auth'
import { Navigation } from './App'
import { AnalyticsClient } from './analytics/api'
import type { Metadata, Definition, Run } from './analytics/api'
import {
  DefinitionEditor,
  Definitions,
  RunDetail,
  RunHistory,
} from './analytics/pages'
const metadata: Metadata = {
  CORE_HR_WORKERS: [
    {
      key: 'person_number',
      label: 'Person Number',
      type: 'text',
      operators: ['equals', 'contains', 'in'],
    },
    {
      key: 'employee_name',
      label: 'Employee Name',
      type: 'text',
      operators: ['equals', 'contains', 'in'],
    },
  ],
}
const definition: Definition = {
  id: 'd',
  code: 'SYNTH',
  name: 'Synthetic workforce',
  domain: 'CORE_HR_WORKERS',
  selected_columns: ['person_number'],
  filters: [],
  sort_definition: [],
  is_active: true,
}
const run: Run = {
  id: 'r',
  status: 'COMPLETED',
  row_count: 1,
  started_at: '2026-01-01T00:00:00Z',
  completed_at: '2026-01-01T00:00:01Z',
  error_message: null,
  definition_snapshot: { name: 'Synthetic workforce' },
}
const client = () =>
  new AnalyticsClient(new AuthClient('http://localhost:8000'))
it.each([true, false])('report/extract navigation staff=%s', (staff) => {
  render(
    <MemoryRouter>
      <Navigation staff={staff} />
    </MemoryRouter>,
  )
  expect(Boolean(screen.queryByRole('link', { name: 'Reports' }))).toBe(staff)
  expect(Boolean(screen.queryByRole('link', { name: 'Extracts' }))).toBe(staff)
})
it.each([true, false])('definition list extract=%s', async (extract) => {
  const api = client()
  vi.spyOn(api, 'list').mockResolvedValue([definition])
  render(
    <MemoryRouter>
      <Definitions api={api} extract={extract} />
    </MemoryRouter>,
  )
  expect(
    await screen.findByRole('link', { name: 'Synthetic workforce' }),
  ).toBeTruthy()
})
it('builder saves allowed columns, filters and sorting', async () => {
  const api = client()
  const save = vi.spyOn(api, 'save').mockResolvedValue(definition)
  render(
    <MemoryRouter>
      <DefinitionEditor
        api={api}
        extract={false}
        metadata={metadata}
        initial={null}
      />
    </MemoryRouter>,
  )
  fireEvent.change(screen.getByLabelText('Code'), {
    target: { value: 'SYNTH' },
  })
  fireEvent.change(screen.getByLabelText('Name'), {
    target: { value: 'Synthetic workforce' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Add filter' }))
  fireEvent.change(screen.getByLabelText('Value 1'), {
    target: { value: 'SYNTH' },
  })
  fireEvent.change(screen.getByLabelText('Sort field'), {
    target: { value: 'person_number' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Save definition' }))
  await screen.findByRole('button', { name: 'Run now' })
  expect(save).toHaveBeenCalledWith(
    false,
    expect.objectContaining({
      filters: [{ field: 'person_number', operator: 'equals', value: 'SYNTH' }],
      sort_definition: [{ field: 'person_number', direction: 'asc' }],
    }),
    undefined,
  )
})
it('extract create and explicit incremental run', async () => {
  const api = client()
  vi.spyOn(api, 'save').mockResolvedValue({
    ...definition,
    extract_type: 'WORKER_SNAPSHOT',
  })
  const execute = vi.spyOn(api, 'run').mockResolvedValue(run)
  render(
    <MemoryRouter>
      <Routes>
        <Route
          path="/"
          element={
            <DefinitionEditor
              api={api}
              extract
              metadata={metadata}
              initial={null}
            />
          }
        />
        <Route path="/extracts/runs/:id" element={<p>Run saved</p>} />
      </Routes>
    </MemoryRouter>,
  )
  fireEvent.change(screen.getByLabelText('Code'), {
    target: { value: 'SYNTH' },
  })
  fireEvent.change(screen.getByLabelText('Name'), {
    target: { value: 'Synthetic' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Save definition' }))
  await screen.findByRole('button', { name: 'Run now' })
  fireEvent.change(screen.getByLabelText('Mode'), {
    target: { value: 'INCREMENTAL' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Run now' }))
  await screen.findByText('Run saved')
  expect(execute).toHaveBeenCalledWith(true, 'd', { mode: 'INCREMENTAL' })
})
it.each([true, false])('results/download extract=%s', async (extract) => {
  const api = client()
  vi.spyOn(api, 'result').mockResolvedValue({
    ...run,
    mode: 'INCREMENTAL',
    watermark_to: run.started_at,
    output_filename: 'r.json',
  })
  vi.spyOn(api, 'rows').mockResolvedValue({
    columns: ['person_number'],
    total: 1,
    rows: [{ person_number: 'SYNTH' }],
  })
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
  render(
    <MemoryRouter initialEntries={['/runs/r']}>
      <Routes>
        <Route
          path="/runs/:id"
          element={<RunDetail api={api} extract={extract} />}
        />
      </Routes>
    </MemoryRouter>,
  )
  fireEvent.click(
    await screen.findByRole('button', {
      name: extract ? 'Download output' : 'Export CSV',
    }),
  )
  await waitFor(() =>
    expect(download).toHaveBeenCalledWith(extract, 'r', 'csv'),
  )
  if (!extract) {
    expect(screen.getByText('SYNTH')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Export XLSX' }))
    await waitFor(() =>
      expect(download).toHaveBeenCalledWith(false, 'r', 'xlsx'),
    )
  }
})
it('run history and loading/error states', async () => {
  const api = client()
  vi.spyOn(api, 'runs').mockResolvedValue([run])
  render(
    <MemoryRouter>
      <RunHistory api={api} extract />
    </MemoryRouter>,
  )
  expect(screen.getByRole('status')).toBeTruthy()
  expect(
    await screen.findByRole('link', { name: 'Synthetic workforce' }),
  ).toBeTruthy()
})
it('safe errors in report list', async () => {
  const api = client()
  vi.spyOn(api, 'list').mockRejectedValue(new Error('Unavailable'))
  render(
    <MemoryRouter>
      <Definitions api={api} extract={false} />
    </MemoryRouter>,
  )
  expect(await screen.findByRole('alert')).toHaveTextContent('Unavailable')
})
