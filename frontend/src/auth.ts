export interface User {
  id: string
  first_name: string
  last_name: string
  email: string
  roles: string[]
}

export class AuthError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

// Access tokens stay in memory. Only the browser manages the HttpOnly cookie.
export class AuthClient {
  private token: string | null = null
  private generation = 0
  private pendingRefresh: Promise<void> | null = null
  private base: string

  constructor(base: string) { this.base = base.replace(/\/$/, '') }

  private async request(path: string, init: RequestInit = {}) {
    if (!this.base) throw new Error('VITE_API_BASE_URL is not configured.')
    let response: Response
    try {
      response = await fetch(`${this.base}/auth${path}`, { ...init, credentials: 'include' })
    } catch {
      throw new Error('Unable to connect. Check your connection and try again.')
    }
    if (!response.ok) {
      throw new AuthError(response.status === 401
        ? 'Your session has expired. Please sign in again.'
        : 'The request failed. Please try again.', response.status)
    }
    return response.json()
  }

  refresh(): Promise<void> {
    if (this.pendingRefresh) return this.pendingRefresh
    const generation = this.generation
    const pending = this.request('/refresh', { method: 'POST' }).then(data => {
      if (generation === this.generation) this.token = data.access_token
    }).catch(error => {
      if (generation === this.generation) this.token = null
      throw error
    }).finally(() => {
      if (this.pendingRefresh === pending) this.pendingRefresh = null
    })
    this.pendingRefresh = pending
    return pending
  }

  async me(): Promise<User> {
    if (!this.token) await this.refresh()
    try {
      return await this.request('/me', { headers: { Authorization: `Bearer ${this.token}` } })
    } catch (error) {
      if (!(error instanceof AuthError) || error.status !== 401) throw error
      await this.refresh()
      try {
        return await this.request('/me', { headers: { Authorization: `Bearer ${this.token}` } })
      } catch (retryError) {
        this.token = null
        throw retryError
      }
    }
  }

  async login(email: string, password: string): Promise<User> {
    this.generation++
    this.token = null
    this.pendingRefresh = null
    try {
      const data = await this.request('/login', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      this.token = data.access_token
    } catch (error) {
      if (error instanceof AuthError && error.status === 401) throw new AuthError('Invalid email or password.', 401)
      throw error
    }
    return this.me()
  }

  async logout(): Promise<void> {
    this.generation++
    this.token = null
    this.pendingRefresh = null
    await this.request('/logout', { method: 'POST' })
  }
}
