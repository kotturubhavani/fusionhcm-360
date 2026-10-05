import assert from 'node:assert/strict'
import { test } from 'node:test'
import { AuthClient } from './auth.ts'

const user = { id: '1', first_name: 'Test', last_name: 'User', email: 'test@example.com', roles: ['EMPLOYEE'] }
const json = (body, status = 200) => new Response(JSON.stringify(body), { status })

function mock(steps) {
  const original = globalThis.fetch
  globalThis.fetch = async (url, init) => {
    const next = steps.shift()
    assert.ok(next, `Unexpected request: ${url}`)
    assert.equal(url, `http://localhost:8000/auth${next.path}`)
    assert.equal(init.credentials, 'include')
    if (next.authorization) assert.equal(init.headers.Authorization, next.authorization)
    if (next.error) throw next.error
    return json(next.body ?? user, next.status ?? 200)
  }
  return () => { globalThis.fetch = original; assert.equal(steps.length, 0) }
}

test('login loads user; expired access token refreshes and retries; logout clears memory', async () => {
  const done = mock([
    { path: '/login', body: { access_token: 'old' } },
    { path: '/me', authorization: 'Bearer old' },
    { path: '/me', authorization: 'Bearer old', status: 401 },
    { path: '/refresh', body: { access_token: 'new' } },
    { path: '/me', authorization: 'Bearer new' },
    { path: '/logout', body: { message: 'Logged out' } },
    { path: '/refresh', status: 401 },
  ])
  try {
    const auth = new AuthClient('http://localhost:8000/')
    assert.deepEqual(await auth.login(user.email, 'password'), user)
    assert.deepEqual(await auth.me(), user)
    await auth.logout()
    await assert.rejects(auth.me(), { status: 401 })
  } finally { done() }
})

test('invalid credentials are actionable', async () => {
  const done = mock([{ path: '/login', status: 401 }])
  try {
    await assert.rejects(new AuthClient('http://localhost:8000').login(user.email, 'bad'), { message: 'Invalid email or password.' })
  } finally { done() }
})

test('failed refresh ends the session without a retry loop', async () => {
  const done = mock([
    { path: '/refresh', body: { access_token: 'old' } },
    { path: '/me', status: 401 },
    { path: '/refresh', status: 401 },
  ])
  try { await assert.rejects(new AuthClient('http://localhost:8000').me(), { status: 401 }) }
  finally { done() }
})

test('concurrent restores share one refresh request', async () => {
  const done = mock([
    { path: '/refresh', body: { access_token: 'new' } },
    { path: '/me', authorization: 'Bearer new' },
    { path: '/me', authorization: 'Bearer new' },
  ])
  try {
    const auth = new AuthClient('http://localhost:8000')
    assert.deepEqual(await Promise.all([auth.me(), auth.me()]), [user, user])
  } finally { done() }
})

test('network failure on logout still discards the access token', async () => {
  const done = mock([
    { path: '/login', body: { access_token: 'old' } },
    { path: '/me' },
    { path: '/logout', error: new Error('offline') },
    { path: '/refresh', status: 401 },
  ])
  try {
    const auth = new AuthClient('http://localhost:8000')
    await auth.login(user.email, 'password')
    await assert.rejects(auth.logout(), /Unable to connect/)
    await assert.rejects(auth.me(), { status: 401 })
  } finally { done() }
})
