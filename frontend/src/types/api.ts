// 백엔드 API 타입. (추후 openapi-typescript 생성으로 대체 가능)

export type TestGenerationMode = 'c' | 'cpp' | 'kunit'

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface Patch {
  id: number
  name: string
  content: string
  order_index: number
}

export interface PatchIn {
  name: string
  content: string
  order_index: number
}

export interface Product {
  id: number
  name: string
  product_code: string
  git_url: string
  git_ref: string
  compile_db_rel: string
  out_tests_rel: string
  cmake_configure_cmd: string
  cmake_build_cmd: string
  test_run_cmd: string
  test_generation_mode: TestGenerationMode
  active: boolean
  patches: Patch[]
}

export interface ProductCreate {
  name: string
  product_code: string
  git_url: string
  git_ref: string
  compile_db_rel: string
  out_tests_rel: string
  cmake_configure_cmd: string
  cmake_build_cmd: string
  test_run_cmd: string
  test_generation_mode: TestGenerationMode
  patches: PatchIn[]
}
