import type { AuthClient } from '../auth'
export interface Definition {
  id: string
  code: string
  name: string
  legal_employer_id: string
  country_code: string
  currency: string
  frequency: 'MONTHLY'
  is_active: boolean
  retirement_rate: string
  withholding_rate: string
  standard_allowance: string
}
export interface Period {
  id: string
  payroll_definition_id: string
  period_name: string
  period_start: string
  period_end: string
  payment_date: string
  status: 'OPEN' | 'PROCESSING' | 'PROCESSED'
}
export interface Run {
  id: string
  pay_period_id: string
  run_number: number
  status: 'PROCESSING' | 'COMPLETED' | 'FAILED'
  started_at: string
  completed_at: string | null
  failure_reason: string | null
  excluded_assignment_count: number
  unpaid_day_count: number
  rules_snapshot: Record<string, unknown>
}
export interface Result {
  id: string
  payroll_run_id: string
  person_number: string
  worker_name: string
  assignment_number: string
  gross_pay: string
  total_deductions: string
  net_pay: string
  currency: string
  eligible_days: number
  period_days: number
  calculation_snapshot: {
    from: string
    to: string
    days: number
    annual_base_salary: string
    currency: string
    status: string
  }[]
}
export interface ResultDetail {
  result: Result
  lines: {
    id: string
    line_type: 'EARNING' | 'DEDUCTION'
    code: string
    name: string
    amount: string
  }[]
  period: Period
  definition_name: string
}
export interface RunDetail {
  run: Run
  period: Period
  definition_name: string
  currency: string
  result_count: number
  gross_pay: string
  total_deductions: string
  net_pay: string
}
export class PayrollClient {
  private auth: AuthClient
  constructor(auth: AuthClient) {
    this.auth = auth
  }
  request<T>(path: string, body?: unknown) {
    return this.auth.api<T>(
      '/payroll' + path,
      body === undefined
        ? {}
        : {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
          },
    )
  }
  async all<T>(path: string) {
    const rows: T[] = []
    for (let offset = 0; ; offset += 100) {
      const page = await this.request<T[]>(
        `${path}${path.includes('?') ? '&' : '?'}offset=${offset}&limit=100`,
      )
      rows.push(...page)
      if (page.length < 100) return rows
    }
  }
  definitions() {
    return this.all<Definition>('/definitions')
  }
  periods() {
    return this.all<Period>('/periods')
  }
  runs() {
    return this.all<Run>('/runs')
  }
  process(id: string) {
    return this.request<Run>(`/periods/${id}/process`, {})
  }
}
