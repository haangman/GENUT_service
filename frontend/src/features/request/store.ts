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

  setProduct: (id: number, mode: TestGenerationMode) => void
  toggleFile: (path: string) => void
  addPaths: (paths: string[]) => void
  removeFile: (path: string) => void
  setFunctionName: (name: string) => void
  setCompileResult: (result: CompileCheckResult) => void
  reset: () => void
}

export const useRequestBuilder = create<RequestBuilderState>((set) => ({
  productId: null,
  mode: 'cpp',
  selected: [],
  functionName: '',
  compileResult: null,
  compileStale: false,

  setProduct: (id, mode) =>
    set({
      productId: id,
      mode,
      selected: [],
      compileResult: null,
      compileStale: false,
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

  reset: () =>
    set({
      productId: null,
      mode: 'cpp',
      selected: [],
      functionName: '',
      compileResult: null,
      compileStale: false,
    }),
}))
