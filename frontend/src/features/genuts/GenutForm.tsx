import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useLang } from '../../lib/i18n'
import {
  EMPTY_GENUT_FORM,
  genutEditSchema,
  genutFormSchema,
  type GenutFormValues,
} from './genutSchema'

const inputClass = 'input'

interface GenutFormProps {
  onSubmit: (values: GenutFormValues) => void
  submitting?: boolean
  defaultValues?: Partial<GenutFormValues>
  mode?: 'create' | 'edit'
}

export function GenutForm({ onSubmit, submitting, defaultValues, mode = 'create' }: GenutFormProps) {
  const { t } = useLang()
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<GenutFormValues>({
    resolver: zodResolver(mode === 'edit' ? genutEditSchema : genutFormSchema),
    defaultValues: { ...EMPTY_GENUT_FORM, ...defaultValues },
  })

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="card space-y-4 p-5">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="name" className="label">
            {t('이름')}
          </label>
          <input id="name" className={inputClass} {...register('name')} />
          {errors.name ? (
            <p role="alert" className="mt-1 text-xs text-danger-fg">
              {t(errors.name.message ?? '')}
            </p>
          ) : null}
        </div>

        <div>
          <label htmlFor="code_path" className="label">
            {t('코드 저장 경로 (선택, 절대/상대)')}
          </label>
          <input id="code_path" className={inputClass} {...register('code_path')} />
        </div>

        <div>
          <label htmlFor="repo_url" className="label">
            GENUT repo URL
          </label>
          <input id="repo_url" className={inputClass} {...register('repo_url')} />
          {errors.repo_url ? (
            <p role="alert" className="mt-1 text-xs text-danger-fg">
              {t(errors.repo_url.message ?? '')}
            </p>
          ) : null}
        </div>

        <div>
          <label htmlFor="assure_repo_url" className="label">
            {t('ASSURE repo URL (선택)')}
          </label>
          <input id="assure_repo_url" className={inputClass} {...register('assure_repo_url')} />
        </div>

        <div>
          <label htmlFor="repo_ref" className="label">
            repo ref
          </label>
          <input id="repo_ref" className={inputClass} {...register('repo_ref')} />
        </div>

        <div>
          <label htmlFor="ds_assist_credential_key" className="label">
            DS_ASSIST_CREDENTIAL_KEY
          </label>
          <input
            id="ds_assist_credential_key"
            type="password"
            className={inputClass}
            placeholder={mode === 'edit' ? t('변경 시에만 입력 (비우면 기존 값 유지)') : ''}
            {...register('ds_assist_credential_key')}
          />
          {errors.ds_assist_credential_key ? (
            <p role="alert" className="mt-1 text-xs text-danger-fg">
              {t(errors.ds_assist_credential_key.message ?? '')}
            </p>
          ) : null}
        </div>

        <div>
          <label htmlFor="ds_assist_user_id" className="label">
            DS_ASSIST_USER_ID
          </label>
          <input id="ds_assist_user_id" className={inputClass} {...register('ds_assist_user_id')} />
        </div>

        <div>
          <label htmlFor="ds_assist_send_system_name" className="label">
            DS_ASSIST_SEND_SYSTEM_NAME
          </label>
          <input
            id="ds_assist_send_system_name"
            className={inputClass}
            {...register('ds_assist_send_system_name')}
          />
          {errors.ds_assist_send_system_name ? (
            <p role="alert" className="mt-1 text-xs text-danger-fg">
              {t(errors.ds_assist_send_system_name.message ?? '')}
            </p>
          ) : null}
        </div>

        <div>
          <label htmlFor="max_attempts" className="label">
            max_attempts
          </label>
          <input id="max_attempts" type="number" className={inputClass} {...register('max_attempts')} />
        </div>

        <div>
          <label htmlFor="run_command" className="label">
            {t('실행 명령 (run_command)')}
          </label>
          <input id="run_command" className={inputClass} {...register('run_command')} />
        </div>

        <div>
          <label htmlFor="llm_model" className="label">
            {t('LLM_MODEL (.env로 전달)')}
          </label>
          <select id="llm_model" className={inputClass} {...register('llm_model')}>
            <option value="gptOss">gptOss</option>
            <option value="SSCR_SE">SSCR_SE</option>
          </select>
        </div>
      </div>

      <button type="submit" disabled={submitting} className="btn btn-primary px-5">
        {t('저장')}
      </button>
    </form>
  )
}
