import { apiFetch } from '../lib/apiClient'
import type { Page, Product, ProductCreate } from '../types/api'

export function listProducts(page = 1, pageSize = 50): Promise<Page<Product>> {
  return apiFetch<Page<Product>>('/products', { query: { page, page_size: pageSize } })
}

export function getProduct(id: number): Promise<Product> {
  return apiFetch<Product>(`/products/${id}`)
}

export function createProduct(data: ProductCreate): Promise<Product> {
  return apiFetch<Product>('/products', { method: 'POST', body: data })
}

export function deleteProduct(id: number): Promise<void> {
  return apiFetch<void>(`/products/${id}`, { method: 'DELETE' })
}
