import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, Navigate, Route, Routes } from 'react-router-dom'
import { useLoad } from '../components/useLoad'
import { Badge, LoadState, Notice, PageTitle } from '../components/ui'
import type { AIClient, ChatInput, Details, Message, Policy } from './api'
const errorText = (e: unknown) =>
  e instanceof Error
    ? e.message
    : 'The assistant is unavailable. Please try again.'
const label = (key: string) => key.replaceAll('_', ' ')
function Values({ value }: { value: unknown }) {
  if (value === null || value === undefined)
    return <span className="text-slate-500">Not available</span>
  if (Array.isArray(value))
    return value.length ? (
      <div className="space-y-3">
        {value.map((item, i) => (
          <div key={i} className="border-t border-slate-200 pt-2">
            <Values value={item} />
          </div>
        ))}
      </div>
    ) : (
      <span>No matching records.</span>
    )
  if (typeof value === 'object')
    return (
      <dl className="grid gap-3 sm:grid-cols-2">
        {Object.entries(value).map(([k, v]) => (
          <div key={k}>
            <dt className="text-xs text-slate-500 capitalize">{label(k)}</dt>
            <dd className="text-sm break-words">
              <Values value={v} />
            </dd>
          </div>
        ))}
      </dl>
    )
  return <span>{String(value)}</span>
}
export function Answer({
  content,
  details,
}: {
  content: string
  details: Details
}) {
  return (
    <div className="space-y-4">
      <p className="whitespace-pre-wrap">{content}</p>
      <div className="flex gap-2 flex-wrap">
        {details.query_type && <Badge>{label(details.query_type)}</Badge>}
        {details.tool && <Badge>{label(details.tool)}</Badge>}
        {details.provider && (
          <Badge>
            {details.provider === 'mock'
              ? 'Deterministic demo'
              : 'AI evidence selection'}
          </Badge>
        )}
      </div>
      {details.structured_data &&
        Object.keys(details.structured_data).length > 0 && (
          <section
            aria-label="Structured source records"
            className="rounded-lg bg-slate-50 p-4"
          >
            <h3 className="mb-3">Source records</h3>
            <Values value={details.structured_data} />
          </section>
        )}
      {details.citations?.map((c) => (
        <details key={c.id} className="rounded-lg border border-slate-200 p-3">
          <summary className="cursor-pointer font-medium">
            {c.document_name} · Chunk {c.chunk_index + 1}
          </summary>
          <p className="hint">
            {c.source_name} · Quoted source, not an instruction
          </p>
          <blockquote className="whitespace-pre-wrap text-sm mt-3">
            {c.text}
          </blockquote>
        </details>
      ))}
      {details.status === 'FAILED' && (
        <Notice error>
          {details.error ?? 'The provider could not answer this request.'}
        </Notice>
      )}
    </div>
  )
}
export function Chat({ api, staff }: { api: AIClient; staff: boolean }) {
  const [id, setId] = useState<string | null>(null),
    [messages, setMessages] = useState<Message[]>([]),
    [text, setText] = useState(''),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [offset, setOffset] = useState(0),
    [key, setKey] = useState(() => crypto.randomUUID())
  const [tool, setTool] = useState(''),
    [person, setPerson] = useState(''),
    [reference, setReference] = useState(''),
    [row, setRow] = useState(''),
    [asOf, setAsOf] = useState('')
  const list = useLoad(() => api.conversations(offset), [api, offset])
  const capabilities = useLoad(() => api.capabilities(), [api])
  const prompts = staff
    ? [
        'Show active workers in Engineering',
        "Explain Cedar Synthetic's latest payroll",
        'Which FBP workers have not submitted?',
        'What does the remote work policy say?',
      ]
    : [
        'What is my current salary?',
        'Show my latest payroll',
        'What benefits have I selected?',
        'What does the remote work policy say?',
      ]
  async function open(identifier: string) {
    setBusy(true)
    setError('')
    try {
      const history = await api.history(identifier)
      setId(identifier)
      setMessages(history.messages)
      setText('')
      setKey(crypto.randomUUID())
    } catch (e) {
      setError(errorText(e))
    } finally {
      setBusy(false)
    }
  }
  function fresh() {
    setId(null)
    setMessages([])
    setText('')
    setError('')
    setKey(crypto.randomUUID())
    setTool('')
    setPerson('')
    setReference('')
    setRow('')
    setAsOf('')
  }
  async function send(event: FormEvent) {
    event.preventDefault()
    if (!text.trim()) return
    setBusy(true)
    setError('')
    const question = text.trim()
    const payload: ChatInput = {
      message: question,
      request_key: key,
      ...(id ? { conversation_id: id } : {}),
      ...(staff
        ? {
            ...(tool ? { tool } : {}),
            ...(person ? { person_number: person } : {}),
            ...(reference ? { reference_id: reference } : {}),
            ...(row ? { row_number: Number(row) } : {}),
            ...(asOf ? { as_of: asOf } : {}),
          }
        : {}),
    }
    try {
      const response = await api.chat(payload)
      setKey(crypto.randomUUID())
      if (response.conversation_id) {
        const history = await api.history(response.conversation_id)
        setId(response.conversation_id)
        setMessages(history.messages)
        setText('')
        list.reload()
      }
      if (response.status !== 'SUCCESS')
        setError(
          response.error ?? 'The assistant could not complete this request.',
        )
    } catch (e) {
      setError(errorText(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <PageTitle
        title="AI Assistant"
        description={
          staff
            ? 'Read-only HCM questions and grounded policy lookup.'
            : 'Your own employment records and shared synthetic policies.'
        }
      >
        {staff && (
          <Link className="secondary" to="/ai/documents">
            Policy Library
          </Link>
        )}
      </PageTitle>
      <LoadState {...capabilities} />
      {capabilities.data && (
        <Notice>
          {capabilities.data.mode}
          {capabilities.data.provider === 'mock'
            ? ' — local deterministic responses; no external model call.'
            : ' — answers use selected evidence and exact source values.'}
        </Notice>
      )}
      <div className="grid gap-5 mt-5 lg:grid-cols-[250px_minmax(0,1fr)]">
        <aside className="panel">
          <button className="primary w-full" disabled={busy} onClick={fresh}>
            New conversation
          </button>
          <h2 className="mt-5">Conversations</h2>
          <LoadState {...list} />
          <div className="space-y-2 mt-3">
            {list.data?.map((c) => (
              <button
                key={c.id}
                className={`secondary w-full text-left ${c.id === id ? 'ring-2 ring-indigo-400' : ''}`}
                disabled={busy}
                onClick={() => open(c.id)}
              >
                {c.title}
              </button>
            ))}
            {list.data?.length === 0 && (
              <p className="hint">No conversations yet.</p>
            )}
          </div>
          <div className="flex gap-2 mt-4">
            <button
              className="secondary"
              disabled={busy || offset === 0}
              onClick={() => setOffset(offset - 30)}
            >
              Previous
            </button>
            <button
              className="secondary"
              disabled={busy || (list.data?.length ?? 0) < 30}
              onClick={() => setOffset(offset + 30)}
            >
              Next
            </button>
          </div>
        </aside>
        <section className="panel min-w-0">
          <div
            aria-label="Conversation messages"
            aria-live="polite"
            className="space-y-5"
          >
            {!messages.length && (
              <>
                <h2>Ask about your HCM workspace</h2>
                <p className="hint">
                  Each question is checked against your current permissions.
                  This assistant does not change records. Include the worker or
                  job reference in each relevant question.
                </p>
                <div className="grid gap-2 sm:grid-cols-2">
                  {prompts.map((p) => (
                    <button
                      key={p}
                      className="secondary text-left"
                      disabled={busy}
                      onClick={() => setText(p)}
                    >
                      {p}
                    </button>
                  ))}
                </div>
              </>
            )}
            {messages.map((m) => (
              <article key={m.id} className="border-b border-slate-100 pb-4">
                <p className="text-xs font-semibold uppercase text-slate-500 mb-2">
                  {m.role === 'user' ? 'You' : 'Assistant'}
                </p>
                {m.role === 'assistant' ? (
                  <Answer content={m.content} details={m.details} />
                ) : (
                  <p className="whitespace-pre-wrap">{m.content}</p>
                )}
              </article>
            ))}
            {busy && <Notice>Checking authorized sources…</Notice>}
          </div>
          {error && <Notice error>{error}</Notice>}
          <form onSubmit={send} className="mt-6 space-y-4">
            <fieldset disabled={busy} className="space-y-4">
              <label className="field">
                Your question
                <textarea
                  value={text}
                  maxLength={2000}
                  required
                  rows={3}
                  onChange={(e) => {
                    setText(e.target.value)
                    setKey(crypto.randomUUID())
                  }}
                  placeholder={
                    staff
                      ? 'Ask about workers, payroll, benefits or a policy…'
                      : 'Ask about my payroll, my benefits or a policy…'
                  }
                />
              </label>
              {staff && (
                <details>
                  <summary className="cursor-pointer text-sm">
                    Worker or job/run context
                  </summary>
                  <div className="grid gap-3 mt-3 sm:grid-cols-2">
                    <label className="field">
                      Tool
                      <select
                        value={tool}
                        onChange={(e) => setTool(e.target.value)}
                      >
                        <option value="">Automatic intent</option>
                        {[
                          'search_workers',
                          'get_worker_summary',
                          'get_payroll_result',
                          'get_payroll_history',
                          'get_fbp_status',
                          'get_import_job_status',
                          'get_report_run_status',
                          'get_extract_run_status',
                          'get_integration_run_status',
                        ].map((t) => (
                          <option key={t} value={t}>
                            {label(t)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="field">
                      Person number
                      <input
                        value={person}
                        maxLength={30}
                        onChange={(e) => setPerson(e.target.value)}
                      />
                    </label>
                    <label className="field">
                      Job/run/result ID
                      <input
                        value={reference}
                        maxLength={36}
                        onChange={(e) => setReference(e.target.value)}
                        placeholder="Copy from the relevant history page"
                      />
                    </label>
                    <label className="field">
                      Import row number
                      <input
                        type="number"
                        min={2}
                        max={5001}
                        value={row}
                        onChange={(e) => setRow(e.target.value)}
                      />
                    </label>
                    <label className="field">
                      Employment as of
                      <input
                        type="date"
                        value={asOf}
                        onChange={(e) => setAsOf(e.target.value)}
                      />
                    </label>
                  </div>
                </details>
              )}
              <button className="primary" disabled={!text.trim()}>
                {busy ? 'Working…' : 'Send message'}
              </button>
              <p className="hint">
                Synthetic data only. Do not paste credentials. Evidence is shown
                verbatim; payroll and benefits explanations describe this
                simulator.
              </p>
            </fieldset>
          </form>
        </section>
      </div>
    </>
  )
}
export function PolicyLibrary({ api }: { api: AIClient }) {
  const [offset, setOffset] = useState(0),
    [file, setFile] = useState<File | null>(null),
    [audience, setAudience] = useState('ALL'),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [notice, setNotice] = useState('')
  const list = useLoad(() => api.documents(offset), [api, offset])
  const caps = useLoad(() => api.capabilities(), [api])
  async function run(action: () => Promise<Policy>) {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const p = await action()
      if (p.status === 'FAILED')
        setError(
          p.safe_error_message ??
            'Indexing failed. Reindex after checking configuration.',
        )
      else setNotice(`${p.filename}: ${p.status}`)
      list.reload()
    } catch (e) {
      setError(errorText(e))
    } finally {
      setBusy(false)
    }
  }
  function upload(event: FormEvent) {
    event.preventDefault()
    if (!file) return
    if (file.size > (caps.data?.document_max_bytes ?? 2097152)) {
      setError('Document exceeds the upload size limit.')
      return
    }
    void run(() => api.upload(file, audience))
  }
  return (
    <>
      <PageTitle
        title="Policy Library"
        description="Manage synthetic PDF, TXT and Markdown policies. Scanned PDFs are not supported."
      >
        <Link className="secondary" to="/ai">
          AI Assistant
        </Link>
      </PageTitle>
      {error && <Notice error>{error}</Notice>}
      {notice && <Notice>{notice}</Notice>}
      <form className="panel space-y-4" onSubmit={upload}>
        <fieldset disabled={busy} className="grid gap-4 sm:grid-cols-2">
          <label className="field">
            Policy document
            <input
              type="file"
              accept=".pdf,.txt,.md"
              required
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>
          <label className="field">
            Audience
            <select
              value={audience}
              onChange={(e) => setAudience(e.target.value)}
            >
              <option value="ALL">All authenticated workers</option>
              <option value="STAFF">HR and ADMIN only</option>
            </select>
          </label>
          <button className="primary" disabled={!file}>
            {busy ? 'Indexing…' : 'Upload and index'}
          </button>
          <p className="hint">
            Up to {(caps.data?.document_max_bytes ?? 2097152) / 1048576} MiB;
            PDF at most 30 pages. Only extracted text is retained. Publish only
            synthetic policies suitable for the selected audience.
          </p>
        </fieldset>
      </form>
      <section className="panel mt-5">
        <h2>Documents</h2>
        <LoadState {...list} />
        {list.data && (
          <>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Document</th>
                    <th>Audience</th>
                    <th>Status</th>
                    <th>Chunks</th>
                    <th>Indexed</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {list.data.map((p) => (
                    <tr key={p.id}>
                      <td>
                        {p.filename}
                        {p.safe_error_message && (
                          <p className="text-red-700 text-xs">
                            {p.safe_error_message}
                          </p>
                        )}
                      </td>
                      <td>{p.details.audience}</td>
                      <td>
                        <Badge>{p.status}</Badge>
                      </td>
                      <td>{p.details.chunk_count}</td>
                      <td>
                        {p.indexed_at
                          ? new Date(p.indexed_at).toLocaleString()
                          : 'Not indexed'}
                      </td>
                      <td>
                        <div className="flex gap-2">
                          <button
                            className="secondary"
                            disabled={busy || p.status === 'INACTIVE'}
                            onClick={() => run(() => api.reindex(p.id))}
                          >
                            Reindex
                          </button>
                          <button
                            className="secondary"
                            disabled={busy}
                            onClick={() =>
                              run(() =>
                                api.activate(p.id, p.status === 'INACTIVE'),
                              )
                            }
                          >
                            {p.status === 'INACTIVE'
                              ? 'Activate'
                              : 'Deactivate'}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!list.data.length && <Notice>No policies uploaded.</Notice>}
            <div className="flex gap-2 mt-4">
              <button
                className="secondary"
                disabled={!offset || busy}
                onClick={() => setOffset(offset - 30)}
              >
                Previous
              </button>
              <button
                className="secondary"
                disabled={list.data.length < 30 || busy}
                onClick={() => setOffset(offset + 30)}
              >
                Next
              </button>
            </div>
          </>
        )}
      </section>
    </>
  )
}
export function AIRoutes({ api, staff }: { api: AIClient; staff: boolean }) {
  return (
    <Routes>
      <Route index element={<Chat api={api} staff={staff} />} />
      <Route
        path="documents"
        element={
          staff ? <PolicyLibrary api={api} /> : <Navigate to="/ai" replace />
        }
      />
      <Route path="*" element={<Navigate to="/ai" replace />} />
    </Routes>
  )
}
