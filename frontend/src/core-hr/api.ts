import { AuthClient } from '../auth'
import { resources } from './types'
import type {
  HireResult,
  References,
  Reference,
  Resource,
  Worker,
  Relationship,
} from './types'
export class CoreHrClient {
  private auth: AuthClient
  constructor(auth: AuthClient) {
    this.auth = auth
  }
  request<T>(path: string, method = 'GET', body?: unknown) {
    return this.auth.api<T>(`/core-hr${path}`, {
      method,
      ...(body === undefined
        ? {}
        : {
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
          }),
    })
  }
  async all<T>(path: string): Promise<T[]> {
    const rows: T[] = []
    for (let offset = 0; ; offset += 100) {
      const page = await this.request<T[]>(
        `${path}${path.includes('?') ? '&' : '?'}offset=${offset}&limit=100`,
      )
      rows.push(...page)
      if (page.length < 100) return rows
    }
  }
  workers(date: string) {
    return this.all<Worker>(`/workers?as_of=${date}`)
  }
  worker(id: string | undefined, date: string) {
    return this.request<Worker>(
      `${id ? `/workers/${encodeURIComponent(id)}` : '/me'}?as_of=${date}`,
    )
  }
  relationships(id: string) {
    return this.request<Relationship[]>(`/persons/${id}/work-relationships`)
  }
  async references(): Promise<References> {
    const entries = await Promise.all(
      (Object.keys(resources) as Resource[]).map(
        async (key) =>
          [key, await this.all<Reference>(`/reference/${key}`)] as const,
      ),
    )
    return Object.fromEntries(entries) as References
  }
  saveReference(resource: Resource, body: unknown, id?: string) {
    return this.request<Reference>(
      `/reference/${resource}${id ? `/${id}` : ''}`,
      id ? 'PATCH' : 'POST',
      body,
    )
  }
  hire(body: unknown, personId?: string) {
    return this.request<HireResult>(
      personId ? `/workers/${personId}/rehire` : '/workers/hire',
      'POST',
      body,
    )
  }
}
