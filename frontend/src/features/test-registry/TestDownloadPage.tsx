import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { PageHeader } from '../../components/PageHeader'
import {
  downloadTestFilesZip,
  listRegisteredTestFiles,
  removeTestFiles,
} from '../../api/testFiles'
import { ProductGroupPicker } from './ProductGroupPicker'
import type { ProductGroup } from './groupByName'

export function TestDownloadPage() {
  const queryClient = useQueryClient()
  const [group, setGroup] = useState<ProductGroup | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const onSelectGroup = (next: ProductGroup) => {
    setGroup(next)
    setSelected(new Set())
  }

  const { data: files } = useQuery({
    queryKey: ['test-files', group?.name],
    queryFn: () => listRegisteredTestFiles(group!.name),
    enabled: group != null,
  })
  const rows = files ?? []

  const toggle = (path: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
  }

  const allChecked = rows.length > 0 && selected.size === rows.length
  const toggleAll = () => {
    setSelected(allChecked ? new Set() : new Set(rows.map((r) => r.rel_path)))
  }

  const downloadMut = useMutation({
    mutationFn: () => downloadTestFilesZip(group!.name, group!.representativeId, [...selected]),
    onError: () => window.alert('다운로드에 실패했습니다.'),
  })

  const removeMut = useMutation({
    mutationFn: () => removeTestFiles(group!.name, [...selected]),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['test-files', group!.name] })
      setSelected(new Set())
    },
    onError: () => window.alert('삭제에 실패했습니다.'),
  })

  return (
    <div>
      <PageHeader
        title="테스트 다운로드"
        description="프로덕트별로 등록된 테스트 파일을 확인하고 선택해 zip으로 받는다."
      />
      <ProductGroupPicker value={group?.name ?? null} onChange={onSelectGroup} />
      {group ? (
        <div className="card mt-5 p-4 text-sm">
          {rows.length === 0 ? (
            <p className="text-subtle">등록된 테스트 파일이 없습니다.</p>
          ) : (
            <>
              <div className="mb-3 flex items-center justify-between gap-3 border-b border-border pb-3">
                <label className="flex items-center gap-2 font-medium text-fg">
                  <input type="checkbox" checked={allChecked} onChange={toggleAll} />
                  전체 선택 ({selected.size}/{rows.length})
                </label>
                <div className="flex gap-2">
                  <button
                    type="button"
                    className="btn btn-primary btn-sm"
                    disabled={selected.size === 0 || downloadMut.isPending}
                    onClick={() => downloadMut.mutate()}
                  >
                    {downloadMut.isPending ? '다운로드 중…' : '다운로드 (zip)'}
                  </button>
                  <button
                    type="button"
                    className="btn btn-danger btn-sm"
                    disabled={selected.size === 0 || removeMut.isPending}
                    onClick={() => removeMut.mutate()}
                  >
                    선택 삭제
                  </button>
                </div>
              </div>
              <ul className="space-y-1.5">
                {rows.map((row) => (
                  <li key={row.id}>
                    <label className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={selected.has(row.rel_path)}
                        onChange={() => toggle(row.rel_path)}
                      />
                      <span className="truncate font-mono text-xs text-muted">{row.rel_path}</span>
                    </label>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      ) : (
        <p className="mt-5 text-sm text-muted">프로덕트를 선택하세요.</p>
      )}
    </div>
  )
}
