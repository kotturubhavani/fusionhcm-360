import { expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { AuthClient } from './auth'
import { Navigation } from './App'
import { AIClient } from './ai/api'
import type { Message, Policy } from './ai/api'
import { Chat, PolicyLibrary, AIRoutes, Answer } from './ai/pages'
const caps = {
  provider: 'mock',
  mode: 'Deterministic demo',
  staff: true,
  document_max_bytes: 2097152,
  streaming: false,
}
const convo = {
  id: 'c',
  title: 'Synthetic question',
  scope: 'STAFF',
  updated_at: '2026-01-01T00:00:00Z',
}
const citation = {
  id: 'chunk',
  document_id: 'document',
  document_name: 'remote.md',
  source_name: 'Synthetic policies',
  chunk_index: 0,
  text: 'Remote work requires manager approval.',
  score: 0.8,
}
const answer: Message = {
  id: 'a',
  role: 'assistant',
  sequence_number: 2,
  content: 'Here are the authorized source records.',
  details: {
    query_type: 'HYBRID',
    tool: 'get_my_payroll',
    provider: 'mock',
    status: 'SUCCESS',
    structured_data: { gross: '10000.25', net: '9000.20', currency: 'INR' },
    citations: [citation],
  },
}
const policy: Policy = {
  id: 'd',
  source_id: 's',
  filename: 'synthetic.md',
  content_type: 'text/markdown',
  status: 'INDEXED',
  indexed_at: '2026-01-01T00:00:00Z',
  safe_error_message: null,
  details: { chunk_count: 1, audience: 'ALL' },
}
function client() {
  const api = new AIClient(new AuthClient('http://localhost:8000'))
  vi.spyOn(api, 'capabilities').mockResolvedValue(caps)
  vi.spyOn(api, 'conversations').mockResolvedValue([])
  return api
}
it.each([true, false])('AI navigation and library staff=%s', (staff) => {
  render(
    <MemoryRouter>
      <Navigation staff={staff} />
    </MemoryRouter>,
  )
  expect(screen.getByRole('link', { name: 'AI Assistant' })).toBeTruthy()
  expect(Boolean(screen.queryByRole('link', { name: 'Policy Library' }))).toBe(
    staff,
  )
})
it('employee send renders exact source values, citations and owned history', async () => {
  const api = client()
  const send = vi.spyOn(api, 'chat').mockResolvedValue({
    status: 'SUCCESS',
    error: null,
    conversation_id: 'c',
    answer: answer.content,
  })
  vi.spyOn(api, 'history').mockResolvedValue({
    conversation: convo,
    messages: [
      {
        id: 'u',
        role: 'user',
        sequence_number: 1,
        content: 'Show my latest payroll',
        details: {},
      },
      answer,
    ],
  })
  render(
    <MemoryRouter>
      <Chat api={api} staff={false} />
    </MemoryRouter>,
  )
  await screen.findByText(/local deterministic responses/)
  expect(screen.queryByLabelText('Person number')).toBeNull()
  fireEvent.change(screen.getByLabelText('Your question'), {
    target: { value: 'Show my latest payroll' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Send message' }))
  expect(await screen.findByText('9000.20')).toBeTruthy()
  expect(screen.getByText('remote.md · Chunk 1')).toBeTruthy()
  expect(send).toHaveBeenCalledWith({
    message: 'Show my latest payroll',
    request_key: expect.any(String),
  })
})
it('loading disables send and conversation selection', async () => {
  const api = client()
  vi.spyOn(api, 'chat').mockImplementation(() => new Promise(() => {}))
  render(
    <MemoryRouter>
      <Chat api={api} staff />
    </MemoryRouter>,
  )
  fireEvent.change(screen.getByLabelText('Your question'), {
    target: { value: 'Show workers' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Send message' }))
  expect(await screen.findByText('Checking authorized sources…')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Working…' })).toBeDisabled()
  expect(
    screen.getByRole('button', { name: 'New conversation' }),
  ).toBeDisabled()
})
it('HR typed context is sent and backend failure is actionable', async () => {
  const api = client()
  const send = vi.spyOn(api, 'chat').mockResolvedValue({
    status: 'FAILED',
    error: 'Worker reference could not be resolved.',
  })
  render(
    <MemoryRouter>
      <Chat api={api} staff />
    </MemoryRouter>,
  )
  fireEvent.change(screen.getByLabelText('Your question'), {
    target: { value: 'Explain payroll' },
  })
  fireEvent.change(screen.getByLabelText('Person number'), {
    target: { value: 'DEMO360_P02' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Send message' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Worker reference')
  expect(send).toHaveBeenCalledWith(
    expect.objectContaining({ person_number: 'DEMO360_P02' }),
  )
})
it('provider network failure is shown without fake answers', async () => {
  const api = client()
  vi.spyOn(api, 'chat').mockRejectedValue(new Error('AI provider unavailable'))
  render(
    <MemoryRouter>
      <Chat api={api} staff={false} />
    </MemoryRouter>,
  )
  fireEvent.change(screen.getByLabelText('Your question'), {
    target: { value: 'What does the remote policy say?' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Send message' }))
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'AI provider unavailable',
  )
  expect(screen.queryByText(answer.content)).toBeNull()
})
it('opens history and starts fresh conversation', async () => {
  const api = client()
  vi.mocked(api.conversations).mockResolvedValue([convo])
  const history = vi
    .spyOn(api, 'history')
    .mockResolvedValue({ conversation: convo, messages: [answer] })
  render(
    <MemoryRouter>
      <Chat api={api} staff />
    </MemoryRouter>,
  )
  fireEvent.click(
    await screen.findByRole('button', { name: 'Synthetic question' }),
  )
  await screen.findByText('9000.20')
  expect(history).toHaveBeenCalledWith('c')
  fireEvent.click(screen.getByRole('button', { name: 'New conversation' }))
  expect(screen.queryByText('9000.20')).toBeNull()
})
it('source text is inert and financial values are not rounded', () => {
  render(
    <Answer
      content="Source"
      details={{
        structured_data: { salary: '999999999999.99' },
        citations: [{ ...citation, text: '<script>alert(1)</script>' }],
      }}
    />,
  )
  expect(screen.getByText('999999999999.99')).toBeTruthy()
  expect(screen.getByText('<script>alert(1)</script>')).toBeTruthy()
  expect(document.querySelector('script')).toBeNull()
})
it('document upload and indexed status', async () => {
  const api = client()
  vi.spyOn(api, 'documents').mockResolvedValue([policy])
  const upload = vi.spyOn(api, 'upload').mockResolvedValue(policy)
  render(
    <MemoryRouter>
      <PolicyLibrary api={api} />
    </MemoryRouter>,
  )
  await screen.findByText('INDEXED')
  const file = new File(['Synthetic remote policy text.'], 'synthetic.md', {
    type: 'text/markdown',
  })
  fireEvent.change(screen.getByLabelText('Policy document'), {
    target: { files: [file] },
  })
  fireEvent.submit(
    screen.getByRole('button', { name: 'Upload and index' }).closest('form')!,
  )
  await screen.findByText('synthetic.md: INDEXED')
  expect(upload).toHaveBeenCalledWith(file, 'ALL')
})
it('reindex failure and deactivate controls', async () => {
  const api = client()
  vi.spyOn(api, 'documents').mockResolvedValue([policy])
  const index = vi.spyOn(api, 'reindex').mockResolvedValue({
    ...policy,
    status: 'FAILED',
    safe_error_message: 'Indexing failed. Check the vector store.',
  })
  const deactivate = vi
    .spyOn(api, 'activate')
    .mockResolvedValue({ ...policy, status: 'INACTIVE' })
  render(
    <MemoryRouter>
      <PolicyLibrary api={api} />
    </MemoryRouter>,
  )
  fireEvent.click(await screen.findByRole('button', { name: 'Reindex' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Indexing failed')
  expect(index).toHaveBeenCalledWith('d')
  fireEvent.click(screen.getByRole('button', { name: 'Deactivate' }))
  await waitFor(() => expect(deactivate).toHaveBeenCalledWith('d', false))
})
it('employee library URL redirects without loading documents', async () => {
  const api = client()
  const docs = vi.spyOn(api, 'documents')
  render(
    <MemoryRouter initialEntries={['/ai/documents']}>
      <Routes>
        <Route path="/ai/*" element={<AIRoutes api={api} staff={false} />} />
      </Routes>
    </MemoryRouter>,
  )
  await screen.findByText(/Your own employment/)
  expect(docs).not.toHaveBeenCalled()
  expect(screen.queryByLabelText('Policy document')).toBeNull()
})
it('library load error and oversized upload', async () => {
  const api = client()
  vi.spyOn(api, 'documents').mockRejectedValue(new Error('Library unavailable'))
  const upload = vi.spyOn(api, 'upload')
  render(
    <MemoryRouter>
      <PolicyLibrary api={api} />
    </MemoryRouter>,
  )
  await screen.findByText('Library unavailable')
  const file = new File(['x'], 'large.txt')
  Object.defineProperty(file, 'size', { value: 3000000 })
  fireEvent.change(screen.getByLabelText('Policy document'), {
    target: { files: [file] },
  })
  fireEvent.submit(
    screen.getByRole('button', { name: 'Upload and index' }).closest('form')!,
  )
  await screen.findByText('Document exceeds the upload size limit.')
  expect(upload).not.toHaveBeenCalled()
})
it('renders multiple domain sources and preserves useful partial results', () => {
  render(
    <Answer
      content="Authorized sources"
      details={{
        status: 'PARTIAL',
        selected_agents: ['PAYROLL_AGENT', 'BENEFITS_AGENT'],
        sections: [
          {
            agent: 'PAYROLL_AGENT',
            tool: 'get_my_payroll',
            label: 'Payroll',
            status: 'SUCCESS',
            data: { net: '61108.33' },
            error: null,
          },
          {
            agent: 'BENEFITS_AGENT',
            tool: 'get_my_fbp',
            label: 'Benefits',
            status: 'FAILED',
            data: {},
            error: 'Benefits source unavailable.',
          },
        ],
        citations: [citation],
      }}
    />,
  )
  expect(screen.getByText('PAYROLL AGENT')).toBeTruthy()
  expect(screen.getByText('BENEFITS AGENT')).toBeTruthy()
  expect(
    screen.getByRole('region', { name: 'Payroll source' }),
  ).toHaveTextContent('61108.33')
  expect(
    screen.getByRole('region', { name: 'Benefits source' }),
  ).toHaveTextContent('Benefits source unavailable.')
  expect(screen.getByText(/Some sources could not complete/)).toBeTruthy()
  expect(screen.getByText(citation.text)).toBeTruthy()
  expect(screen.queryByText('agent_trace')).toBeNull()
})
it('employee cross-worker refusal displays without records or staff filters', async () => {
  const api = client()
  vi.spyOn(api, 'chat').mockRejectedValue(
    new Error('Employees can query only their own linked worker.'),
  )
  render(
    <MemoryRouter>
      <Chat api={api} staff={false} />
    </MemoryRouter>,
  )
  fireEvent.change(screen.getByLabelText('Your question'), {
    target: { value: 'Show another worker payroll' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Send message' }))
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'only their own linked worker',
  )
  expect(screen.queryByLabelText('Person number')).toBeNull()
  expect(screen.queryByRole('region', { name: 'Payroll source' })).toBeNull()
})
