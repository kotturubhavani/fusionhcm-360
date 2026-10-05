import type { AuthClient } from '../auth'
export interface Plan {
  id: string
  code: string
  name: string
  legal_employer_id: string
  plan_year: number
  effective_from: string
  effective_to: string
  currency: string
  budget_rate: string
  status: 'DRAFT' | 'OPEN' | 'CLOSED'
  is_active: boolean
  budgets_generated_at: string | null
}
export interface Component {
  id: string
  plan_id: string
  code: string
  name: string
  description: string | null
  component_type: 'ALLOWANCE' | 'BENEFIT' | 'REIMBURSEMENT'
  min_amount: string
  max_amount: string
  default_amount: string
  display_order: number
  is_active: boolean
}
export interface Election {
  component_id: string
  amount: string
}
export interface Budget {
  id: string
  plan_id: string
  person_id: string
  assignment_id: string
  person_number: string
  worker_name: string
  assignment_number: string
  annual_base_salary: string
  budget_rate: string
  eligible_budget: string
  currency: string
  status: 'OPEN' | 'SUBMITTED' | 'FINALIZED'
  revision: number
  allocated: string
  remaining: string
  elections: Election[]
  submitted_at: string | null
  finalized_at: string | null
}
export interface PlanView {
  plan: Plan
  components: Component[]
  budgets: Budget[]
}
export interface Summary {
  workers: number
  budgets: number
  open: number
  submitted: number
  finalized: number
  eligible_budget: string
  allocated: string
  remaining: string
  currency: string
}
export class FbpClient {
  private auth: AuthClient
  constructor(auth: AuthClient) {
    this.auth = auth
  }
  request<T>(path: string, method = 'GET', body?: unknown) {
    return this.auth.api<T>('/fbp' + path, {
      method,
      ...(body === undefined
        ? {}
        : {
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
          }),
    })
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
}
// Integer cents keep display arithmetic exact; server validates every write.
export function cents(value: string): bigint | null {
  if (!/^\d{1,12}(\.\d{1,2})?$/.test(value)) return null
  const [whole, fraction = ''] = value.split('.')
  return BigInt(whole) * 100n + BigInt(fraction.padEnd(2, '0'))
}
export function decimal(value: bigint) {
  const sign = value < 0n ? '-' : ''
  const abs = value < 0n ? -value : value
  return `${sign}${abs / 100n}.${String(abs % 100n).padStart(2, '0')}`
}
