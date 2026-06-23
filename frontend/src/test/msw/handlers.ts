import { http, HttpResponse } from 'msw'

// 기본(happy-path) 핸들러. 개별 테스트에서 server.use(...)로 덮어쓴다.
export const handlers = [
  http.get('/api/health', () => HttpResponse.json({ status: 'ok' })),
  http.get('/api/products', () =>
    HttpResponse.json({ items: [], total: 0, page: 1, page_size: 50 }),
  ),
  http.get('/api/genuts', () =>
    HttpResponse.json({ items: [], total: 0, page: 1, page_size: 50 }),
  ),
  http.get('/api/jobs', () =>
    HttpResponse.json({ items: [], total: 0, page: 1, page_size: 50 }),
  ),
  http.get('/api/workers', () => HttpResponse.json([])),
  http.get('/api/queue', () => HttpResponse.json([])),
  http.get('/api/test-files', () => HttpResponse.json([])),
]
