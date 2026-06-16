import { z } from 'zod'

export const patchSchema = z.object({
  name: z.string().min(1, '이름을 입력하세요'),
  content: z.string().min(1, '내용을 입력하세요'),
})

export const productFormSchema = z.object({
  name: z.string().min(1, '이름을 입력하세요'),
  product_code: z.string().min(1, '프로덕트 ID를 입력하세요'),
  git_url: z.string().min(1, 'git URL을 입력하세요'),
  git_ref: z.string().min(1, 'git ref를 입력하세요'),
  compile_db_rel: z.string().min(1, 'compile_commands.json 폴더 경로를 입력하세요'),
  out_tests_rel: z.string().min(1, '테스트 출력 폴더 경로를 입력하세요'),
  cmake_configure_cmd: z.string().min(1, 'configure 명령을 입력하세요'),
  cmake_build_cmd: z.string().min(1, 'build 명령을 입력하세요'),
  test_run_cmd: z.string().min(1, 'test 실행 명령을 입력하세요'),
  test_generation_mode: z.enum(['c', 'cpp', 'kunit']),
  code_path: z.string(),
  patches: z.array(patchSchema),
})

export type ProductFormValues = z.infer<typeof productFormSchema>

export const EMPTY_PRODUCT_FORM: ProductFormValues = {
  name: '',
  product_code: '',
  git_url: '',
  git_ref: 'main',
  compile_db_rel: '',
  out_tests_rel: '',
  cmake_configure_cmd: '',
  cmake_build_cmd: '',
  test_run_cmd: '',
  test_generation_mode: 'cpp',
  code_path: '',
  patches: [],
}
