import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../test/msw/server'
import { apiFetch, ApiError } from './apiClient'

describe('apiFetch', () => {
  it('returns parsed JSON on success', async () => {
    const data = await apiFetch<{ status: string }>('/health')
    expect(data).toEqual({ status: 'ok' })
  })

  it('throws ApiError on non-2xx', async () => {
    server.use(http.get('/api/missing', () => new HttpResponse(null, { status: 404 })))
    await expect(apiFetch('/missing')).rejects.toBeInstanceOf(ApiError)
  })

  it('appends defined query params and drops undefined ones', async () => {
    let seen: URLSearchParams | null = null
    server.use(
      http.get('/api/echo', ({ request }) => {
        seen = new URL(request.url).searchParams
        return HttpResponse.json({ ok: true })
      }),
    )
    await apiFetch('/echo', { query: { q: 'hello', skip: undefined } })
    expect(seen!.get('q')).toBe('hello')
    expect(seen!.has('skip')).toBe(false)
  })
})
