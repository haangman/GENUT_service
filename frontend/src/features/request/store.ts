import { create } from 'zustand'
import type { CompileCheckResult, TestGenerationMode } from '../../types/api'

interface RequestBuilderState {
  productId: number | null
  mode: TestGenerationMode
  selected: string[]
  functionName: string
  // compile-check 결과 (M4). selected 변경 시 stale 처리.
  compileResult: CompileCheckResult | null
  compileStale: boolean
  // 마지막으로 접수된 job id. 제출 후 초기 화면에서 접수 안내를 표시하기 위해 보존한다.
  lastSubmittedJobId: number | null

  setProduct: (id: number, mode: TestGenerationMode) => void
  toggleFile: (path: string) => void
  addPaths: (paths: string[]) => void
  removeFile: (path: string) => void
  setFunctionName: (name: string) => void
  setCompileResult: (result: CompileCheckResult) => void
  completeSubmission: (jobId: number) => void
  reset: () => void
}

const INITIAL = {
  productId: null,
  mode: 'cpp' as TestGenerationMode,
  selected: [] as string[],
  functionName: '',
  compileResult: null as CompileCheckResult | null,
  compileStale: false,
  lastSubmittedJobId: null as number | null,
}

export const useRequestBuilder = create<RequestBuilderState>((set) => ({
  ...INITIAL,

  setProduct: (id, mode) =>
    set({
      productId: id,
      mode,
      selected: [],
      compileResult: null,
      compileStale: false,
      // 새 요청을 시작하면 이전 접수 안내는 숨긴다.
      lastSubmittedJobId: null,
    }),

  toggleFile: (path) =>
    set((state) => {
      const exists = state.selected.includes(path)
      return {
        selected: exists
          ? state.selected.filter((p) => p !== path)
          : [...state.selected, path],
        compileStale: true,
      }
    }),

  addPaths: (paths) =>
    set((state) => {
      const merged = new Set(state.selected)
      for (const p of paths) merged.add(p)
      return { selected: Array.from(merged), compileStale: true }
    }),

  removeFile: (path) =>
    set((state) => ({
      selected: state.selected.filter((p) => p !== path),
      compileStale: true,
    })),

  setFunctionName: (name) => set({ functionName: name }),

  setCompileResult: (result) => set({ compileResult: result, compileStale: false }),

  // 제출 성공: 빌더를 초기 상태로 되돌리되, 접수된 job id는 안내용으로 보존한다.
  completeSubmission: (jobId) => set({ ...INITIAL, lastSubmittedJobId: jobId }),

  reset: () => set({ ...INITIAL }),
}))
