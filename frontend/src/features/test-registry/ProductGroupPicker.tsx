import { useQuery } from '@tanstack/react-query'
import { listProducts } from '../../api/products'
import { groupProductsByName, type ProductGroup } from './groupByName'

interface PickerProps {
  value: string | null
  onChange: (group: ProductGroup) => void
}

// 등록/다운로드 탭 공용. 같은 이름의 프로덕트는 1개로만 보인다(코드 공유).
export function ProductGroupPicker({ value, onChange }: PickerProps) {
  const { data } = useQuery({ queryKey: ['products'], queryFn: () => listProducts() })
  const groups = groupProductsByName(data?.items ?? [])

  return (
    <div>
      <label htmlFor="product-group-picker" className="text-sm font-medium">
        프로덕트
      </label>
      <select
        id="product-group-picker"
        className="mt-1 block w-72 rounded border border-gray-300 px-2 py-1 text-sm"
        value={value ?? ''}
        onChange={(event) => {
          const group = groups.find((g) => g.name === event.target.value)
          if (group) onChange(group)
        }}
      >
        <option value="" disabled>
          프로덕트 선택…
        </option>
        {groups.map((group) => (
          <option key={group.name} value={group.name}>
            {group.name}
          </option>
        ))}
      </select>
    </div>
  )
}
