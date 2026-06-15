import { apiFetch } from '../lib/apiClient'
import type { CompileCheckResult, TreeEntry } from '../types/api'

interface TreeResponse {
  entries: TreeEntry[]
}

export function getTree(productId: number, path = ''): Promise<TreeEntry[]> {
  return apiFetch<TreeResponse>(`/products/${productId}/tree`, { query: { path } }).then(
    (response) => response.entries,
  )
}

export function compileCheck(productId: number, files: string[]): Promise<CompileCheckResult> {
  return apiFetch<CompileCheckResult>(`/products/${productId}/compile-check`, {
    method: 'POST',
    body: { files },
  })
}
