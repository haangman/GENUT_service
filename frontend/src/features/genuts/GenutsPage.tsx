import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { PageHeader } from '../../components/PageHeader'
import { GenutForm } from './GenutForm'
import { createGenut, deleteGenut, listGenuts } from '../../api/genuts'
import type { GenutFormValues } from './genutSchema'

export function GenutsPage() {
  const queryClient = useQueryClient()
  const [showForm, setShowForm] = useState(false)

  const { data } = useQuery({ queryKey: ['genuts'], queryFn: () => listGenuts() })

  const createMut = useMutation({
    mutationFn: (values: GenutFormValues) => createGenut({ ...values, enabled: true }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['genuts'] })
      setShowForm(false)
    },
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => deleteGenut(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['genuts'] }),
  })

  return (
    <div>
      <PageHeader title="GENUT" description="GENUT 인스턴스(=워커)를 등록/관리한다." />

      <button
        className="mb-4 rounded border px-3 py-1.5 text-sm font-medium"
        onClick={() => setShowForm((value) => !value)}
      >
        {showForm ? '닫기' : '새 GENUT'}
      </button>

      {showForm ? (
        <div className="mb-4">
          <GenutForm onSubmit={(v) => createMut.mutate(v)} submitting={createMut.isPending} />
          {createMut.isError ? (
            <p role="alert" className="mt-2 text-sm text-red-600">
              등록에 실패했습니다.
            </p>
          ) : null}
        </div>
      ) : null}

      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b text-left text-gray-500">
            <th className="py-2">이름</th>
            <th>repo</th>
            <th>시스템</th>
            <th>max</th>
            <th>상태</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {data?.items.map((genut) => (
            <tr key={genut.id} className="border-b">
              <td className="py-2 font-medium">{genut.name}</td>
              <td className="text-gray-500">{genut.repo_url}</td>
              <td>{genut.ds_assist_send_system_name}</td>
              <td>{genut.max_attempts}</td>
              <td>{genut.worker_status}</td>
              <td>
                <button
                  className="text-xs text-red-600"
                  onClick={() => deleteMut.mutate(genut.id)}
                >
                  삭제
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
