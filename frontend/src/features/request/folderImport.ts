import type { TreeEntry } from '../../types/api'

export interface FolderImportDeps {
  // 한 디렉터리(상대경로)의 직속 항목을 반환한다.
  fetchTree: (path: string) => Promise<TreeEntry[]>
  // 파일명이 대상 소스 파일인지 판정한다.
  isSourceFile: (name: string) => boolean
}

/**
 * 폴더 하위의 소스 파일을 재귀적으로(BFS) 수집한다.
 * 하위 디렉터리 조회 실패는 건너뛴다(부분 실패 허용). 결과는 중복 제거.
 */
export async function importFolder(
  folderPath: string,
  deps: FolderImportDeps,
): Promise<string[]> {
  const collected: string[] = []
  const queue: string[] = [folderPath]
  while (queue.length > 0) {
    const current = queue.shift() as string
    let entries: TreeEntry[]
    try {
      entries = await deps.fetchTree(current)
    } catch {
      continue
    }
    for (const entry of entries) {
      if (entry.type === 'dir') {
        queue.push(entry.path)
      } else if (deps.isSourceFile(entry.name)) {
        collected.push(entry.path)
      }
    }
  }
  return Array.from(new Set(collected))
}
