import { createBrowserRouter, Navigate } from 'react-router-dom'
import { AppLayout } from './app/AppLayout'
import { RequestPage } from './features/request/RequestPage'
import { ProductsPage } from './features/products/ProductsPage'
import { GenutsPage } from './features/genuts/GenutsPage'
import { ManualJobsPage } from './features/jobs/ManualJobsPage'
import { AutoJobsPage } from './features/auto-jobs/AutoJobsPage'
import { TestStatusPage } from './features/test-status/TestStatusPage'
import { TestFileViewPage } from './features/test-status/TestFileViewPage'
import { TerminalPage } from './features/terminal/TerminalPage'

export const routes = [
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <Navigate to="/request" replace /> },
      { path: 'request', element: <RequestPage /> },
      { path: 'products', element: <ProductsPage /> },
      { path: 'genuts', element: <GenutsPage /> },
      { path: 'manual-jobs', element: <ManualJobsPage /> },
      // 구 경로 호환: 모니터링 페이지는 '수동 실행 이력'으로 개편됐다(북마크 보존)
      { path: 'monitoring', element: <Navigate to="/manual-jobs" replace /> },
      { path: 'auto-jobs', element: <AutoJobsPage /> },
      { path: 'test-status', element: <TestStatusPage /> },
      { path: 'test-status/view', element: <TestFileViewPage /> },
      { path: 'terminal', element: <TerminalPage /> },
    ],
  },
]

export const router = createBrowserRouter(routes)
