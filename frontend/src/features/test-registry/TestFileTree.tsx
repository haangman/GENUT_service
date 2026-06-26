import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getTree } from '../../api/tree'
import type { TreeEntry } from '../../types/api'

// FileTree(요청 탭)와 같은 UX지만 request store에 결합하지 않고 props로 선택 상태를 받는다.
interface TreeProps {
  productId: number
  selected: Set<string>
  onToggle: (path: string) => void
  onImportFolder: (path: string) => void
}

function useTree(productId: number, path: string) {
  return useQuery({
    queryKey: ['tree', productId, path],
    queryFn: () => getTree(productId, path),
  })
}

interface NodeProps extends TreeProps {
  entry: TreeEntry
}

function FileNode({ entry, selected, onToggle }: NodeProps) {
  const checked = selected.has(entry.path)
  return (
    <div className="pl-5">
      <label className="flex items-center gap-1">
        <input type="checkbox" checked={checked} onChange={() => onToggle(entry.path)} />
        {entry.name}
      </label>
    </div>
  )
}

function DirNode(props: NodeProps) {
  const { entry, onImportFolder } = props
  const [expanded, setExpanded] = useState(false)
  return (
    <div className="pl-2">
      <div className="flex items-center gap-2">
        <button type="button" className="font-medium" onClick={() => setExpanded((v) => !v)}>
          {expanded ? '▾' : '▸'} {entry.name}
        </button>
        <button
          type="button"
          className="link text-xs"
          onClick={() => onImportFolder(entry.path)}
        >
          폴더 가져오기
        </button>
      </div>
      {expanded ? <DirChildren {...props} path={entry.path} /> : null}
    </div>
  )
}

function DirChildren({ path, ...props }: TreeProps & { path: string }) {
  const { data, isLoading } = useTree(props.productId, path)
  if (isLoading) return <div className="pl-5 text-xs text-subtle">…</div>
  return (
    <div>
      {(data ?? []).map((entry) => (
        <TreeNode key={entry.path} {...props} entry={entry} />
      ))}
    </div>
  )
}

function TreeNode(props: NodeProps) {
  return props.entry.type === 'file' ? <FileNode {...props} /> : <DirNode {...props} />
}

export function TestFileTree(props: TreeProps) {
  const { data, isLoading, isError } = useTree(props.productId, '')

  if (isLoading) return <p className="text-sm text-muted">트리 로딩…</p>
  if (isError)
    return (
      <p role="alert" className="text-sm text-danger-fg">
        트리를 불러오지 못했습니다.
      </p>
    )

  return (
    <div className="card max-h-[28rem] overflow-auto p-3 text-sm">
      {(data ?? []).map((entry) => (
        <TreeNode key={entry.path} {...props} entry={entry} />
      ))}
    </div>
  )
}
