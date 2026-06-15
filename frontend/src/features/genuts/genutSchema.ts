import { z } from 'zod'

export const genutFormSchema = z.object({
  name: z.string().min(1, '이름을 입력하세요'),
  repo_url: z.string().min(1, 'repo URL을 입력하세요'),
  repo_ref: z.string().min(1, 'repo ref를 입력하세요'),
  ds_assist_credential_key: z.string().min(1, 'API 키를 입력하세요'),
  ds_assist_send_system_name: z.string().min(1, '시스템 이름을 입력하세요'),
  max_attempts: z.coerce.number().int().min(1, '1 이상이어야 합니다'),
  run_command: z.string().min(1, '실행 명령을 입력하세요'),
})

// 수정용: credential key를 비워둘 수 있다(비우면 기존 값 유지).
export const genutEditSchema = genutFormSchema.extend({
  ds_assist_credential_key: z.string(),
})

export type GenutFormValues = z.infer<typeof genutFormSchema>

export const EMPTY_GENUT_FORM: GenutFormValues = {
  name: '',
  repo_url: '',
  repo_ref: 'main',
  ds_assist_credential_key: '',
  ds_assist_send_system_name: '',
  max_attempts: 10,
  run_command: 'python -m genut',
}
