import { createBrowserRouter, Navigate } from 'react-router-dom'
import { AppLayout } from './app/AppLayout'
import { RequestPage } from './features/request/RequestPage'
import { ProductsPage } from './features/products/ProductsPage'
import { GenutsPage } from './features/genuts/GenutsPage'
import { ManualJobsPage } from './features/jobs/ManualJobsPage'
import { AutoJobsPage } from './features/auto-jobs/AutoJobsPage'
import { TestStatusPage } from './features/test-status/TestStatusPage'
import { TestFileViewPage } from './features/test-status/TestFileViewPage'

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
      // 터미널 UI는 AppLayout이 항상 마운트한다(라우트 전환에도 세션 유지).
      // 이 라우트는 경로 매칭·네비 활성화용이며 Outlet은 비어 있다.
      { path: 'terminal', element: <></> },
    ],
  },
]

export const router = createBrowserRouter(routes)
