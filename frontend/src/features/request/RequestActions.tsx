import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { createJob } from '../../api/jobs'
import { compileCheck } from '../../api/tree'
import { useRequestBuilder } from './store'

export function RequestActions() {
  const productId = useRequestBuilder((state) => state.productId)
  const selected = useRequestBuilder((state) => state.selected)
  const functionName = useRequestBuilder((state) => state.functionName)
  const compileResult = useRequestBuilder((state) => state.compileResult)
  const compileStale = useRequestBuilder((state) => state.compileStale)
  const setCompileResult = useRequestBuilder((state) => state.setCompileResult)
  const setFunctionName = useRequestBuilder((state) => state.setFunctionName)
  const [submittedJobId, setSubmittedJobId] = useState<number | null>(null)

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
    onSuccess: (job) => setSubmittedJobId(job.id),
  })

  const canCheck = selected.length > 0 && !checkMut.isPending
  const canSubmit =
    !!compileResult && !compileStale && compileResult.included.length > 0 && !submitMut.isPending

  return (
    <div className="mt-4 space-y-3 rounded border bg-white p-3 text-sm">
      <div>
        <label htmlFor="function-name" className="text-sm font-medium">
          함수명 (선택)
        </label>
        <input
          id="function-name"
          className="mt-1 block w-64 rounded border border-gray-300 px-2 py-1"
          value={functionName}
          onChange={(event) => setFunctionName(event.target.value)}
        />
      </div>

      <button
        className="rounded border px-3 py-1.5 font-medium disabled:opacity-50"
        disabled={!canCheck}
        onClick={() => checkMut.mutate()}
      >
        compile_commands 검사
      </button>

      {compileResult ? (
        <div className="space-y-2">
          {compileStale ? (
            <p role="alert" className="text-amber-700">
              선택이 변경되었습니다. 다시 검사하세요.
            </p>
          ) : null}
          <div>
            <h4 className="font-medium text-green-700">포함 ({compileResult.included.length})</h4>
            <ul className="list-inside list-disc">
              {compileResult.included.map((file) => (
                <li key={file} className="text-green-700">
                  {file}
                </li>
              ))}
            </ul>
          </div>
          {compileResult.excluded.length > 0 ? (
            <div>
              <h4 className="font-medium text-amber-700">
                제외 — compile_commands.json에 없음 ({compileResult.excluded.length})
              </h4>
              <ul className="list-inside list-disc">
                {compileResult.excluded.map((file) => (
                  <li key={file} className="text-amber-700">
                    {file}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}

      <button
        className="rounded bg-gray-900 px-4 py-1.5 font-medium text-white disabled:opacity-50"
        disabled={!canSubmit}
        onClick={() => submitMut.mutate()}
      >
        제출
      </button>
      {submittedJobId ? (
        <p className="text-green-700">요청이 접수되었습니다. job #{submittedJobId}</p>
      ) : null}
      {submitMut.isError ? (
        <p role="alert" className="text-red-600">
          제출에 실패했습니다.
        </p>
      ) : null}
    </div>
  )
}
