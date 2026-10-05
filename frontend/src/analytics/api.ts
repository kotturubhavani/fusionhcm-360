import type { AuthClient } from '../auth'
export interface FieldMeta {
  key: string
  label: string
  type: string
  operators: string[]
}
export type Metadata = Record<string, FieldMeta[]>
export interface Filter {
  field: string
  operator: string
  value: string | string[]
}
export interface Definition {
  id: string
  code: string
  name: string
  description?: string | null
  domain?: string
  selected_columns?: string[]
  filters?: Filter[]
  sort_definition?: { field: string; direction: string }[]
  is_active: boolean
  extract_type?: string
  output_format?: string
  configuration?: { filters: Filter[] }
  last_successful_run_at?: string | null
}
export interface Run {
  id: string
  status: string
  row_count: number
  started_at: string
  completed_at: string | null
  error_message: string | null
  definition_snapshot: Record<string, unknown>
  mode?: string
  watermark_from?: string | null
  watermark_to?: string
  output_filename?: string | null
}
export interface Results {
  columns: string[]
  total: number
  rows: Record<string, unknown>[]
}
export class AnalyticsClient {
  private auth: AuthClient
  constructor(auth: AuthClient) {
    this.auth = auth
  }
  metadata = () => this.auth.api<Metadata>('/reports/metadata')
  list = (extract: boolean, offset = 0) =>
    this.auth.api<Definition[]>(
      `${extract ? '/extracts/definitions' : '/reports'}?offset=${offset}&limit=50`,
    )
  definition = (extract: boolean, id: string) =>
    this.auth.api<Definition>(
      `${extract ? '/extracts/definitions' : '/reports'}/${id}`,
    )
  save = (extract: boolean, payload: unknown, id?: string) =>
    this.auth.api<Definition>(
      `${extract ? '/extracts/definitions' : '/reports'}${id ? '/' + id : ''}`,
      {
        method: id ? 'PATCH' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      },
    )
  run = (extract: boolean, id: string, payload: unknown) =>
    this.auth.api<Run>(
      `${extract ? '/extracts/definitions' : '/reports'}/${id}/run`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      },
    )
  runs = (extract: boolean, offset = 0) =>
    this.auth.api<Run[]>(
      `${extract ? '/extracts' : '/reports'}/runs?offset=${offset}&limit=50`,
    )
  result = (extract: boolean, id: string) =>
    this.auth.api<Run>(`${extract ? '/extracts' : '/reports'}/runs/${id}`)
  rows = (id: string, offset = 0) =>
    this.auth.api<Results>(
      `/reports/runs/${id}/results?offset=${offset}&limit=100`,
    )
  download = (extract: boolean, id: string, format = 'csv') =>
    this.auth.api<Blob>(
      extract
        ? `/extracts/runs/${id}/download`
        : `/reports/runs/${id}/export.${format}`,
      {},
      'blob',
    )
}
export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}
