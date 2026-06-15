import { describe, it, expect } from 'vitest'
import { importFolder } from './folderImport'
import { makeIsSourceFile } from './sourceFiles'
import type { TreeEntry } from '../../types/api'

const tree: Record<string, TreeEntry[]> = {
  src: [
    { name: 'a.cpp', path: 'src/a.cpp', type: 'file' },
    { name: 'readme.md', path: 'src/readme.md', type: 'file' },
    { name: 'sub', path: 'src/sub', type: 'dir' },
  ],
  'src/sub': [
    { name: 'b.c', path: 'src/sub/b.c', type: 'file' },
    { name: 'notes.txt', path: 'src/sub/notes.txt', type: 'file' },
  ],
}

describe('importFolder', () => {
  it('recursively collects source files filtered by extension', async () => {
    const result = await importFolder('src', {
      fetchTree: (path) => Promise.resolve(tree[path] ?? []),
      isSourceFile: makeIsSourceFile('cpp'),
    })
    expect([...result].sort()).toEqual(['src/a.cpp', 'src/sub/b.c'])
  })

  it('skips subdirectories whose fetch fails', async () => {
    const result = await importFolder('src', {
      fetchTree: (path) =>
        path === 'src/sub'
          ? Promise.reject(new Error('boom'))
          : Promise.resolve(tree[path] ?? []),
      isSourceFile: makeIsSourceFile('cpp'),
    })
    expect(result).toEqual(['src/a.cpp'])
  })
})
