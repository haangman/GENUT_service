import { describe, it, expect, beforeEach } from 'vitest'
import { useRequestBuilder } from './store'

beforeEach(() => useRequestBuilder.getState().reset())

describe('useRequestBuilder', () => {
  it('setProduct resets selection', () => {
    useRequestBuilder.getState().toggleFile('x')
    useRequestBuilder.getState().setProduct(1, 'c')
    const state = useRequestBuilder.getState()
    expect(state.productId).toBe(1)
    expect(state.mode).toBe('c')
    expect(state.selected).toEqual([])
  })

  it('toggleFile adds then removes', () => {
    useRequestBuilder.getState().toggleFile('a')
    expect(useRequestBuilder.getState().selected).toEqual(['a'])
    useRequestBuilder.getState().toggleFile('a')
    expect(useRequestBuilder.getState().selected).toEqual([])
  })

  it('addPaths unions, dedups, and marks compile result stale', () => {
    useRequestBuilder.getState().addPaths(['a', 'b', 'a'])
    expect([...useRequestBuilder.getState().selected].sort()).toEqual(['a', 'b'])
    expect(useRequestBuilder.getState().compileStale).toBe(true)
  })

  it('removeFile removes a path', () => {
    useRequestBuilder.getState().addPaths(['a', 'b'])
    useRequestBuilder.getState().removeFile('a')
    expect(useRequestBuilder.getState().selected).toEqual(['b'])
  })
})
