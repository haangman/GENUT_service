import type { Project } from '../types/api'

// 프로젝트 선택지. 새 프로젝트 추가 시 여기(+ types/api.ts의 Project 유니온)와
// 백엔드 genut_service/enums.py의 Project enum에 함께 추가한다.
export const PROJECTS: readonly Project[] = ['Ulysses', 'Thetis'] as const

export const DEFAULT_PROJECT: Project = 'Ulysses'
