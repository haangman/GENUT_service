import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { PageHeader } from '../../components/PageHeader'
import { getTree } from '../../api/tree'
import { addTestFiles } from '../../api/testFiles'
import { importFolder } from '../request/folderImport'
import { ProductGroupPicker } from './ProductGroupPicker'
import { TestFileTree } from './TestFileTree'
import type { ProductGroup } from './groupByName'

// result.json은 GENUT 산출물 메타라 테스트 파일에서 제외하고 나머지는 모두 가져온다.
const isTestFile = (name: string) => name !== 'result.json'

export function TestRegistryPage() {
  const queryClient = useQueryClient()
  const [group, setGroup] = useState<ProductGroup | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const onSelectGroup = (next: ProductGroup) => {
    setGroup(next)
    setSelected(new Set())
  }

  const toggle = (path: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
  }

  const importFolderPaths = async (folderPath: string) => {
    if (!group) return
    const files = await importFolder(folderPath, {
      fetchTree: (path) => getTree(group.representativeId, path),
      isSourceFile: isTestFile,
    })
    setSelected((prev) => new Set([...prev, ...files]))
  }

  const registerMut = useMutation({
    mutationFn: () => addTestFiles(group!.name, [...selected]),
    onSuccess: (rows) => {
      queryClient.invalidateQueries({ queryKey: ['test-files', group!.name] })
      setSelected(new Set())
      window.alert(`등록 완료 (총 ${rows.length}개)`)
    },
    onError: () => window.alert('등록에 실패했습니다.'),
  })

  return (
    <div>
      <PageHeader
        title="테스트 등록"
        description="프로덕트를 선택해 코드 트리에서 테스트 파일(또는 폴더)을 골라 등록한다."
      />
      <ProductGroupPicker value={group?.name ?? null} onChange={onSelectGroup} />
      {group ? (
        <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
          <TestFileTree
            productId={group.representativeId}
            selected={selected}
            onToggle={toggle}
            onImportFolder={importFolderPaths}
          />
          <div className="rounded border bg-white p-3 text-sm">
            <div className="mb-2 font-medium">선택한 파일 ({selected.size})</div>
            {selected.size === 0 ? (
              <p className="text-gray-400">아직 선택한 파일이 없습니다.</p>
            ) : (
              <ul className="space-y-1">
                {[...selected].map((path) => (
                  <li key={path} className="flex items-center justify-between gap-2">
                    <span className="truncate">{path}</span>
                    <button className="text-xs text-red-600" onClick={() => toggle(path)}>
                      제거
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <button
              type="button"
              className="mt-3 rounded border px-3 py-1.5 text-sm font-medium disabled:opacity-50"
              disabled={selected.size === 0 || registerMut.isPending}
              onClick={() => registerMut.mutate()}
            >
              {registerMut.isPending ? '등록 중…' : '등록'}
            </button>
          </div>
        </div>
      ) : (
        <p className="mt-4 text-sm text-gray-500">프로덕트를 선택하세요.</p>
      )}
    </div>
  )
}
