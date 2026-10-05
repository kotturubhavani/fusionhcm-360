import type { AuthClient } from '../auth'
export interface ImportJob {
  id: string
  object_type: string
  original_filename: string
  status: string
  total_rows: number
  valid_rows: number
  invalid_rows: number
  processed_rows: number
  failed_rows: number
  created_at: string
  validated_at: string | null
  processed_at: string | null
  created_by_user_id: string | null
}
export interface ImportRow {
  id: string
  row_number: number
  status: string
  raw_data: Record<string, string>
  normalized_data: Record<string, unknown> | null
  error_code: string | null
  error_message: string | null
  created_record_reference: Record<string, string> | null
}
export interface Template {
  object_type: string
  columns: string[]
  required: string[]
}
export class ImportsClient {
  private auth: AuthClient
  constructor(auth: AuthClient) {
    this.auth = auth
  }
  templates = () => this.auth.api<Template[]>('/imports/templates')
  jobs = (offset = 0) =>
    this.auth.api<ImportJob[]>(`/imports?offset=${offset}&limit=50`)
  job = (id: string) => this.auth.api<ImportJob>(`/imports/${id}`)
  rows = (id: string, status = '', offset = 0) =>
    this.auth.api<ImportRow[]>(
      `/imports/${id}/rows?offset=${offset}&limit=100${status ? `&status=${status}` : ''}`,
    )
  upload = (kind: string, file: File) => {
    const body = new FormData()
    body.append('object_type', kind)
    body.append('file', file)
    return this.auth.api<ImportJob>('/imports', { method: 'POST', body })
  }
  action = (id: string, action: 'validate' | 'process') =>
    this.auth.api<ImportJob>(`/imports/${id}/${action}`, { method: 'POST' })
  template = (kind: string) =>
    this.auth.api<string>(`/imports/templates/${kind}`, {}, 'text')
  errors = (id: string) =>
    this.auth.api<string>(`/imports/${id}/errors.csv`, {}, 'text')
}
export function downloadCsv(content: string, name: string) {
  const url = URL.createObjectURL(
    new Blob([content], { type: 'text/csv;charset=utf-8' }),
  )
  const link = document.createElement('a')
  link.href = url
  link.download = name
  link.click()
  URL.revokeObjectURL(url)
}
