import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { PageHeader } from '../../components/PageHeader'
import { GenutForm } from './GenutForm'
import { createGenut, deleteGenut, listGenuts, updateGenut } from '../../api/genuts'
import type { GenutFormValues } from './genutSchema'
import type { Genut, GenutCreate } from '../../types/api'

function toFormValues(genut: Genut): Partial<GenutFormValues> {
  return {
    name: genut.name,
    repo_url: genut.repo_url,
    repo_ref: genut.repo_ref,
    ds_assist_credential_key: '', // 비워두면 기존 값 유지
    ds_assist_send_system_name: genut.ds_assist_send_system_name,
    max_attempts: genut.max_attempts,
    run_command: genut.run_command,
    code_path: genut.code_path ?? '',
  }
}

export function GenutsPage() {
  const queryClient = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<Genut | null>(null)

  const { data } = useQuery({ queryKey: ['genuts'], queryFn: () => listGenuts() })

  const saveMut = useMutation({
    mutationFn: ({ id, data }: { id: number | null; data: Record<string, unknown> }) =>
      id == null ? createGenut(data as unknown as GenutCreate) : updateGenut(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['genuts'] })
      setShowForm(false)
      setEditing(null)
    },
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => deleteGenut(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['genuts'] }),
  })

  const handleSubmit = (values: GenutFormValues) => {
    const code_path = values.code_path.trim() || undefined
    if (editing) {
      const data: Record<string, unknown> = { ...values, code_path }
      // 키를 비워두면 전송하지 않아 기존 값을 유지한다
      if (!values.ds_assist_credential_key) delete data.ds_assist_credential_key
      saveMut.mutate({ id: editing.id, data })
    } else {
      saveMut.mutate({ id: null, data: { ...values, code_path, enabled: true } })
    }
  }

  const openCreate = () => {
    setEditing(null)
    setShowForm(true)
  }
  const openEdit = (genut: Genut) => {
    setEditing(genut)
    setShowForm(true)
  }
  const closeForm = () => {
    setShowForm(false)
    setEditing(null)
  }

  return (
    <div>
      <PageHeader title="GENUT" description="GENUT 인스턴스(=워커)를 등록/관리한다." />

      <button
        className="mb-4 rounded border px-3 py-1.5 text-sm font-medium"
        onClick={showForm ? closeForm : openCreate}
      >
        {showForm ? '닫기' : '새 GENUT'}
      </button>

      {showForm ? (
        <div className="mb-4">
          <h3 className="mb-2 text-sm font-semibold">
            {editing ? `수정: ${editing.name}` : '새 GENUT'}
          </h3>
          <GenutForm
            key={editing?.id ?? 'new'}
            mode={editing ? 'edit' : 'create'}
            defaultValues={editing ? toFormValues(editing) : undefined}
            onSubmit={handleSubmit}
            submitting={saveMut.isPending}
          />
          {saveMut.isError ? (
            <p role="alert" className="mt-2 text-sm text-red-600">
              저장에 실패했습니다.
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
              <td className="space-x-2 whitespace-nowrap">
                <button className="text-xs text-blue-600" onClick={() => openEdit(genut)}>
                  수정
                </button>
                <button className="text-xs text-red-600" onClick={() => deleteMut.mutate(genut.id)}>
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
