import type { ReactElement } from 'react'
import { render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { LangProvider } from '../lib/i18n'

interface RenderOptions {
  route?: string
}

// LangProvider + QueryClientProvider + MemoryRouter로 감싸 컴포넌트를 렌더한다.
// (언어 기본값은 한국어 — 기존 테스트의 한국어 단언이 그대로 유효하다)
export function renderWithProviders(ui: ReactElement, { route = '/' }: RenderOptions = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <LangProvider>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
      </QueryClientProvider>
    </LangProvider>,
  )
}
