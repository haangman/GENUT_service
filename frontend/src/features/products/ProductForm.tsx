import { useEffect, useMemo, useState } from 'react'
import { useFieldArray, useForm } from 'react-hook-form'
import { useQuery } from '@tanstack/react-query'
import { zodResolver } from '@hookform/resolvers/zod'
import { EMPTY_PRODUCT_FORM, productFormSchema, type ProductFormValues } from './productSchema'
import { previewTargetFiles } from '../../api/products'
import type { TargetFileItem } from '../../types/api'

type TextFieldName =
  | 'name'
  | 'product_code'
  | 'git_url'
  | 'git_ref'
  | 'compile_db_rel'
  | 'out_tests_rel'
  | 'cmake_configure_cmd'
  | 'cmake_build_cmd'
  | 'test_run_cmd'
  | 'code_path'

const TEXT_FIELDS: { name: TextFieldName; label: string }[] = [
  { name: 'name', label: '이름' },
  { name: 'product_code', label: '프로덕트 ID' },
  { name: 'code_path', label: '코드 저장 경로 (선택, 절대/상대)' },
  { name: 'git_url', label: 'Git URL' },
  { name: 'git_ref', label: 'Git ref' },
  { name: 'compile_db_rel', label: 'compile_commands.json 폴더(상대)' },
  { name: 'out_tests_rel', label: '테스트 출력 폴더(상대)' },
  { name: 'cmake_configure_cmd', label: 'CMAKE_CONFIGURE_CMD' },
  { name: 'cmake_build_cmd', label: 'CMAKE_BUILD_CMD' },
  { name: 'test_run_cmd', label: 'TEST_RUN_CMD' },
]

const inputClass = 'input'

interface ProductFormProps {
  // autoFileList: 자동 실행 모드에서 최종 포함된 대상 파일 목록(비자동이면 빈 배열)
  onSubmit: (values: ProductFormValues, autoFileList: string[]) => void
  submitting?: boolean
  defaultValues?: Partial<ProductFormValues>
}

export function ProductForm({ onSubmit, submitting, defaultValues }: ProductFormProps) {
  const {
    register,
    handleSubmit,
    control,
    watch,
    formState: { errors },
  } = useForm<ProductFormValues>({
    resolver: zodResolver(productFormSchema),
    defaultValues: { ...EMPTY_PRODUCT_FORM, ...defaultValues },
  })
  const { fields, append, remove } = useFieldArray({ control, name: 'patches' })

  const autoRun = watch('auto_run')
  const codePath = watch('code_path')
  const compileDbRel = watch('compile_db_rel')
  const excludePatterns = watch('exclude_patterns')

  // 대상 파일 미리보기: code_path/compile_db_rel/제외패턴 변경을 디바운스해 조회한다.
  const [params, setParams] = useState({ code_path: '', compile_db_rel: '', exclude_globs: [] as string[] })
  useEffect(() => {
    const globs = excludePatterns.split('\n').map((s) => s.trim()).filter(Boolean)
    const timer = setTimeout(
      () => setParams({ code_path: codePath, compile_db_rel: compileDbRel, exclude_globs: globs }),
      400,
    )
    return () => clearTimeout(timer)
  }, [codePath, compileDbRel, excludePatterns])

  const { data: preview, isFetching } = useQuery({
    queryKey: ['target-files', params],
    queryFn: () => previewTargetFiles(params),
    enabled: autoRun && Boolean(params.code_path) && Boolean(params.compile_db_rel),
  })
  const candidates: TargetFileItem[] = preview?.files ?? []

  // 행별 수동 override(true=제외, false=복원). 없으면 패턴 매칭 결과를 따른다.
  const [overrides, setOverrides] = useState<Record<string, boolean>>({})
  const isExcluded = (f: TargetFileItem) =>
    f.path in overrides ? overrides[f.path] : f.excluded_by_pattern
  const toggle = (f: TargetFileItem) =>
    setOverrides((prev) => ({ ...prev, [f.path]: !isExcluded(f) }))
  const included = useMemo(
    () => candidates.filter((f) => !isExcluded(f)).map((f) => f.path),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [candidates, overrides],
  )

  const submit = (values: ProductFormValues) => onSubmit(values, included)

  return (
    <form onSubmit={handleSubmit(submit)} className="card space-y-4 p-5">
      <label className="flex items-center gap-2 text-sm font-medium text-fg">
        <input type="checkbox" {...register('auto_run')} />
        자동 실행 모드 (주기마다 자동으로 테스트 생성)
      </label>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {TEXT_FIELDS.map((field) => (
          <div key={field.name}>
            <label htmlFor={field.name} className="label">
              {field.name === 'product_code' && autoRun ? `${field.label} (auto 로 시작)` : field.label}
            </label>
            <input id={field.name} className={inputClass} {...register(field.name)} />
            {errors[field.name] ? (
              <p role="alert" className="mt-1 text-xs text-danger-fg">
                {errors[field.name]?.message}
              </p>
            ) : null}
          </div>
        ))}

        <div>
          <label htmlFor="test_generation_mode" className="label">
            테스트 모드 {autoRun ? '(c·cpp=gtest, kunit은 추후)' : ''}
          </label>
          <select
            id="test_generation_mode"
            className={inputClass}
            {...register('test_generation_mode')}
          >
            <option value="c">c</option>
            <option value="cpp">cpp</option>
            <option value="kunit">kunit</option>
          </select>
        </div>

        {autoRun ? (
          <div>
            <label htmlFor="auto_interval_value" className="label">
              자동 수행 주기
            </label>
            <div className="flex gap-2">
              <input
                id="auto_interval_value"
                type="number"
                min={1}
                className={inputClass}
                {...register('auto_interval_value')}
              />
              <select className={inputClass} {...register('auto_interval_unit')}>
                <option value="minutes">분</option>
                <option value="hours">시간</option>
                <option value="days">일</option>
              </select>
            </div>
          </div>
        ) : null}
      </div>

      <div>
        <label htmlFor="exclude_patterns" className="label">
          테스트 대상 제외 패턴 (한 줄에 하나, 예: <code className="font-mono">*test*</code>)
        </label>
        <textarea
          id="exclude_patterns"
          className={`${inputClass} min-h-[72px] font-mono`}
          placeholder={'*test*\n*/legacy/*'}
          {...register('exclude_patterns')}
        />
        <p className="mt-1 text-xs text-subtle">
          compile_commands.json 대상 파일 중 path가 이 글롭에 맞으면 제외됩니다.
        </p>
      </div>

      {autoRun ? (
        <>
          <div className="rounded-lg border border-border p-4">
            <div className="mb-2 flex items-center gap-2">
              <h4 className="text-sm font-semibold text-fg">
                대상 파일 미리보기 ({included.length}/{candidates.length})
              </h4>
              {isFetching ? <span className="text-xs text-muted">스캔 중…</span> : null}
            </div>
            {candidates.length === 0 ? (
              <p className="text-sm text-subtle">
                코드 저장 경로와 compile_commands.json 폴더를 입력하면 대상 파일이 표시됩니다.
              </p>
            ) : (
              <ul className="max-h-72 overflow-auto">
                {candidates.map((f) => {
                  const excluded = isExcluded(f)
                  const byPattern = !(f.path in overrides) && f.excluded_by_pattern
                  return (
                    <li
                      key={f.path}
                      className="flex items-center justify-between gap-2 border-b border-border py-1.5"
                    >
                      <span
                        className={`break-all font-mono text-xs ${
                          excluded ? 'text-danger-fg line-through' : 'text-fg'
                        }`}
                      >
                        {f.path}
                      </span>
                      <span className="flex shrink-0 items-center gap-2">
                        {excluded ? (
                          <span className="badge badge-danger">
                            제외됨{byPattern ? ' (패턴)' : ''}
                          </span>
                        ) : null}
                        <button
                          type="button"
                          className="btn btn-sm btn-ghost"
                          onClick={() => toggle(f)}
                        >
                          {excluded ? '복원' : '제외'}
                        </button>
                      </span>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>

          <div>
            <label htmlFor="cmake_template" className="label">
              CMakeLists.txt 양식 (placeholder <code className="font-mono">filename</code> → 파일 이름으로 치환)
            </label>
            <textarea
              id="cmake_template"
              className={`${inputClass} min-h-[220px] font-mono text-xs`}
              {...register('cmake_template')}
            />
          </div>
        </>
      ) : null}

      <fieldset className="rounded-lg border border-border p-4">
        <legend className="px-1.5 text-sm font-medium text-fg">패치 (순서대로 적용)</legend>
        {fields.map((field, index) => (
          <div key={field.id} className="mb-3 space-y-1.5 border-b border-dashed border-border pb-3">
            <input
              aria-label={`패치 ${index + 1} 이름`}
              className={inputClass}
              placeholder="이름"
              {...register(`patches.${index}.name`)}
            />
            <textarea
              aria-label={`패치 ${index + 1} 내용`}
              className={`${inputClass} min-h-[72px] font-mono`}
              placeholder="unified diff"
              {...register(`patches.${index}.content`)}
            />
            <button
              type="button"
              className="text-xs font-medium text-danger-fg transition hover:opacity-80"
              onClick={() => remove(index)}
            >
              삭제
            </button>
          </div>
        ))}
        <button type="button" className="link text-sm" onClick={() => append({ name: '', content: '' })}>
          패치 추가
        </button>
      </fieldset>

      <button type="submit" disabled={submitting} className="btn btn-primary px-5">
        저장
      </button>
    </form>
  )
}
