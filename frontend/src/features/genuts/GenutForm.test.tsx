import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { GenutForm } from './GenutForm'
import type { GenutFormValues } from './genutSchema'

const VALID: GenutFormValues = {
  name: 'g1',
  repo_url: 'https://example.com/genut.git',
  assure_repo_url: '',
  repo_ref: 'main',
  ds_assist_credential_key: 'secret',
  ds_assist_user_id: 'user-1',
  ds_assist_send_system_name: 'sys-A',
  max_attempts: 10,
  run_command: 'python -m genut',
  llm_model: 'gptOss',
  code_path: '',
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
    expect(values.ds_assist_user_id).toBe('user-1')
    expect(values.max_attempts).toBe(10)
  })

  it('renders the DS_ASSIST_USER_ID input', () => {
    render(<GenutForm onSubmit={vi.fn()} />)
    expect(screen.getByLabelText('DS_ASSIST_USER_ID')).toBeInTheDocument()
  })

  it('renders the ASSURE repo URL input', () => {
    render(<GenutForm onSubmit={vi.fn()} />)
    expect(screen.getByLabelText('ASSURE repo URL (선택)')).toBeInTheDocument()
  })

  it('LLM_MODEL 선택은 기본 gptOss이고 SSCR_SE로 바꿔 제출할 수 있다', async () => {
    const onSubmit = vi.fn()
    render(<GenutForm onSubmit={onSubmit} defaultValues={VALID} />)
    const select = screen.getByLabelText('LLM_MODEL (.env로 전달)') as HTMLSelectElement
    expect(select.value).toBe('gptOss') // 기본값

    await userEvent.selectOptions(select, 'SSCR_SE')
    await userEvent.click(screen.getByRole('button', { name: '저장' }))
    expect(onSubmit).toHaveBeenCalledTimes(1)
    expect(onSubmit.mock.calls[0][0].llm_model).toBe('SSCR_SE')
  })
})
