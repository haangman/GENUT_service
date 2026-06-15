import { createBrowserRouter, Navigate } from 'react-router-dom'
import { AppLayout } from './app/AppLayout'
import { RequestPage } from './features/request/RequestPage'
import { ProductsPage } from './features/products/ProductsPage'
import { GenutsPage } from './features/genuts/GenutsPage'
import { MonitoringPage } from './features/workers/MonitoringPage'

export const routes = [
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <Navigate to="/request" replace /> },
      { path: 'request', element: <RequestPage /> },
      { path: 'products', element: <ProductsPage /> },
      { path: 'genuts', element: <GenutsPage /> },
      { path: 'monitoring', element: <MonitoringPage /> },
    ],
  },
]

export const router = createBrowserRouter(routes)
