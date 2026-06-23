import { apiFetch } from '../lib/apiClient'
import type { ProductTestFile } from '../types/api'

export function listRegisteredTestFiles(productName: string): Promise<ProductTestFile[]> {
  return apiFetch<ProductTestFile[]>('/test-files', { query: { product_name: productName } })
}

export function addTestFiles(
  productName: string,
  relPaths: string[],
): Promise<ProductTestFile[]> {
  return apiFetch<ProductTestFile[]>('/test-files', {
    method: 'POST',
    body: { product_name: productName, rel_paths: relPaths },
  })
}

export function removeTestFiles(
  productName: string,
  relPaths: string[],
): Promise<{ removed: number }> {
  return apiFetch<{ removed: number }>('/test-files', {
    method: 'DELETE',
    body: { product_name: productName, rel_paths: relPaths },
  })
}

/**
 * 선택한 파일들을 서버에서 zip으로 묶어 받아 브라우저 다운로드를 트리거한다.
 * apiFetch는 JSON 파싱이라 blob을 다룰 수 없어 fetch를 직접 쓴다.
 */
export async function downloadTestFilesZip(
  productName: string,
  productId: number,
  relPaths: string[],
): Promise<void> {
  const res = await fetch('/api/test-files/download', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ product_id: productId, rel_paths: relPaths }),
  })
  if (!res.ok) {
    throw new Error(`download failed: ${res.status}`)
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${productName}_tests.zip`
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}
