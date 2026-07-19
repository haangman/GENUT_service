import { z } from 'zod'

// 자동 실행 모드 기본 CMakeLists 양식2. placeholder `filename`은 저장 시 파일 stem으로 치환된다.
// JS 템플릿 리터럴이라 CMake의 ${...}는 \$로 이스케이프한다.
export const DEFAULT_CMAKE_TEMPLATE = `set(MODULE_TEST_NAME filename_UnitTest)

file(GLOB SOURCES
    *.cpp
)

if(SOURCES)
    add_executable(\${MODULE_TEST_NAME} \${SOURCES})

    target_link_libraries(\${MODULE_TEST_NAME} PRIVATE UnitTest)
    target_link_libraries(\${MODULE_TEST_NAME} PRIVATE Json)
    target_link_libraries(\${MODULE_TEST_NAME} PRIVATE Util)
    target_link_libraries(\${MODULE_TEST_NAME} PRIVATE Kstub)

    if (LCOV_ENABLE STREQUAL True)
        add_custom_command(TARGET \${MODULE_TEST_NAME} POST_BUILD COMMAND find \${PROJECT_BINARY_DIR} -name *.gcda -type f -delete | true)
    endif()

    gtest_discover_tests(\${MODULE_TEST_NAME} EXTRA_ARGS --gtest_output=xml:\${CMAKE_CURRENT_BINARY_DIR}/gtest_results.xml)
endif()
`

export const patchSchema = z.object({
  name: z.string().min(1, '이름을 입력하세요'),
  content: z.string().min(1, '내용을 입력하세요'),
})

// 절대 경로 판정: 윈도우 드라이브(C:\ 또는 C:/), UNC(\\server), POSIX(/)
export const ABSOLUTE_PATH_RE = /^(?:[A-Za-z]:[\\/]|\/|\\\\)/

export const productFormSchema = z
  .object({
    project: z.enum(['Ulysses', 'Thetis']),
    name: z.string().min(1, '이름을 입력하세요'),
    product_code: z.string().min(1, '프로덕트 ID를 입력하세요'),
    git_url: z.string().min(1, 'git URL을 입력하세요'),
    git_ref: z.string().min(1, 'git ref를 입력하세요'),
    // 코드 업데이트 방식: reset(원격 강제 일치) | rebase(로컬 커밋 유지)
    git_update_mode: z.enum(['reset', 'rebase']),
    compile_db_rel: z.string().min(1, 'compile_commands.json 폴더 경로를 입력하세요'),
    out_tests_rel: z.string().min(1, '테스트 출력 폴더 경로를 입력하세요'),
    cmake_configure_cmd: z.string().min(1, 'configure 명령을 입력하세요'),
    cmake_build_cmd: z.string().min(1, 'build 명령을 입력하세요'),
    test_run_cmd: z.string().min(1, 'test 실행 명령을 입력하세요'),
    test_generation_mode: z.enum(['c', 'cpp', 'kunit']),
    // 필수 + 절대 경로 — 다운로드/명령 실행이 이 경로를 작업 디렉터리로 쓴다
    code_path: z
      .string()
      .min(1, '코드 저장 경로를 입력하세요')
      .regex(ABSOLUTE_PATH_RE, '코드 저장 경로는 절대 경로로 입력하세요'),
    // 제외 패턴: 한 줄에 하나(예: *test*). 제출 시 줄 분리해 string[]로 변환한다.
    exclude_patterns: z.string(),
    patches: z.array(patchSchema),
    // 자동 실행 모드
    auto_run: z.boolean(),
    auto_interval_value: z.coerce.number().min(1, '주기를 입력하세요'),
    auto_interval_unit: z.enum(['minutes', 'hours', 'days']),
    cmake_template: z.string(),
  })
  .refine((v) => !v.auto_run || v.product_code.startsWith('auto'), {
    path: ['product_code'],
    message: "자동 실행 모드의 ID는 'auto'로 시작해야 합니다",
  })

export type ProductFormValues = z.infer<typeof productFormSchema>

export const EMPTY_PRODUCT_FORM: ProductFormValues = {
  project: 'Ulysses',
  name: '',
  product_code: '',
  git_url: '',
  git_ref: 'main',
  git_update_mode: 'reset',
  compile_db_rel: '',
  out_tests_rel: '',
  cmake_configure_cmd: '',
  cmake_build_cmd: '',
  test_run_cmd: '',
  test_generation_mode: 'cpp',
  code_path: '',
  exclude_patterns: '',
  patches: [],
  auto_run: false,
  auto_interval_value: 24,
  auto_interval_unit: 'hours',
  cmake_template: DEFAULT_CMAKE_TEMPLATE,
}

// 단위 → 초 환산
export const INTERVAL_UNIT_SECONDS: Record<ProductFormValues['auto_interval_unit'], number> = {
  minutes: 60,
  hours: 3600,
  days: 86400,
}
