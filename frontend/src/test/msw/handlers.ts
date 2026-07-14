import { http, HttpResponse } from 'msw'

// 기본(happy-path) 핸들러. 개별 테스트에서 server.use(...)로 덮어쓴다.
export const handlers = [
  http.get('/api/health', () => HttpResponse.json({ status: 'ok' })),
  http.get('/api/products', () =>
    HttpResponse.json({ items: [], total: 0, page: 1, page_size: 50 }),
  ),
  http.post('/api/products/target-files', () => HttpResponse.json({ files: [] })),
  http.post('/api/products/pull-code', () =>
    HttpResponse.json({
      path: 'C:/checkout',
      detail: '클론 완료',
      log: '최근 커밋:\nabc1234 2026-07-14 tester init',
    }),
  ),
  http.post('/api/products/run-command', () =>
    HttpResponse.json({ exit_code: 0, output: 'ok', duration_seconds: 0.1 }),
  ),
  http.get('/api/genuts', () =>
    HttpResponse.json({ items: [], total: 0, page: 1, page_size: 50 }),
  ),
  http.get('/api/jobs', () =>
    HttpResponse.json({ items: [], total: 0, page: 1, page_size: 50 }),
  ),
  http.get('/api/jobs/auto-history', () => HttpResponse.json([])),
  http.get('/api/workers', () => HttpResponse.json([])),
  http.get('/api/queue', () => HttpResponse.json([])),
  http.get('/api/test-status', () => HttpResponse.json([])),
  http.get('/api/test-status/detail', () => HttpResponse.json([])),
  http.get('/api/test-status/file', () => HttpResponse.json({ path: '', content: '' })),
  http.get('/api/terminal/info', () => HttpResponse.json({ available: true, reason: '' })),
]
