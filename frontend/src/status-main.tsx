import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider, createBrowserRouter, Navigate } from 'react-router-dom'
import { StatusLayout } from './app/StatusLayout'
import { TestStatusPage } from './features/test-status/TestStatusPage'
import { TestFileViewPage } from './features/test-status/TestFileViewPage'
import { queryClient } from './lib/queryClient'
import { LangProvider } from './lib/i18n'
import './index.css'

// 독립 테스트 현황 앱(status.html 엔트리). 라우트 경로는 메인 앱과 동일하게 유지해
// TestStatusPage의 뷰어 링크(/test-status/view?…)를 무수정 재사용한다.
const router = createBrowserRouter([
  {
    path: '/',
    element: <StatusLayout />,
    children: [
      { index: true, element: <Navigate to="/test-status" replace /> },
      { path: 'test-status', element: <TestStatusPage /> },
      { path: 'test-status/view', element: <TestFileViewPage /> },
      { path: '*', element: <Navigate to="/test-status" replace /> },
    ],
  },
])

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <LangProvider>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </LangProvider>
  </React.StrictMode>,
)
