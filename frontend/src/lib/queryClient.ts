import { QueryClient } from '@tanstack/react-query'

// 서버 상태 캐시. 폴링은 각 쿼리에서 refetchInterval로 개별 설정한다.
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      refetchOnWindowFocus: false,
    },
  },
})
