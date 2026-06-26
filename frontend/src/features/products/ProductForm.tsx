import { useFieldArray, useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { EMPTY_PRODUCT_FORM, productFormSchema, type ProductFormValues } from './productSchema'

type TextFieldName =
  | 'name'
  | 'product_code'
  | 'git_url'
  | 'git_ref'
  | 'compile_db_rel'
  | 'out_tests_rel'
  | 'cmake_configure_cmd'
  | 'cmake_build_cmd'
  | 'test_run_cmd'
  | 'code_path'

const TEXT_FIELDS: { name: TextFieldName; label: string }[] = [
  { name: 'name', label: '이름' },
  { name: 'product_code', label: '프로덕트 ID' },
  { name: 'code_path', label: '코드 저장 경로 (선택, 절대/상대)' },
  { name: 'git_url', label: 'Git URL' },
  { name: 'git_ref', label: 'Git ref' },
  { name: 'compile_db_rel', label: 'compile_commands.json 폴더(상대)' },
  { name: 'out_tests_rel', label: '테스트 출력 폴더(상대)' },
  { name: 'cmake_configure_cmd', label: 'CMAKE_CONFIGURE_CMD' },
  { name: 'cmake_build_cmd', label: 'CMAKE_BUILD_CMD' },
  { name: 'test_run_cmd', label: 'TEST_RUN_CMD' },
]

const inputClass = 'input'

interface ProductFormProps {
  onSubmit: (values: ProductFormValues) => void
  submitting?: boolean
  defaultValues?: Partial<ProductFormValues>
}

export function ProductForm({ onSubmit, submitting, defaultValues }: ProductFormProps) {
  const {
    register,
    handleSubmit,
    control,
    formState: { errors },
  } = useForm<ProductFormValues>({
    resolver: zodResolver(productFormSchema),
    defaultValues: { ...EMPTY_PRODUCT_FORM, ...defaultValues },
  })
  const { fields, append, remove } = useFieldArray({ control, name: 'patches' })

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="card space-y-4 p-5">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {TEXT_FIELDS.map((field) => (
          <div key={field.name}>
            <label htmlFor={field.name} className="label">
              {field.label}
            </label>
            <input id={field.name} className={inputClass} {...register(field.name)} />
            {errors[field.name] ? (
              <p role="alert" className="mt-1 text-xs text-danger-fg">
                {errors[field.name]?.message}
              </p>
            ) : null}
          </div>
        ))}

        <div>
          <label htmlFor="test_generation_mode" className="label">
            테스트 모드
          </label>
          <select
            id="test_generation_mode"
            className={inputClass}
            {...register('test_generation_mode')}
          >
            <option value="c">c</option>
            <option value="cpp">cpp</option>
            <option value="kunit">kunit</option>
          </select>
        </div>
      </div>

      <div>
        <label htmlFor="exclude_patterns" className="label">
          테스트 대상 제외 패턴 (한 줄에 하나, 예: <code className="font-mono">*test*</code>)
        </label>
        <textarea
          id="exclude_patterns"
          className={`${inputClass} min-h-[72px] font-mono`}
          placeholder={'*test*\n*/legacy/*'}
          {...register('exclude_patterns')}
        />
        <p className="mt-1 text-xs text-subtle">
          compile_commands.json 대상 파일 중 path가 이 글롭에 맞으면 현황에서 제외됩니다.
        </p>
      </div>

      <fieldset className="rounded-lg border border-border p-4">
        <legend className="px-1.5 text-sm font-medium text-fg">패치 (순서대로 적용)</legend>
        {fields.map((field, index) => (
          <div key={field.id} className="mb-3 space-y-1.5 border-b border-dashed border-border pb-3">
            <input
              aria-label={`패치 ${index + 1} 이름`}
              className={inputClass}
              placeholder="이름"
              {...register(`patches.${index}.name`)}
            />
            <textarea
              aria-label={`패치 ${index + 1} 내용`}
              className={`${inputClass} min-h-[72px] font-mono`}
              placeholder="unified diff"
              {...register(`patches.${index}.content`)}
            />
            <button
              type="button"
              className="text-xs font-medium text-danger-fg transition hover:opacity-80"
              onClick={() => remove(index)}
            >
              삭제
            </button>
          </div>
        ))}
        <button type="button" className="link text-sm" onClick={() => append({ name: '', content: '' })}>
          패치 추가
        </button>
      </fieldset>

      <button type="submit" disabled={submitting} className="btn btn-primary px-5">
        저장
      </button>
    </form>
  )
}
