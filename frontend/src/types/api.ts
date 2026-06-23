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
  code_path: string | null
  patches: Patch[]
}

export interface Genut {
  id: number
  name: string
  repo_url: string
  repo_ref: string
  assure_repo_url: string | null
  ds_assist_send_system_name: string
  ds_assist_user_id: string | null
  max_attempts: number
  run_command: string
  enabled: boolean
  code_path: string | null
  worker_status: string
  current_job_id: number | null
}

export interface GenutCreate {
  name: string
  repo_url: string
  repo_ref: string
  assure_repo_url?: string
  ds_assist_credential_key: string
  ds_assist_send_system_name: string
  ds_assist_user_id?: string
  max_attempts: number
  run_command: string
  enabled: boolean
  code_path?: string
}

export interface Worker {
  id: number
  name: string
  worker_status: string
  current_job_id: number | null
  enabled: boolean
}

export interface QueueItem {
  job_id: number
  product_id: number
  submitted_at: string
  waiting_on_product: boolean
}

export interface Job {
  id: number
  product_id: number
  genut_instance_id: number | null
  status: string
  function_name: string | null
  file_list: string[]
  excluded_files: string[]
  attempt: number
  submitted_at: string
  started_at: string | null
  finished_at: string | null
  result_summary: string | null
  error: string | null
}

export interface JobEvent {
  id: number
  job_id: number
  ts: string
  level: string
  phase: string | null
  message: string
  payload: unknown
}

export interface JobCreate {
  product_id: number
  files: string[]
  function_name?: string
}

export type TreeEntryType = 'file' | 'dir'

export interface TreeEntry {
  name: string
  path: string
  type: TreeEntryType
}

export interface CompileCheckResult {
  included: string[]
  excluded: string[]
}

export interface ProductTestFile {
  id: number
  product_name: string
  rel_path: string
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
  code_path?: string
  patches: PatchIn[]
}
