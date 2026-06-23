import { describe, it, expect } from 'vitest'
import { groupProductsByName } from './groupByName'
import type { Product } from '../../types/api'

function product(id: number, name: string): Product {
  return {
    id,
    name,
    product_code: `${name}-${id}`,
    git_url: 'u',
    git_ref: 'main',
    compile_db_rel: 'build',
    out_tests_rel: 'tests/generated',
    cmake_configure_cmd: 'c',
    cmake_build_cmd: 'b',
    test_run_cmd: 'r',
    test_generation_mode: 'cpp',
    active: true,
    code_path: null,
    patches: [],
  }
}

describe('groupProductsByName', () => {
  it('collapses same-name products into one with the lowest id as representative', () => {
    const groups = groupProductsByName([product(3, 'AA'), product(1, 'AA'), product(2, 'BB')])
    expect(groups.map((g) => g.name)).toEqual(['AA', 'BB'])
    expect(groups.find((g) => g.name === 'AA')?.representativeId).toBe(1)
    expect(groups.find((g) => g.name === 'BB')?.representativeId).toBe(2)
  })

  it('returns empty for no products', () => {
    expect(groupProductsByName([])).toEqual([])
  })
})
