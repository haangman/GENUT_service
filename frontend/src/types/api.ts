// 백엔드 API 타입. (추후 openapi-typescript 생성으로 대체 가능)

// 프로덕트가 속한 상위 프로젝트. 선택지 목록은 lib/projects.ts의 PROJECTS.
export type Project = 'Ulysses' | 'Thetis'

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
  project: Project
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
  exclude_globs: string[]
  auto_run: boolean
  auto_interval_seconds: number | null
  auto_file_list: string[]
  cmake_template: string | null
  patches: Patch[]
}

// GENUT가 사용할 LLM 모델 (.env의 LLM_MODEL 값)
export type LlmModel = 'gptOss' | 'SSCR_SE'

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
  llm_model: LlmModel
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
  llm_model?: LlmModel
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
  origin: JobOrigin
}

// 실행 경로: genut(워커 실행) | auto_scan(누락 스캔) | auto_diff(변경 감지)
export type JobKind = 'genut' | 'auto_scan' | 'auto_diff'
// 생성 주체: manual(수동 제출) | auto(auto 모드 주기 실행)
export type JobOrigin = 'manual' | 'auto'

export interface Job {
  id: number
  product_id: number
  // 대상 프로덕트 이름 — 이력 화면 표시용(id와 함께 보여준다)
  product_name: string | null
  genut_instance_id: number | null
  // 배정된 GENUT 인스턴스 이름(미배정이면 null) — 이력 화면 표시용
  genut_name: string | null
  status: string
  kind: JobKind
  origin: JobOrigin
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

// GET /api/jobs/auto-history 응답: auto 프로덕트별 최근 job 그룹
export interface AutoHistoryGroup {
  product_id: number
  product_name: string
  product_code: string
  auto_interval_seconds: number | null
  total: number
  jobs: Job[]
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

export interface ProductCreate {
  project: Project
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
  exclude_globs: string[]
  auto_run?: boolean
  auto_interval_seconds?: number | null
  auto_file_list?: string[]
  cmake_template?: string | null
  patches: PatchIn[]
}

export interface TargetFileItem {
  path: string
  excluded_by_pattern: boolean
}

export interface TargetFilesResponse {
  files: TargetFileItem[]
}

// 테스트 현황: 대상 파일 1건과 그에 매칭된 테스트 파일들
export interface TestFileInfo {
  name: string
  path: string
  product_codes: string[]
  log_path: string | null
  case_count: number | null
}

export interface TargetFileStatus {
  name: string
  path: string
  product_codes: string[]
  test_count: number
  test_files: TestFileInfo[]
  case_count: number
  fail_count: number
  failed_test_files: TestFileInfo[]
}

export interface NameTestSummary {
  project: Project
  name: string
  product_codes: string[]
  test_generation_mode: TestGenerationMode
  target_file_count: number
  total_test_count: number
  total_case_count: number
  total_fail_count: number
  // 스냅샷 생성 시각(스냅샷 응답일 때만; 실시간 폴백 스캔이면 null/미존재)
  generated_at?: string | null
}

export interface FileContent {
  path: string
  content: string
}
