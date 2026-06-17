import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import {
  EMPTY_GENUT_FORM,
  genutEditSchema,
  genutFormSchema,
  type GenutFormValues,
} from './genutSchema'

const inputClass = 'mt-1 w-full rounded border border-gray-300 px-2 py-1 text-sm'

interface GenutFormProps {
  onSubmit: (values: GenutFormValues) => void
  submitting?: boolean
  defaultValues?: Partial<GenutFormValues>
  mode?: 'create' | 'edit'
}

export function GenutForm({ onSubmit, submitting, defaultValues, mode = 'create' }: GenutFormProps) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<GenutFormValues>({
    resolver: zodResolver(mode === 'edit' ? genutEditSchema : genutFormSchema),
    defaultValues: { ...EMPTY_GENUT_FORM, ...defaultValues },
  })

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-3 rounded border bg-white p-4">
      <div>
        <label htmlFor="name" className="text-sm font-medium">
          이름
        </label>
        <input id="name" className={inputClass} {...register('name')} />
        {errors.name ? (
          <p role="alert" className="mt-0.5 text-xs text-red-600">
            {errors.name.message}
          </p>
        ) : null}
      </div>

      <div>
        <label htmlFor="code_path" className="text-sm font-medium">
          코드 저장 경로 (선택, 절대/상대)
        </label>
        <input id="code_path" className={inputClass} {...register('code_path')} />
      </div>

      <div>
        <label htmlFor="repo_url" className="text-sm font-medium">
          GENUT repo URL
        </label>
        <input id="repo_url" className={inputClass} {...register('repo_url')} />
        {errors.repo_url ? (
          <p role="alert" className="mt-0.5 text-xs text-red-600">
            {errors.repo_url.message}
          </p>
        ) : null}
      </div>

      <div>
        <label htmlFor="assure_repo_url" className="text-sm font-medium">
          ASSURE repo URL (선택)
        </label>
        <input id="assure_repo_url" className={inputClass} {...register('assure_repo_url')} />
      </div>

      <div>
        <label htmlFor="repo_ref" className="text-sm font-medium">
          repo ref
        </label>
        <input id="repo_ref" className={inputClass} {...register('repo_ref')} />
      </div>

      <div>
        <label htmlFor="ds_assist_credential_key" className="text-sm font-medium">
          DS_ASSIST_CREDENTIAL_KEY
        </label>
        <input
          id="ds_assist_credential_key"
          type="password"
          className={inputClass}
          placeholder={mode === 'edit' ? '변경 시에만 입력 (비우면 기존 값 유지)' : ''}
          {...register('ds_assist_credential_key')}
        />
        {errors.ds_assist_credential_key ? (
          <p role="alert" className="mt-0.5 text-xs text-red-600">
            {errors.ds_assist_credential_key.message}
          </p>
        ) : null}
      </div>

      <div>
        <label htmlFor="ds_assist_user_id" className="text-sm font-medium">
          DS_ASSIST_USER_ID
        </label>
        <input
          id="ds_assist_user_id"
          className={inputClass}
          {...register('ds_assist_user_id')}
        />
      </div>

      <div>
        <label htmlFor="ds_assist_send_system_name" className="text-sm font-medium">
          DS_ASSIST_SEND_SYSTEM_NAME
        </label>
        <input
          id="ds_assist_send_system_name"
          className={inputClass}
          {...register('ds_assist_send_system_name')}
        />
        {errors.ds_assist_send_system_name ? (
          <p role="alert" className="mt-0.5 text-xs text-red-600">
            {errors.ds_assist_send_system_name.message}
          </p>
        ) : null}
      </div>

      <div>
        <label htmlFor="max_attempts" className="text-sm font-medium">
          max_attempts
        </label>
        <input
          id="max_attempts"
          type="number"
          className={inputClass}
          {...register('max_attempts')}
        />
      </div>

      <div>
        <label htmlFor="run_command" className="text-sm font-medium">
          실행 명령 (run_command)
        </label>
        <input id="run_command" className={inputClass} {...register('run_command')} />
      </div>

      <button
        type="submit"
        disabled={submitting}
        className="rounded bg-gray-900 px-4 py-1.5 text-sm font-medium text-white disabled:opacity-50"
      >
        저장
      </button>
    </form>
  )
}
