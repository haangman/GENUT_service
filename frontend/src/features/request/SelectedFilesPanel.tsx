import { useRequestBuilder } from './store'
import { useLang } from '../../lib/i18n'

export function SelectedFilesPanel() {
  const { t } = useLang()
  const selected = useRequestBuilder((state) => state.selected)
  const removeFile = useRequestBuilder((state) => state.removeFile)

  return (
    <div className="card p-3 text-sm">
      <div className="mb-2 font-semibold text-fg">{t('선택한 파일 ({count})', { count: selected.length })}</div>
      {selected.length === 0 ? (
        <p className="text-subtle">{t('아직 선택한 파일이 없습니다.')}</p>
      ) : (
        <ul className="space-y-1">
          {selected.map((path) => (
            <li key={path} className="flex items-center justify-between gap-2">
              <span className="truncate font-mono text-xs text-muted">{path}</span>
              <button
                className="text-xs font-medium text-danger-fg transition hover:opacity-80"
                onClick={() => removeFile(path)}
              >
                {t('제거')}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
