import { useEffect, useMemo, useRef, useState } from 'react'
import { useFieldArray, useForm } from 'react-hook-form'
import { useMutation, useQuery } from '@tanstack/react-query'
import { zodResolver } from '@hookform/resolvers/zod'
import { EMPTY_PRODUCT_FORM, productFormSchema, type ProductFormValues } from './productSchema'
import { previewTargetFiles, pullCode } from '../../api/products'
import { ApiError } from '../../lib/apiClient'
import { useLang } from '../../lib/i18n'
import { PROJECTS } from '../../lib/projects'
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
  // 수정 시 저장돼 있던 대상 파일 목록(미리보기 초기 제외/포함 상태를 복원)
  initialAutoFiles?: string[]
}

export function ProductForm({ onSubmit, submitting, defaultValues, initialAutoFiles }: ProductFormProps) {
  const { t } = useLang()
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
  const testMode = watch('test_generation_mode')
  const codePath = watch('code_path')
  const compileDbRel = watch('compile_db_rel')
  const excludePatterns = watch('exclude_patterns')
  const gitUrl = watch('git_url')
  const gitRef = watch('git_ref')
  const outTestsRel = watch('out_tests_rel')

  // 코드 저장 경로 다운로드(git clone/pull). 폼 값 기반이라 저장 전에도 동작한다.
  const pullMut = useMutation({
    mutationFn: () =>
      pullCode({
        git_url: gitUrl.trim(),
        git_ref: gitRef.trim() || 'main',
        code_path: codePath.trim(),
        out_tests_rel: outTestsRel.trim() || undefined,
      }),
  })
  const canPull = Boolean(gitUrl.trim() && codePath.trim()) && !pullMut.isPending
  const pullReset = pullMut.reset
  // 경로/URL을 고치면 이전 성공/실패 표시는 무효 — 상태를 지운다
  useEffect(() => {
    pullReset()
  }, [codePath, gitUrl, pullReset])
  const pullErrorDetail =
    pullMut.error instanceof ApiError
      ? (pullMut.error.body as { detail?: string } | null)?.detail
      : undefined

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
  // 수정 시: 저장돼 있던 파일 목록으로 최초 1회 제외/포함 상태를 복원한다.
  const restoredRef = useRef(false)
  useEffect(() => {
    if (restoredRef.current || !initialAutoFiles || candidates.length === 0) return
    restoredRef.current = true
    const saved = new Set(initialAutoFiles)
    setOverrides(Object.fromEntries(candidates.map((f) => [f.path, !saved.has(f.path)])))
  }, [candidates, initialAutoFiles])

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
        {t('자동 실행 모드 (주기마다 자동으로 테스트 생성)')}
      </label>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="project" className="label">
            {t('프로젝트')}
          </label>
          <select id="project" className={inputClass} {...register('project')}>
            {PROJECTS.map((project) => (
              <option key={project} value={project}>
                {project}
              </option>
            ))}
          </select>
        </div>

        {TEXT_FIELDS.map((field) => (
          <div key={field.name}>
            <label htmlFor={field.name} className="label">
              {field.name === 'product_code' && autoRun
                ? t('{label} (auto 로 시작)', { label: t(field.label) })
                : t(field.label)}
            </label>
            {field.name === 'code_path' ? (
              // 코드 저장 경로: 입력 옆 다운로드 버튼(git clone/pull) + 결과 표시
              <>
                <div className="flex gap-2">
                  <input id={field.name} className={inputClass} {...register(field.name)} />
                  <button
                    type="button"
                    className="btn btn-sm shrink-0 self-center"
                    onClick={() => pullMut.mutate()}
                    disabled={!canPull}
                    title={t('이 경로로 git 코드를 받아온다 (없으면 clone, 있으면 업데이트)')}
                  >
                    {pullMut.isPending ? t('다운로드 중…') : t('다운로드')}
                  </button>
                </div>
                {pullMut.isSuccess ? (
                  <p className="mt-1 text-xs text-success-fg">
                    {t('다운로드 성공')} — {t(pullMut.data.detail)}
                  </p>
                ) : null}
                {pullMut.isError ? (
                  <p role="alert" className="mt-1 text-xs text-danger-fg">
                    {t('다운로드 실패')}
                    {pullErrorDetail ? `: ${pullErrorDetail}` : ''}
                  </p>
                ) : null}
              </>
            ) : (
              <input id={field.name} className={inputClass} {...register(field.name)} />
            )}
            {errors[field.name] ? (
              <p role="alert" className="mt-1 text-xs text-danger-fg">
                {t(errors[field.name]?.message ?? '')}
              </p>
            ) : null}
          </div>
        ))}

        <div>
          <label htmlFor="test_generation_mode" className="label">
            {t('테스트 모드')} {autoRun ? t('(c·cpp=gtest, kunit은 추후)') : ''}
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
              {t('자동 수행 주기')}
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
                <option value="minutes">{t('분')}</option>
                <option value="hours">{t('시간')}</option>
                <option value="days">{t('일')}</option>
              </select>
            </div>
          </div>
        ) : null}
      </div>

      <div>
        <label htmlFor="exclude_patterns" className="label">
          {t('테스트 대상 제외 패턴 (한 줄에 하나, 예:')} <code className="font-mono">*test*</code>)
        </label>
        <textarea
          id="exclude_patterns"
          className={`${inputClass} min-h-[72px] font-mono`}
          placeholder={'*test*\n*/legacy/*'}
          {...register('exclude_patterns')}
        />
        <p className="mt-1 text-xs text-subtle">
          {t('compile_commands.json 대상 파일 중 path가 이 글롭에 맞으면 제외됩니다.')}
        </p>
      </div>

      {autoRun ? (
        <>
          <div className="rounded-lg border border-border p-4">
            <div className="mb-2 flex items-center gap-2">
              <h4 className="text-sm font-semibold text-fg">
                {t('대상 파일 미리보기 ({included}/{total})', {
                  included: included.length,
                  total: candidates.length,
                })}
              </h4>
              {isFetching ? <span className="text-xs text-muted">{t('스캔 중…')}</span> : null}
            </div>
            {candidates.length === 0 ? (
              <p className="text-sm text-subtle">
                {t('코드 저장 경로와 compile_commands.json 폴더를 입력하면 대상 파일이 표시됩니다.')}
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
                            {t('제외됨')}{byPattern ? t(' (패턴)') : ''}
                          </span>
                        ) : null}
                        <button
                          type="button"
                          className="btn btn-sm btn-ghost"
                          onClick={() => toggle(f)}
                        >
                          {excluded ? t('복원') : t('제외')}
                        </button>
                      </span>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>

          {/* kunit은 gtest용 CMakeLists 스캐폴딩을 쓰지 않으므로 양식창을 숨긴다 */}
          {testMode !== 'kunit' ? (
            <div>
              <label htmlFor="cmake_template" className="label">
                {t('CMakeLists.txt 양식 (placeholder')} <code className="font-mono">filename</code> {t('→ 파일 이름으로 치환)')}
              </label>
              <textarea
                id="cmake_template"
                className={`${inputClass} min-h-[220px] font-mono text-xs`}
                {...register('cmake_template')}
              />
            </div>
          ) : null}
        </>
      ) : null}

      <fieldset className="rounded-lg border border-border p-4">
        <legend className="px-1.5 text-sm font-medium text-fg">{t('패치 (순서대로 적용)')}</legend>
        {fields.map((field, index) => (
          <div key={field.id} className="mb-3 space-y-1.5 border-b border-dashed border-border pb-3">
            <input
              aria-label={t('패치 {n} 이름', { n: index + 1 })}
              className={inputClass}
              placeholder={t('이름')}
              {...register(`patches.${index}.name`)}
            />
            <textarea
              aria-label={t('패치 {n} 내용', { n: index + 1 })}
              className={`${inputClass} min-h-[72px] font-mono`}
              placeholder="unified diff"
              {...register(`patches.${index}.content`)}
            />
            <button
              type="button"
              className="text-xs font-medium text-danger-fg transition hover:opacity-80"
              onClick={() => remove(index)}
            >
              {t('삭제')}
            </button>
          </div>
        ))}
        <button type="button" className="link text-sm" onClick={() => append({ name: '', content: '' })}>
          {t('패치 추가')}
        </button>
      </fieldset>

      <button type="submit" disabled={submitting} className="btn btn-primary px-5">
        {t('저장')}
      </button>
    </form>
  )
}
