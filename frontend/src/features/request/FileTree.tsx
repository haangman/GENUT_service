import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getTree } from '../../api/tree'
import type { TreeEntry } from '../../types/api'
import { importFolder } from './folderImport'
import { makeIsSourceFile } from './sourceFiles'
import { useRequestBuilder } from './store'

function useTree(productId: number, path: string) {
  return useQuery({
    queryKey: ['tree', productId, path],
    queryFn: () => getTree(productId, path),
  })
}

interface NodeProps {
  productId: number
  entry: TreeEntry
  onImport: (path: string) => void
}

function FileNode({ entry }: { entry: TreeEntry }) {
  const selected = useRequestBuilder((state) => state.selected)
  const toggleFile = useRequestBuilder((state) => state.toggleFile)
  const checked = selected.includes(entry.path)
  return (
    <div className="pl-5">
      <label className="flex items-center gap-1">
        <input type="checkbox" checked={checked} onChange={() => toggleFile(entry.path)} />
        {entry.name}
      </label>
    </div>
  )
}

function DirNode({ productId, entry, onImport }: NodeProps) {
  const [expanded, setExpanded] = useState(false)
  return (
    <div className="pl-2">
      <div className="flex items-center gap-2">
        <button
          type="button"
          className="font-medium"
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? '▾' : '▸'} {entry.name}
        </button>
        <button
          type="button"
          className="link text-xs"
          onClick={() => onImport(entry.path)}
        >
          폴더 가져오기
        </button>
      </div>
      {expanded ? <DirChildren productId={productId} path={entry.path} onImport={onImport} /> : null}
    </div>
  )
}

function DirChildren({ productId, path, onImport }: { productId: number; path: string; onImport: (p: string) => void }) {
  const { data, isLoading } = useTree(productId, path)
  if (isLoading) return <div className="pl-5 text-xs text-subtle">…</div>
  return (
    <div>
      {(data ?? []).map((entry) => (
        <TreeNode key={entry.path} productId={productId} entry={entry} onImport={onImport} />
      ))}
    </div>
  )
}

function TreeNode(props: NodeProps) {
  return props.entry.type === 'file' ? (
    <FileNode entry={props.entry} />
  ) : (
    <DirNode {...props} />
  )
}

export function FileTreePanel({ productId }: { productId: number }) {
  const { data, isLoading, isError } = useTree(productId, '')
  const addPaths = useRequestBuilder((state) => state.addPaths)
  const mode = useRequestBuilder((state) => state.mode)

  const onImport = async (folderPath: string) => {
    const files = await importFolder(folderPath, {
      fetchTree: (path) => getTree(productId, path),
      isSourceFile: makeIsSourceFile(mode),
    })
    addPaths(files)
  }

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
        <TreeNode key={entry.path} productId={productId} entry={entry} onImport={onImport} />
      ))}
    </div>
  )
}
