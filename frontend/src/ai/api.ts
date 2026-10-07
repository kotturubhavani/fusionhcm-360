import type { AuthClient } from '../auth'
export interface Citation {
  id: string
  document_id: string
  document_name: string
  source_name: string
  chunk_index: number
  text: string
  score: number
}
export interface Details {
  query_type?: string
  tool?: string | null
  structured_data?: Record<string, unknown>
  citations?: Citation[]
  provider?: string
  status?: string
  error?: string | null
}
export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  details: Details
  sequence_number: number
}
export interface Conversation {
  id: string
  title: string
  scope: string
  updated_at: string
}
export interface ChatInput {
  message: string
  request_key: string
  conversation_id?: string
  tool?: string
  person_number?: string
  reference_id?: string
  row_number?: number
  document_id?: string
  as_of?: string
}
export interface ChatResult extends Details {
  status: string
  error: string | null
  answer?: string
  conversation_id?: string
  message_id?: string
}
export interface Policy {
  id: string
  source_id: string
  filename: string
  content_type: string
  status: string
  indexed_at: string | null
  safe_error_message: string | null
  details: { chunk_count: number; audience: string; embedding?: string }
}
export interface Capabilities {
  provider: string
  mode: string
  staff: boolean
  document_max_bytes: number
  streaming: boolean
}
export class AIClient {
  private auth: AuthClient
  constructor(auth: AuthClient) {
    this.auth = auth
  }
  capabilities = () => this.auth.api<Capabilities>('/ai/capabilities')
  conversations = (offset = 0) =>
    this.auth.api<Conversation[]>(`/ai/conversations?offset=${offset}`)
  history = (id: string) =>
    this.auth.api<{ conversation: Conversation; messages: Message[] }>(
      `/ai/conversations/${id}`,
    )
  chat = (payload: ChatInput) =>
    this.auth.api<ChatResult>('/ai/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  documents = (offset = 0) =>
    this.auth.api<Policy[]>(`/ai/documents?offset=${offset}`)
  upload = (file: File, audience: string) => {
    const body = new FormData()
    body.append('file', file)
    body.append('audience', audience)
    return this.auth.api<Policy>('/ai/documents', { method: 'POST', body })
  }
  reindex = (id: string) =>
    this.auth.api<Policy>(`/ai/documents/${id}/reindex`, { method: 'POST' })
  activate = (id: string, active: boolean) =>
    this.auth.api<Policy>(`/ai/documents/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_active: active }),
    })
}
