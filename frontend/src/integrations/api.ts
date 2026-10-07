import type { AuthClient } from '../auth'
import type { Template } from '../imports/api'
export interface Config {
  auth_type: 'NONE' | 'BEARER_ENV'
  credential_env_key?: string | null
  as_of?: string | null
  legal_employer_code?: string | null
  business_unit_code?: string | null
  department_code?: string | null
  active_workers_only?: boolean
  payroll_definition_code?: string | null
  period_name?: string | null
  completed_run_number?: number | null
  fbp_plan_code?: string | null
}
export interface Definition {
  id: string
  code: string
  name: string
  description: string | null
  direction: 'INBOUND' | 'OUTBOUND'
  integration_type: string
  transport_type: 'FILE' | 'HTTP_REST'
  endpoint_url: string | null
  http_method: 'POST' | null
  output_format: 'JSON' | 'CSV'
  configuration: Config
  is_active: boolean
}
export type DefinitionInput = Omit<Definition, 'id'>
export interface Run {
  id: string
  integration_definition_id: string
  status: string
  retry_of_run_id: string | null
  retry_depth: number
  requested_by_user_id: string | null
  trigger_type: string
  request_key: string
  started_at: string
  completed_at: string | null
  records_read: number
  records_succeeded: number
  records_failed: number
  safe_error_message: string | null
  definition_snapshot: DefinitionInput
  request_metadata: Record<string, unknown> | null
  response_metadata: Record<string, unknown> | null
  output_filename: string | null
}
export interface Item {
  id: string
  sequence_number: number
  business_reference: string
  status: string
  response_status: number | null
  safe_error_message: string | null
}
export interface RunInput {
  request_key: string
  records?: Record<string, string>[]
  csv_content?: string
}
export class IntegrationsClient {
  private auth: AuthClient
  constructor(auth: AuthClient) {
    this.auth = auth
  }
  list = (offset = 0) =>
    this.auth.api<Definition[]>(`/integrations?offset=${offset}&limit=50`)
  definition = (id: string) => this.auth.api<Definition>(`/integrations/${id}`)
  private post = <T>(path: string, payload: unknown, method = 'POST') =>
    this.auth.api<T>(path, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  save = (payload: DefinitionInput, id?: string) =>
    this.post<Definition>(
      `/integrations${id ? '/' + id : ''}`,
      payload,
      id ? 'PATCH' : 'POST',
    )
  run = (id: string, payload: RunInput) =>
    this.post<Run>(`/integrations/${id}/run`, payload)
  runs = (offset = 0) =>
    this.auth.api<Run[]>(`/integrations/runs?offset=${offset}&limit=50`)
  result = (id: string) => this.auth.api<Run>(`/integrations/runs/${id}`)
  items = (id: string) =>
    this.auth.api<Item[]>(`/integrations/runs/${id}/items?limit=100`)
  retry = (id: string, key: string) =>
    this.post<Run>(`/integrations/runs/${id}/retry`, { request_key: key })
  download = (id: string) =>
    this.auth.api<Blob>(`/integrations/runs/${id}/download`, {}, 'blob')
  templates = () => this.auth.api<Template[]>('/imports/templates')
}
