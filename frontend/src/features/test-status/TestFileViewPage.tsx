import { useQuery } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { PageHeader } from '../../components/PageHeader'
import { getTestFileContent } from '../../api/testStatus'
import { useLang } from '../../lib/i18n'

// 테스트 코드/로그 뷰어(전용 라우트). 쿼리: code, codePath, logPath, name, tab(code|log).
// 탭 전환은 tab 파라미터를 replace로 바꿔 히스토리를 더럽히지 않고, 뒤로가기는 목록으로 복귀한다.
export function TestFileViewPage() {
  const { t } = useLang()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  const code = searchParams.get('code') ?? ''
  const codePath = searchParams.get('codePath') ?? ''
  const logPath = searchParams.get('logPath')
  const name = searchParams.get('name') ?? ''
  const tab = searchParams.get('tab') === 'log' ? 'log' : 'code'

  const activePath = tab === 'log' ? logPath ?? '' : codePath

  const setTab = (next: 'code' | 'log') => {
    const params = new URLSearchParams(searchParams)
    params.set('tab', next)
    setSearchParams(params, { replace: true })
  }

  const { data, isLoading, isError } = useQuery({
    queryKey: ['test-file', code, activePath],
    queryFn: () => getTestFileContent(code, activePath),
    enabled: code !== '' && activePath !== '',
  })

  return (
    <div>
      <button className="link mb-3 inline-block text-sm" onClick={() => navigate(-1)}>
        {t('← 뒤로')}
      </button>
      <PageHeader title={name || t('테스트 파일')} description={tab === 'log' ? t('생성 로그') : t('테스트 코드')} />

      <div className="mb-3 flex gap-2">
        <button
          className={`btn btn-sm ${tab === 'code' ? 'btn-primary' : ''}`}
          onClick={() => setTab('code')}
        >
          {t('코드')}
        </button>
        <button
          className={`btn btn-sm ${tab === 'log' ? 'btn-primary' : ''}`}
          onClick={() => setTab('log')}
          disabled={!logPath}
        >
          {t('로그')}
        </button>
      </div>

      {activePath ? (
        <p className="mb-2 break-all font-mono text-xs text-muted">{activePath}</p>
      ) : (
        <p className="text-sm text-subtle">{t('표시할 내용이 없습니다.')}</p>
      )}

      {isLoading ? <p className="text-sm text-muted">{t('불러오는 중…')}</p> : null}
      {isError ? (
        <p role="alert" className="text-sm text-danger-fg">
          {t('파일을 불러오지 못했습니다.')}
        </p>
      ) : null}
      {data ? (
        <pre className="card overflow-auto whitespace-pre p-4 font-mono text-xs text-fg">
          {data.content}
        </pre>
      ) : null}
    </div>
  )
}
