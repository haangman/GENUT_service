import { useRequestBuilder } from './store'

export function SelectedFilesPanel() {
  const selected = useRequestBuilder((state) => state.selected)
  const removeFile = useRequestBuilder((state) => state.removeFile)

  return (
    <div className="card p-3 text-sm">
      <div className="mb-2 font-semibold text-fg">선택한 파일 ({selected.length})</div>
      {selected.length === 0 ? (
        <p className="text-subtle">아직 선택한 파일이 없습니다.</p>
      ) : (
        <ul className="space-y-1">
          {selected.map((path) => (
            <li key={path} className="flex items-center justify-between gap-2">
              <span className="truncate font-mono text-xs text-muted">{path}</span>
              <button
                className="text-xs font-medium text-danger-fg transition hover:opacity-80"
                onClick={() => removeFile(path)}
              >
                제거
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
