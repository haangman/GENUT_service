import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { PageHeader } from '../../components/PageHeader'
import { GenutForm } from './GenutForm'
import { createGenut, deleteGenut, listGenuts, updateGenut } from '../../api/genuts'
import { listQueue, listWorkers } from '../../api/workers'
import type { GenutFormValues } from './genutSchema'
import type { Genut, GenutCreate } from '../../types/api'

function workerBadgeClass(status: string): string {
  switch (status) {
    case 'idle':
      return 'badge badge-success'
    case 'busy':
      return 'badge badge-primary'
    case 'error':
      return 'badge badge-danger'
    default:
      return 'badge badge-neutral'
  }
}

// 워커(=GENUT 인스턴스) 실시간 상태. 처리 용량을 요청 큐와 나란히 본다.
function WorkerGrid() {
  const { data } = useQuery({
    queryKey: ['workers'],
    queryFn: listWorkers,
    refetchInterval: 3000,
  })
  return (
    <section>
      <h2 className="mb-3 text-sm font-semibold text-fg">워커</h2>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
        {(data ?? []).map((worker) => (
          <div key={worker.id} className="card p-3.5 text-sm">
            <div className="flex items-center justify-between gap-2">
              <span className="truncate font-semibold text-fg">{worker.name}</span>
              <span className={workerBadgeClass(worker.worker_status)}>{worker.worker_status}</span>
            </div>
            {worker.current_job_id ? (
              <div className="mt-1.5 font-mono text-xs text-muted">job #{worker.current_job_id}</div>
            ) : null}
          </div>
        ))}
      </div>
    </section>
  )
}

// 워커 배정을 기다리는 요청 큐(수동 제출 + auto 생성 GENUT job).
function QueuePanel() {
  const { data } = useQuery({
    queryKey: ['queue'],
    queryFn: listQueue,
    refetchInterval: 3000,
  })
  return (
    <section>
      <h2 className="mb-3 text-sm font-semibold text-fg">요청 큐</h2>
      {(data ?? []).length === 0 ? (
        <p className="text-sm text-subtle">대기 중인 요청이 없습니다.</p>
      ) : (
        <ul className="space-y-2 text-sm">
          {data?.map((item) => (
            <li
              key={item.job_id}
              className="flex items-center gap-3 rounded-lg border border-border bg-surface px-3 py-2"
            >
              <span className="font-semibold text-fg">job #{item.job_id}</span>
              <span className="text-muted">product {item.product_id}</span>
              <span className={`badge ${item.origin === 'auto' ? 'badge-neutral' : 'badge-primary'}`}>
                {item.origin === 'auto' ? '자동' : '수동'}
              </span>
              {item.waiting_on_product ? (
                <span className="badge badge-warn ml-auto">대기(프로덕트 사용 중)</span>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function toFormValues(genut: Genut): Partial<GenutFormValues> {
  return {
    name: genut.name,
    repo_url: genut.repo_url,
    assure_repo_url: genut.assure_repo_url ?? '',
    repo_ref: genut.repo_ref,
    ds_assist_credential_key: '', // 비워두면 기존 값 유지
    ds_assist_user_id: genut.ds_assist_user_id ?? '',
    ds_assist_send_system_name: genut.ds_assist_send_system_name,
    max_attempts: genut.max_attempts,
    run_command: genut.run_command,
    llm_model: genut.llm_model ?? 'gptOss',
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
    const ds_assist_user_id = values.ds_assist_user_id.trim() || undefined
    const assure_repo_url = values.assure_repo_url.trim() || undefined
    if (editing) {
      const data: Record<string, unknown> = {
        ...values,
        code_path,
        ds_assist_user_id,
        assure_repo_url,
      }
      // 키를 비워두면 전송하지 않아 기존 값을 유지한다
      if (!values.ds_assist_credential_key) delete data.ds_assist_credential_key
      saveMut.mutate({ id: editing.id, data })
    } else {
      saveMut.mutate({
        id: null,
        data: { ...values, code_path, ds_assist_user_id, assure_repo_url, enabled: true },
      })
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
      <PageHeader
        title="GENUT 등록"
        description="GENUT 인스턴스(=워커)를 등록/관리하고, 워커 상태·요청 큐를 본다."
      />

      <button
        className={`mb-5 ${showForm ? 'btn' : 'btn btn-primary'}`}
        onClick={showForm ? closeForm : openCreate}
      >
        {showForm ? '닫기' : '+ 새 GENUT'}
      </button>

      {showForm ? (
        <div className="mb-6">
          <h3 className="mb-3 text-sm font-semibold text-fg">
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
            <p role="alert" className="mt-2 text-sm text-danger-fg">
              저장에 실패했습니다.
            </p>
          ) : null}
        </div>
      ) : null}

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-surface-2 text-left text-xs font-semibold uppercase tracking-wide text-muted">
              <th className="px-4 py-3">이름</th>
              <th className="px-4 py-3">repo</th>
              <th className="px-4 py-3">시스템</th>
              <th className="px-4 py-3">LLM</th>
              <th className="px-4 py-3">max</th>
              <th className="px-4 py-3">상태</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((genut) => (
              <tr key={genut.id} className="border-t border-border transition hover:bg-surface-hover">
                <td className="px-4 py-3 font-medium text-fg">{genut.name}</td>
                <td className="max-w-[260px] truncate px-4 py-3 text-muted">{genut.repo_url}</td>
                <td className="px-4 py-3 text-muted">{genut.ds_assist_send_system_name}</td>
                <td className="px-4 py-3 text-muted">{genut.llm_model ?? 'gptOss'}</td>
                <td className="px-4 py-3 text-muted">{genut.max_attempts}</td>
                <td className="px-4 py-3">
                  <span
                    className={`badge ${genut.worker_status === 'idle' ? 'badge-success' : genut.worker_status === 'busy' ? 'badge-primary' : 'badge-neutral'}`}
                  >
                    {genut.worker_status}
                  </span>
                </td>
                <td className="space-x-3 whitespace-nowrap px-4 py-3 text-right">
                  <button className="link text-xs" onClick={() => openEdit(genut)}>
                    수정
                  </button>
                  <button
                    className="text-xs font-medium text-danger-fg transition hover:opacity-80"
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

      <div className="mt-8 space-y-8">
        <WorkerGrid />
        <QueuePanel />
      </div>
    </div>
  )
}
