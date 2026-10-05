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

  private onSessionExpired?: () => void
  setSessionExpiredHandler(handler?: () => void) {
    this.onSessionExpired = handler
  }
  constructor(base: string) {
    this.base = base.replace(/\/$/, '')
  }

  private async request(path: string, init: RequestInit = {}) {
    if (!this.base) throw new Error('VITE_API_BASE_URL is not configured.')
    let response: Response
    try {
      response = await fetch(`${this.base}${path}`, {
        ...init,
        credentials: 'include',
      })
    } catch {
      throw new Error('Unable to connect. Check your connection and try again.')
    }
    if (!response.ok) {
      const body = await response.json().catch(() => ({}))
      const detail = body.detail
      const message =
        response.status >= 500
          ? 'The service could not complete this request. Please try again.'
          : typeof detail === 'string'
            ? detail
            : Array.isArray(detail)
              ? detail
                  .map(
                    (item: { loc: string[]; msg: string }) =>
                      `${item.loc.filter((part) => part !== 'body').join(' / ')}: ${item.msg}`,
                  )
                  .join('; ')
              : 'The request failed. Please try again.'
      throw new AuthError(
        response.status === 401
          ? 'Your session has expired. Please sign in again.'
          : message,
        response.status,
      )
    }
    return response.json()
  }

  refresh(): Promise<void> {
    if (this.pendingRefresh) return this.pendingRefresh
    const generation = this.generation
    const pending = this.request('/auth/refresh', { method: 'POST' })
      .then((data) => {
        if (generation === this.generation) this.token = data.access_token
      })
      .catch((error) => {
        if (generation === this.generation) this.token = null
        throw error
      })
      .finally(() => {
        if (this.pendingRefresh === pending) this.pendingRefresh = null
      })
    this.pendingRefresh = pending
    return pending
  }

  async me(): Promise<User> {
    return this.api<User>('/auth/me')
  }

  async api<T>(path: string, init: RequestInit = {}): Promise<T> {
    const generation = this.generation
    const send = () =>
      this.request(path, {
        ...init,
        headers: {
          ...Object.fromEntries(new Headers(init.headers)),
          Authorization: `Bearer ${this.token}`,
        },
      })
    try {
      if (!this.token) await this.refresh()
      if (generation !== this.generation)
        throw new AuthError('Session changed. Please try again.', 401)
      const usedToken = this.token
      let result: T
      try {
        result = await send()
      } catch (error) {
        if (!(error instanceof AuthError) || error.status !== 401) throw error
        if (generation !== this.generation) throw error
        if (usedToken === this.token) await this.refresh()
        if (generation !== this.generation) throw error
        result = await send()
      }
      if (generation !== this.generation)
        throw new AuthError('Session changed. Please try again.', 401)
      return result
    } catch (error) {
      if (
        generation === this.generation &&
        error instanceof AuthError &&
        error.status === 401
      ) {
        this.token = null
        this.onSessionExpired?.()
      }
      throw error
    }
  }

  async login(email: string, password: string): Promise<User> {
    const generation = ++this.generation
    this.token = null
    this.pendingRefresh = null
    try {
      const data = await this.request('/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      if (generation !== this.generation)
        throw new AuthError('Session changed. Please try again.', 401)
      this.token = data.access_token
    } catch (error) {
      if (error instanceof AuthError && error.status === 401)
        throw new AuthError('Invalid email or password.', 401)
      throw error
    }
    return this.me()
  }

  async logout(): Promise<void> {
    this.generation++
    this.token = null
    this.pendingRefresh = null
    await this.request('/auth/logout', { method: 'POST' })
  }
}
