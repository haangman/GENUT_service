/* 한/영 전환 i18n. 다크 모드(useTheme)처럼 헤더 버튼으로 토글한다.
 *
 * - 한국어 문구 자체를 키로 쓰고, EN 사전에 영문 번역을 둔다(누락 시 한국어 그대로 —
 *   안전한 폴백). 동적 값은 `{name}` 플레이스홀더로 치환한다.
 * - 기본 언어는 한국어. 선택은 localStorage('lang')에 저장된다.
 * - Provider 없이 렌더되면(단위 테스트 등) 한국어로 동작한다.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'

export type Lang = 'ko' | 'en'

// 한국어 문구(키) → 영어 번역. UI에 보이는 문구만 담는다(서버 데이터는 그대로).
const EN: Record<string, string> = {
  // 네비게이션 / 페이지 제목·설명
  '프로덕트 등록': 'Product Registration',
  'GENUT 등록': 'GENUT Registration',
  '수동 실행 요청': 'Manual Run Request',
  '수동 실행 이력': 'Manual Run History',
  '자동 실행 이력': 'Auto Run History',
  '테스트 파일 현황': 'Test File Status',
  터미널: 'Terminal',
  'GENUT SERVICE가 실행 중인 환경의 셸에서 명령을 실행·디버깅한다.':
    'Run and debug commands in the shell of the environment where GENUT SERVICE is running.',
  '터미널을 사용할 수 없습니다.': 'Terminal is not available.',
  '+ 새 터미널': '+ New terminal',
  '탭 닫기 {title}': 'Close tab {title}',
  '열린 터미널이 없습니다. 새 터미널을 여세요.': 'No open terminals. Open a new one.',
  '\r\n[연결이 종료되었습니다]\r\n': '\r\n[Connection closed]\r\n',
  '테스트 생성 대상 프로덕트를 등록/관리한다.':
    'Register and manage products targeted for test generation.',
  'GENUT 인스턴스(=워커)를 등록/관리하고, 워커 상태·요청 큐를 본다.':
    'Register/manage GENUT instances (workers) and view worker status and the request queue.',
  '프로덕트를 선택하고 소스 파일을 구성해 GENUT 테스트 생성을 요청한다.':
    'Select a product, compose source files, and request GENUT test generation.',
  '수동 실행 요청 페이지로 제출한 job 이력/로그를 본다.':
    'View history/logs of jobs submitted from the Manual Run Request page.',
  '자동 실행 프로덕트별 job 이력(변경 감지/스캔/GENUT)을 본다.':
    'View job history per auto-run product (diff detection / scan / GENUT).',
  '프로덕트별 테스트 생성 대상 파일과 생성된 테스트(성공/실패) 현황을 본다. 같은 이름의 프로덕트는 합산해서 보여준다.':
    'View target files and generated tests (passed/failed) per product. Same-named products are aggregated.',

  // 테마/언어 토글
  '다크 모드로 전환': 'Switch to dark mode',
  '라이트 모드로 전환': 'Switch to light mode',
  '다크 모드': 'Dark mode',
  '라이트 모드': 'Light mode',
  '영어로 전환': 'Switch to English',
  '한국어로 전환': 'Switch to Korean',

  // 공통
  저장: 'Save',
  닫기: 'Close',
  수정: 'Edit',
  삭제: 'Delete',
  제거: 'Remove',
  제출: 'Submit',
  이름: 'Name',
  상태: 'Status',
  결과: 'Result',
  종류: 'Kind',
  제품: 'Product',
  모드: 'Mode',
  시스템: 'System',
  워커: 'Workers',
  '요청 큐': 'Request Queue',
  보기: 'View',
  코드: 'Code',
  로그: 'Log',
  분: 'min',
  시간: 'hr',
  일: 'day',
  '불러오는 중…': 'Loading…',
  자동: 'auto',
  수동: 'manual',
  '← 뒤로': '← Back',
  프로덕트: 'Products',
  '테스트 파일': 'Test file',
  '저장에 실패했습니다.': 'Save failed.',
  '삭제에 실패했습니다.': 'Delete failed.',
  '{name} 프로덕트를 삭제할까요? 관련 job 이력도 함께 삭제됩니다.':
    'Delete product {name}? Its job history will be deleted too.',
  '{name} GENUT를 삭제할까요? 종료된 job 이력은 남습니다.':
    'Delete GENUT {name}? Finished job history is kept.',
  '실행 중이거나 대기 중인 job이 있는 프로덕트는 삭제할 수 없다':
    'A product with queued or running jobs cannot be deleted',
  '실행 중인 job이 배정된 GENUT는 삭제할 수 없다':
    'A GENUT with a running job assigned cannot be deleted',

  // job 테이블 / 로그
  '제출 시각': 'Submitted',
  '시작 시간': 'Started',
  '종료 시간': 'Finished',
  '총 수행 시간': 'Duration',
  '강제 종료': 'Force kill',
  '종료 중…': 'Killing…',
  '삭제 중…': 'Deleting…',
  'job #{id}을 삭제할까요? 로그도 함께 삭제됩니다.':
    'Delete job #{id}? Its logs will be deleted as well.',
  '완료된 job만 삭제할 수 있다 — 실행 중이면 먼저 강제 종료하세요':
    'Only finished jobs can be deleted — force-kill a running job first',
  '진행 중': 'running',
  'job 이력이 없습니다.': 'No job history.',
  '더 보기 ({visible}/{total})': 'Show more ({visible}/{total})',
  'job #{id} 로그': 'Job #{id} log',
  '(완료)': '(finished)',
  '· 실행 중…': '· running…',
  '로그 저장': 'Save log',
  재수행: 'Rerun',
  '재수행 중…': 'Rerunning…',
  '로그 없음': 'No log',
  '이전 {count}줄 표시 생략 — 전체는 로그 저장으로 받으세요':
    'First {count} lines hidden — use Save log to get everything',
  '재수행 요청 완료 (새 job #{id})': 'Rerun requested (new job #{id})',
  '재수행 요청에 실패했습니다.': 'Rerun request failed.',
  '강제 종료 요청에 실패했습니다. 페이지를 새로고침(Ctrl+Shift+R) 후 다시 시도하세요.':
    'Force kill request failed. Refresh the page (Ctrl+Shift+R) and try again.',
  스캔: 'Scan',
  '변경 감지': 'Diff detection',
  완료: 'Done',
  '실패로 실행이 중단됨.': 'Stopped due to a failure.',
  '서버 재시작으로 실행이 중단됨.': 'Interrupted by a server restart.',
  '강제 종료됨': 'Force killed',

  // 자동 실행 이력
  '전체 {total}건': '{total} total',
  ' · 외 {count}건 보기': ' · view {count} more',
  '주기 {seconds}s': 'every {seconds}s',
  '▶ 지금 실행': '▶ Run now',
  '요청 중…': 'Requesting…',
  '주기와 무관하게 지금 실행 (변경 감지 → 누락 테스트 스캔)':
    'Run now regardless of the interval (diff detection → missing-test scan)',
  '실행 이력이 없습니다.': 'No run history.',
  '자동 실행 프로덕트가 없습니다.': 'No auto-run products.',
  '실행 요청에 실패했습니다. 이미 진행 중인 자동 실행이 있는지 확인하세요.':
    'Run request failed. Check whether an auto run is already in progress.',

  // 페이지네이션
  '페이지 이동': 'Pagination',
  '첫 페이지': 'First page',
  '이전 페이지': 'Previous page',
  '다음 페이지': 'Next page',
  '마지막 페이지': 'Last page',

  // GENUT 등록
  '+ 새 GENUT': '+ New GENUT',
  '새 GENUT': 'New GENUT',
  '수정: {name}': 'Edit: {name}',
  '대기(프로덕트 사용 중)': 'Waiting (product busy)',
  '대기 중인 요청이 없습니다.': 'No pending requests.',
  '코드 저장 경로 (선택, 절대/상대)': 'Code checkout path (optional, absolute/relative)',
  '코드 저장 경로 (절대 경로)': 'Code checkout path (absolute)',
  '코드 저장 경로를 입력하세요': 'Enter the code checkout path',
  '코드 저장 경로는 절대 경로로 입력하세요': 'The code checkout path must be absolute',
  'ASSURE repo URL (선택)': 'ASSURE repo URL (optional)',
  '변경 시에만 입력 (비우면 기존 값 유지)': 'Enter only to change (blank keeps current)',
  '실행 명령 (run_command)': 'Run command (run_command)',
  'LLM_MODEL (.env로 전달)': 'LLM_MODEL (passed via .env)',
  '이름을 입력하세요': 'Enter a name',
  'repo URL을 입력하세요': 'Enter the repo URL',
  'repo ref를 입력하세요': 'Enter the repo ref',
  'API 키를 입력하세요': 'Enter the API key',
  '시스템 이름을 입력하세요': 'Enter the system name',
  '1 이상이어야 합니다': 'Must be 1 or greater',
  '실행 명령을 입력하세요': 'Enter the run command',

  // 프로덕트 등록
  '+ 새 프로덕트': '+ New product',
  '새 프로덕트': 'New product',
  '목록을 불러오지 못했습니다.': 'Failed to load the list.',
  프로젝트: 'Project',
  '프로덕트 ID': 'Product ID',
  다운로드: 'Download',
  '다운로드 중…': 'Downloading…',
  '다운로드 성공': 'Download succeeded',
  '다운로드 실패': 'Download failed',
  '이 경로로 git 코드를 받아온다 (없으면 clone, 있으면 업데이트)':
    'Fetch the git code into this path (clone if missing, update otherwise)',
  '클론 완료': 'Clone complete',
  '업데이트 완료': 'Update complete',
  실행: 'Run',
  '실행 중…': 'Running…',
  '실행 로그': 'Execution log',
  지우기: 'Clear',
  '코드 저장 경로에서 이 명령을 실행해 본다': 'Try this command in the code checkout path',
  '명령 실행에 실패했습니다.': 'Failed to run the command.',
  '다운로드/실행 버튼의 로그가 여기에 표시됩니다.':
    'Logs from the download/run buttons appear here.',
  '프로덕트 ID를 입력하세요': 'Enter the product ID',
  'git URL을 입력하세요': 'Enter the git URL',
  'git ref를 입력하세요': 'Enter the git ref',
  'compile_commands.json 폴더 경로를 입력하세요': 'Enter the compile_commands.json folder path',
  '테스트 출력 폴더 경로를 입력하세요': 'Enter the test output folder path',
  'configure 명령을 입력하세요': 'Enter the configure command',
  'build 명령을 입력하세요': 'Enter the build command',
  'test 실행 명령을 입력하세요': 'Enter the test run command',
  '내용을 입력하세요': 'Enter the content',
  '주기를 입력하세요': 'Enter the interval',
  "자동 실행 모드의 ID는 'auto'로 시작해야 합니다":
    "In auto-run mode the ID must start with 'auto'",
  '자동 실행 모드 (주기마다 자동으로 테스트 생성)':
    'Auto-run mode (generate tests automatically on an interval)',
  '{label} (auto 로 시작)': '{label} (starts with auto)',
  'compile_commands.json 폴더(상대)': 'compile_commands.json folder (relative)',
  '테스트 출력 폴더(상대)': 'Test output folder (relative)',
  '테스트 모드': 'Test mode',
  '(c·cpp=gtest, kunit은 추후)': '(c·cpp=gtest, kunit later)',
  '자동 수행 주기': 'Auto-run interval',
  '테스트 대상 제외 패턴 (한 줄에 하나, 예:': 'Exclude patterns for targets (one per line, e.g.',
  'compile_commands.json 대상 파일 중 path가 이 글롭에 맞으면 제외됩니다.':
    'Files from compile_commands.json whose path matches these globs are excluded.',
  '대상 파일 미리보기 ({included}/{total})': 'Target file preview ({included}/{total})',
  '스캔 중…': 'Scanning…',
  '코드 저장 경로와 compile_commands.json 폴더를 입력하면 대상 파일이 표시됩니다.':
    'Enter the code checkout path and the compile_commands.json folder to list target files.',
  제외됨: 'Excluded',
  ' (패턴)': ' (pattern)',
  복원: 'Restore',
  제외: 'Exclude',
  'CMakeLists.txt 양식 (placeholder': 'CMakeLists.txt template (placeholder',
  '→ 파일 이름으로 치환)': '→ replaced with the file name)',
  '패치 (순서대로 적용)': 'Patches (applied in order)',
  '패치 {n} 이름': 'Patch {n} name',
  '패치 {n} 내용': 'Patch {n} content',
  '패치 추가': 'Add patch',
  업데이트: 'Refresh',
  'compile_commands.json과 제외 패턴 기준으로 다시 스캔한다 (수동 제외/복원 초기화)':
    'Re-scan from compile_commands.json and the exclude patterns (clears manual include/exclude)',
  '코드 업데이트 방식': 'Code update mode',
  'reset — 원격 최신 강제 일치 (로컬 커밋 삭제)':
    'reset — force-match remote latest (drops local commits)',
  'rebase — 로컬 커밋 유지 (충돌 시 작업 실패)':
    'rebase — keep local commits (job fails on conflict)',
  'Gerrit change 주소': 'Gerrit change URL',
  'Gerrit change 주소 또는 번호 (예: https://…/+/1234, 1234/5)':
    'Gerrit change URL or number (e.g. https://…/+/1234, 1234/5)',
  가져오기: 'Fetch',
  '가져오는 중…': 'Fetching…',
  'Gerrit 가져오기': 'Fetch from Gerrit',
  '패치 행 추가': 'Patch row added',
  'Gerrit 패치를 가져오지 못했습니다.': 'Failed to fetch the Gerrit patch.',
  'Git URL로 change ref를 받아 패치로 추가한다 (코드 다운로드 후 사용 가능)':
    'Fetches the change ref via the Git URL and adds it as a patch (requires downloaded code)',

  // 테스트 파일 현황
  새로고침: 'Refresh',
  '갱신 중…': 'Refreshing…',
  '마지막 갱신 {time}': 'Last updated {time}',
  '등록 ID': 'Registered IDs',
  '대상 파일 수': 'Target files',
  '총 테스트파일 수': 'Total test files',
  '총 테스트 케이스 수': 'Total test cases',
  '실패 수': 'Failures',
  '등록된 프로덕트가 없습니다.': 'No registered products.',
  '현황을 불러오지 못했습니다.': 'Failed to load the status.',
  '대상 파일 {count}': 'Target files {count}',
  '총 테스트파일 {count}': 'Test files {count}',
  '총 테스트 케이스 {count}': 'Test cases {count}',
  '총 실패 {count}': 'Failures {count}',
  파일명: 'File name',
  '테스트 파일 수': 'Test files',
  '테스트 케이스 수': 'Test cases',
  '테스트 파일명': 'Test file name',
  '테스트 삭제': 'Delete tests',
  '{name} 테스트 파일을 삭제할까요?': 'Delete the test file {name}?',
  '{name}의 테스트 {count}개(실패 포함)를 모두 삭제할까요?':
    'Delete all {count} tests of {name} (including failed ones)?',
  '생성 성공': 'Succeeded',
  '생성 실패': 'Failed',
  '생성에 성공한 테스트 파일이 없습니다.': 'No successfully generated test files.',
  '실패한 테스트 파일이 없습니다.': 'No failed test files.',
  '테스트 생성 대상 파일이 없습니다.': 'No target files for test generation.',
  '생성 로그': 'Generation log',
  '테스트 코드': 'Test code',
  '표시할 내용이 없습니다.': 'Nothing to display.',
  '파일을 불러오지 못했습니다.': 'Failed to load the file.',

  // 수동 실행 요청
  '요청이 접수되었습니다. job #{id}': 'Request accepted. Job #{id}',
  '프로덕트를 선택하세요.': 'Select a product.',
  '프로덕트 선택…': 'Select a product…',
  '함수명 (선택)': 'Function name (optional)',
  'compile_commands 검사': 'Check compile_commands',
  '선택이 변경되었습니다. 다시 검사하세요.': 'Selection changed — check again.',
  '포함 ({count})': 'Included ({count})',
  '제외 — compile_commands.json에 없음 ({count})':
    'Excluded — not in compile_commands.json ({count})',
  '제출에 실패했습니다.': 'Submit failed.',
  '선택한 파일 ({count})': 'Selected files ({count})',
  '아직 선택한 파일이 없습니다.': 'No files selected yet.',
  '폴더 가져오기': 'Import folder',
  '트리 로딩…': 'Loading tree…',
  '트리를 불러오지 못했습니다.': 'Failed to load the tree.',
}

export type TranslateParams = Record<string, string | number>

/** 순수 번역 함수: 한국어 키 → 현재 언어 문구(+ `{name}` 치환). 미등록 키는 그대로. */
export function translate(lang: Lang, key: string, params?: TranslateParams): string {
  const template = lang === 'en' ? EN[key] ?? key : key
  if (!params) return template
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in params ? String(params[name]) : match,
  )
}

function initialLang(): Lang {
  try {
    return localStorage.getItem('lang') === 'en' ? 'en' : 'ko'
  } catch {
    return 'ko'
  }
}

const LangContext = createContext<{ lang: Lang; toggle: () => void }>({
  lang: 'ko',
  toggle: () => {},
})

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>(initialLang)
  useEffect(() => {
    try {
      localStorage.setItem('lang', lang)
    } catch {
      /* 저장 불가(프라이빗 모드 등)는 무시 */
    }
  }, [lang])
  const toggle = useCallback(() => setLang((current) => (current === 'ko' ? 'en' : 'ko')), [])
  return <LangContext.Provider value={{ lang, toggle }}>{children}</LangContext.Provider>
}

/** 현재 언어와 토글, 그리고 바인딩된 t()를 반환한다. Provider 밖에서는 한국어 고정. */
export function useLang() {
  const { lang, toggle } = useContext(LangContext)
  const t = useCallback(
    (key: string, params?: TranslateParams) => translate(lang, key, params),
    [lang],
  )
  return { lang, toggle, t }
}
