import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { GenutForm } from './GenutForm'
import type { GenutFormValues } from './genutSchema'

const VALID: GenutFormValues = {
  name: 'g1',
  repo_url: 'https://example.com/genut.git',
  repo_ref: 'main',
  ds_assist_credential_key: 'secret',
  ds_assist_send_system_name: 'sys-A',
  max_attempts: 10,
  run_command: 'python -m genut',
}

describe('GenutForm', () => {
  it('shows validation errors and does not submit when empty', async () => {
    const onSubmit = vi.fn()
    render(<GenutForm onSubmit={onSubmit} />)
    await userEvent.click(screen.getByRole('button', { name: '저장' }))
    expect(await screen.findByText('이름을 입력하세요')).toBeInTheDocument()
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('submits including the credential key', async () => {
    const onSubmit = vi.fn()
    render(<GenutForm onSubmit={onSubmit} defaultValues={VALID} />)
    await userEvent.click(screen.getByRole('button', { name: '저장' }))
    expect(onSubmit).toHaveBeenCalledTimes(1)
    const values = onSubmit.mock.calls[0][0]
    expect(values.name).toBe('g1')
    expect(values.ds_assist_credential_key).toBe('secret')
    expect(values.max_attempts).toBe(10)
  })
})
