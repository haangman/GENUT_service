import { useLang } from '../lib/i18n'
import { PROJECTS } from '../lib/projects'
import type { Project } from '../types/api'

interface ProjectSelectProps {
  value: Project
  onChange: (project: Project) => void
  id?: string
}

// 목록/현황 페이지 공용 프로젝트 필터 select (폼 안에서는 RHF register를 직접 쓴다)
export function ProjectSelect({ value, onChange, id = 'project-select' }: ProjectSelectProps) {
  const { t } = useLang()
  return (
    <label className="flex items-center gap-2 text-sm text-fg" htmlFor={id}>
      <span className="font-medium">{t('프로젝트')}</span>
      <select
        id={id}
        className="input w-auto"
        value={value}
        onChange={(event) => onChange(event.target.value as Project)}
      >
        {PROJECTS.map((project) => (
          <option key={project} value={project}>
            {project}
          </option>
        ))}
      </select>
    </label>
  )
}
