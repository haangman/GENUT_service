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

const TEXT_FIELDS: { name: TextFieldName; label: string }[] = [
  { name: 'name', label: '이름' },
  { name: 'product_code', label: '프로덕트 ID' },
  { name: 'git_url', label: 'Git URL' },
  { name: 'git_ref', label: 'Git ref' },
  { name: 'compile_db_rel', label: 'compile_commands.json 폴더(상대)' },
  { name: 'out_tests_rel', label: '테스트 출력 폴더(상대)' },
  { name: 'cmake_configure_cmd', label: 'CMAKE_CONFIGURE_CMD' },
  { name: 'cmake_build_cmd', label: 'CMAKE_BUILD_CMD' },
  { name: 'test_run_cmd', label: 'TEST_RUN_CMD' },
]

const inputClass = 'mt-1 w-full rounded border border-gray-300 px-2 py-1 text-sm'

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
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-3 rounded border bg-white p-4">
      {TEXT_FIELDS.map((field) => (
        <div key={field.name}>
          <label htmlFor={field.name} className="text-sm font-medium">
            {field.label}
          </label>
          <input id={field.name} className={inputClass} {...register(field.name)} />
          {errors[field.name] ? (
            <p role="alert" className="mt-0.5 text-xs text-red-600">
              {errors[field.name]?.message}
            </p>
          ) : null}
        </div>
      ))}

      <div>
        <label htmlFor="test_generation_mode" className="text-sm font-medium">
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

      <fieldset className="rounded border border-gray-200 p-3">
        <legend className="px-1 text-sm font-medium">패치 (순서대로 적용)</legend>
        {fields.map((field, index) => (
          <div key={field.id} className="mb-2 space-y-1 border-b border-dashed pb-2">
            <input
              aria-label={`패치 ${index + 1} 이름`}
              className={inputClass}
              placeholder="이름"
              {...register(`patches.${index}.name`)}
            />
            <textarea
              aria-label={`패치 ${index + 1} 내용`}
              className={inputClass}
              placeholder="unified diff"
              {...register(`patches.${index}.content`)}
            />
            <button
              type="button"
              className="text-xs text-red-600"
              onClick={() => remove(index)}
            >
              삭제
            </button>
          </div>
        ))}
        <button
          type="button"
          className="text-sm text-blue-600"
          onClick={() => append({ name: '', content: '' })}
        >
          패치 추가
        </button>
      </fieldset>

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
