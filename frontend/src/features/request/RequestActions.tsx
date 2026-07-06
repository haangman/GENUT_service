import { useMutation } from '@tanstack/react-query'
import { createJob } from '../../api/jobs'
import { compileCheck } from '../../api/tree'
import { useRequestBuilder } from './store'
import { useLang } from '../../lib/i18n'

export function RequestActions() {
  const { t } = useLang()
  const productId = useRequestBuilder((state) => state.productId)
  const selected = useRequestBuilder((state) => state.selected)
  const functionName = useRequestBuilder((state) => state.functionName)
  const compileResult = useRequestBuilder((state) => state.compileResult)
  const compileStale = useRequestBuilder((state) => state.compileStale)
  const setCompileResult = useRequestBuilder((state) => state.setCompileResult)
  const setFunctionName = useRequestBuilder((state) => state.setFunctionName)
  const completeSubmission = useRequestBuilder((state) => state.completeSubmission)

  const checkMut = useMutation({
    mutationFn: () => compileCheck(productId as number, selected),
    onSuccess: (result) => setCompileResult(result),
  })

  const submitMut = useMutation({
    mutationFn: () =>
      createJob({
        product_id: productId as number,
        files: selected,
        function_name: functionName || undefined,
      }),
    // 제출 성공 시 요청 빌더를 초기화한다 → 페이지가 초기 화면으로 돌아간다.
    onSuccess: (job) => completeSubmission(job.id),
  })

  const canCheck = selected.length > 0 && !checkMut.isPending
  const canSubmit =
    !!compileResult && !compileStale && compileResult.included.length > 0 && !submitMut.isPending

  return (
    <div className="card mt-4 space-y-4 p-4 text-sm">
      <div className="max-w-xs">
        <label htmlFor="function-name" className="label">
          {t('함수명 (선택)')}
        </label>
        <input
          id="function-name"
          className="input"
          value={functionName}
          onChange={(event) => setFunctionName(event.target.value)}
        />
      </div>

      <button className="btn" disabled={!canCheck} onClick={() => checkMut.mutate()}>
        {t('compile_commands 검사')}
      </button>

      {compileResult ? (
        <div className="space-y-3">
          {compileStale ? (
            <p role="alert" className="text-sm font-medium text-warn-fg">
              {t('선택이 변경되었습니다. 다시 검사하세요.')}
            </p>
          ) : null}
          <div>
            <h4 className="mb-1 font-semibold text-success-fg">
              {t('포함 ({count})', { count: compileResult.included.length })}
            </h4>
            <ul className="space-y-0.5">
              {compileResult.included.map((file) => (
                <li key={file} className="font-mono text-xs text-success-fg">
                  {file}
                </li>
              ))}
            </ul>
          </div>
          {compileResult.excluded.length > 0 ? (
            <div>
              <h4 className="mb-1 font-semibold text-warn-fg">
                {t('제외 — compile_commands.json에 없음 ({count})', { count: compileResult.excluded.length })}
              </h4>
              <ul className="space-y-0.5">
                {compileResult.excluded.map((file) => (
                  <li key={file} className="font-mono text-xs text-warn-fg">
                    {file}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}

      <button className="btn btn-primary px-4" disabled={!canSubmit} onClick={() => submitMut.mutate()}>
        {t('제출')}
      </button>
      {submitMut.isError ? (
        <p role="alert" className="text-sm font-medium text-danger-fg">
          {t('제출에 실패했습니다.')}
        </p>
      ) : null}
    </div>
  )
}
