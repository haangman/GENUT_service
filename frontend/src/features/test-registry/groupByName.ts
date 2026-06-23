import type { Product, TestGenerationMode } from '../../types/api'

export interface ProductGroup {
  name: string
  // 같은 이름은 코드를 공유하므로 대표 1개(최저 id)의 체크아웃을 기준으로 본다.
  representativeId: number
  mode: TestGenerationMode
}

/**
 * 프로덕트를 이름 단위로 그룹핑한다. 같은 이름이 여러 번 등록돼 있어도 1개로 보이며,
 * 대표 id는 가장 낮은 id다(결정론적). 이름 오름차순 정렬.
 */
export function groupProductsByName(products: Product[]): ProductGroup[] {
  const byName = new Map<string, ProductGroup>()
  for (const product of products) {
    const existing = byName.get(product.name)
    if (!existing) {
      byName.set(product.name, {
        name: product.name,
        representativeId: product.id,
        mode: product.test_generation_mode,
      })
    } else if (product.id < existing.representativeId) {
      existing.representativeId = product.id
      existing.mode = product.test_generation_mode
    }
  }
  return Array.from(byName.values()).sort((a, b) => a.name.localeCompare(b.name))
}
