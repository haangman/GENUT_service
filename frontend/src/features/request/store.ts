import { create } from 'zustand'
import { DEFAULT_PROJECT } from '../../lib/projects'
import type { CompileCheckResult, Project, TestGenerationMode } from '../../types/api'

interface RequestBuilderState {
  // 프로젝트 필터. 변경 시 선택된 프로덕트/파일이 함께 리셋된다.
  project: Project
  productId: number | null
  mode: TestGenerationMode
  selected: string[]
  functionName: string
  // compile-check 결과 (M4). selected 변경 시 stale 처리.
  compileResult: CompileCheckResult | null
  compileStale: boolean
  // 마지막으로 접수된 job id. 제출 후 초기 화면에서 접수 안내를 표시하기 위해 보존한다.
  lastSubmittedJobId: number | null

  setProject: (project: Project) => void
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
  project: DEFAULT_PROJECT,
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

  // 프로젝트 변경: 이전 프로젝트에서 고른 프로덕트/파일은 무효이므로 함께 리셋한다.
  setProject: (project) =>
    set({
      project,
      productId: null,
      mode: 'cpp',
      selected: [],
      compileResult: null,
      compileStale: false,
      lastSubmittedJobId: null,
    }),

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
  // 프로젝트는 필터 선호이므로 유지한다(같은 프로젝트에 이어서 요청하는 흐름).
  completeSubmission: (jobId) =>
    set((state) => ({ ...INITIAL, project: state.project, lastSubmittedJobId: jobId })),

  reset: () => set((state) => ({ ...INITIAL, project: state.project })),
}))
