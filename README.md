# GENUT SERVICE

GENUT(테스트 자동생성 CLI 도구)를 **여러 워커로 병렬 실행**하여, 다수의 대상 프로덕트(C/C++/kunit)에 단위 테스트를 생성·관리하는 서비스다.

- **백엔드**: Python 3.12 · FastAPI · SQLAlchemy 2.0(SQLite→Postgres) · Alembic · 자체 완결형 인앱 스케줄러(외부 브로커 없음)
- **프론트엔드**: React 18 + Vite + TypeScript · Tailwind · TanStack Query (한국어/영어 전환, 다크 모드)
- **실행 격리**: job마다 Docker 컨테이너(`USE_DOCKER=true`) 또는 호스트 실행(기본)
- 원격: https://github.com/haangman/GENUT_service (main, public)

## 주요 기능

| 페이지 | 설명 |
|--------|------|
| 프로덕트 등록 | 테스트 생성 대상 repo 등록/수정. **프로젝트**(Ulysses/Thetis, 기본 Ulysses) 선택, 코드 저장 경로 **다운로드 버튼**(git clone/pull + 성공/실패 표시). **자동 실행 모드**(주기 실행) 지원 — 대상 파일 미리보기·제외 패턴·CMakeLists 양식·패치 관리 |
| GENUT 등록 | GENUT 인스턴스(=워커) 등록(repo, 자격증명, LLM_MODEL 등) + 워커 상태·요청 큐 실시간 보기 |
| 수동 실행 요청 | 프로젝트 선택 → 해당 프로젝트의 프로덕트 선택 → 파일 트리에서 소스 선택 → compile_commands 검사 → GENUT job 제출 |
| 수동 실행 이력 | 프로젝트 필터 + 수동 제출 job 이력/실시간 로그/재수행/강제 종료 (20개씩 게시판식 페이지네이션) |
| 자동 실행 이력 | 프로젝트 필터 + auto 프로덕트별 사이클 이력(변경 감지 → 누락 테스트 스캔 → 함수별 GENUT job) + ▶ 지금 실행 |
| 테스트 파일 현황 | 프로젝트 필터 + 프로덕트(이름별 합산) → 대상 파일 → 생성 테스트(성공/실패) 드릴다운 + 코드/로그 뷰어. **백그라운드 스냅샷** 기반으로 즉시 응답 |

**독립 테스트 현황 서버**: `genut-service serve-status`(기본 8001)로 테스트 파일 현황만 담은 읽기 전용 웹페이지를 별도 포트·별도 프로세스로 띄울 수 있다. 메인 서버가 내려가도 마지막 스냅샷을 계속 보여준다.

## 동작 개요

- **워커 모델**: 등록된 GENUT 1개 = 워커 1개. N개 등록 시 서로 다른 N개 프로덕트가 동시 실행된다. 한 프로덕트(**같은 프로젝트의 이름** 기준)는 동시에 1개 job만 실행되고 나머지는 대기한다 — 프로젝트가 다르면 같은 이름이라도 병렬 실행된다(프로젝트별로 코드가 분리되어 있다는 전제; 이 경우 code_path도 분리해서 등록한다).
- **job 실행**: 스케줄러(1초 tick)가 idle 워커에 queued job을 배정 → runner가 워크스페이스 준비(프로덕트 clone+패치, GENUT clone, `.env`, file-list) 후 GENUT CLI를 Host/Docker executor로 실행. 실행 중 로그는 웹에서 실시간 확인, 강제 종료 가능.
- **자동 실행(auto) 모드**: `auto`로 시작하는 프로덕트는 주기마다 ① 변경 감지(git diff → 수정 함수별 job) ② 누락 테스트 스캔(`<out>/<stem>/<함수>_Test.cpp` 존재 확인 → 누락 함수별 job)을 수행한다. 함수 추출은 우분투에서 `tools/func_extractor/<버전>/FunctionExtractor`(clang 기반)가 있으면 우선 사용하고, 없으면 내장 파서(C/C++/커널 드라이버 C 지원)를 쓴다.
- **테스트 현황 스냅샷**: 메인 서버의 백그라운드 리프레셔가 주기(기본 30초)마다 전체 현황을 미리 계산해 DB(`test_status_snapshots`)에 저장한다. 현황 페이지·독립 서버는 이를 읽어 즉시 응답한다(스냅샷이 없으면 실시간 스캔 폴백).

## 실행 방법 (백엔드, .venv)

PowerShell 기준 (Windows). bash면 활성화 줄만 `. .venv/Scripts/activate`로 바꾼다.

```powershell
# 1) 가상환경 생성·활성화
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2) 의존성 설치 (둘 중 하나)
pip install -r requirements.txt          # 런타임만 (실행용)
#   또는
pip install -r requirements-dev.txt      # 런타임 + 테스트 도구
#   또는 (권장) editable 설치 — `genut-service` 콘솔 명령까지 생성
pip install -e ".[dev]"

# 3) DB 마이그레이션 (테이블 생성; 기본 SQLite ./genut_service.db)
alembic upgrade head

# 4) (선택) 프론트엔드 빌드 — 서버가 frontend/dist 를 SPA로 함께 서빙
npm --prefix ./frontend install
npm --prefix ./frontend run build

# 5) 서버 실행 → http://127.0.0.1:8000
python -m genut_service serve --host 127.0.0.1 --port 8000
#   editable(`pip install -e .`) 설치 시: genut-service serve

# 5-1) (선택) 독립 테스트 현황 서버 → http://127.0.0.1:8001
#      메인 서버와 "같은 작업 디렉터리"(.env/DB)에서 실행한다
python -m genut_service serve-status --host 127.0.0.1 --port 8001

# 테스트
pytest                                   # 백엔드 (기본 -m "not docker and not slow")
npm --prefix ./frontend test             # 프론트엔드
```

> `pip install -r requirements.txt`는 의존성만 설치하므로, 패키지가 보이도록 **프로젝트 루트에서** `python -m genut_service ...`로 실행한다. 어디서든 `genut-service` 명령을 쓰려면 `pip install -e .`로 설치한다.

### Linux / WSL 에서의 차이

```bash
# 네이티브 Linux FS(~/)에 클론 권장 — /mnt/c 아래는 git/npm/도커 마운트가 느리다
git clone https://github.com/haangman/GENUT_service.git && cd GENUT_service
python3 -m venv .venv            # Ubuntu는 python3 (python 별칭이 없을 수 있음)
source .venv/bin/activate        # 바이너리는 .venv/bin/ (Windows는 .venv\Scripts\)
pip install -r requirements.txt
alembic upgrade head
npm --prefix ./frontend ci && npm --prefix ./frontend run build
python3 -m genut_service serve --host 127.0.0.1 --port 8000
```

- **`python` vs `python3`**: Linux에선 `python`이 없을 수 있다. 서버는 `python3 -m genut_service`로 실행하고, **GENUT 등록 시 `run_command`도 `python3 ...`로** 지정한다(예: `python3 -m genut`). `python-is-python3` 패키지를 깔면 `python`도 쓸 수 있다.
- **Docker가 실제로 동작**: WSL2/Linux에선 `docker`가 보통 가용하므로 `.env`의 `USE_DOCKER=true`로 컨테이너-per-job 실행이 가능하고(kunit/C·C++ 빌드에 유리), `pytest -m docker`도 실제로 돈다(이미지 필요). Windows(도커 없음)에선 호스트 실행 + docker 테스트 자동 skip.
- **FunctionExtractor**: 우분투 20.04/22.04/24.04에서 `tools/func_extractor/<XX_YY>/FunctionExtractor` 실행파일이 있으면 auto 모드의 함수 추출에 우선 사용된다(`chmod +x` 필요). 없으면 내장 파서로 동작한다.
- **인코딩 함정 없음**: cp949 관련 문제(BOM/requirements 한글 주석)는 Windows-한국어 로케일 특유다. Linux(UTF-8)에선 발생하지 않고, git CRLF 경고도 없다.
- 워크스페이스(`WORKSPACE_ROOT`)와 작업 디렉터리는 네이티브 Linux FS에 두자(도커 bind-mount 성능/정합성).

## 주요 명령어

| 용도 | 명령어 |
|------|--------|
| 백엔드 서버 | `genut-service serve` (http://127.0.0.1:8000) |
| 독립 테스트 현황 서버 | `genut-service serve-status` (http://127.0.0.1:8001, 읽기 전용) |
| 백엔드 테스트 | `pytest` / 도커 포함 `pytest -m docker` |
| DB 마이그레이션 | `alembic upgrade head` (스키마 변경 시 `alembic revision --autogenerate -m "..."`) |
| 프론트 개발 서버 | `npm --prefix ./frontend run dev` (5173, `/api`→8000 프록시) |
| 프론트 테스트 / 빌드 | `npm --prefix ./frontend test` / `run build` → `frontend/dist` |

## 설정 (.env)

`.env.example`을 `.env`로 복사해 수정한다. 주요 값(전체는 `genut_service/config.py`):

| 키 | 기본값 | 설명 |
|----|--------|------|
| `DB_URL` | `sqlite:///./genut_service.db` | DB 연결 문자열 (Postgres 전환 시 교체) |
| `WORKSPACE_ROOT` | `./_workspaces` | job/프로덕트 체크아웃 루트 |
| `GENUT_RUN_TIMEOUT` | `1800` | GENUT CLI 실행 타임아웃(초) |
| `GIT_TIMEOUT` | `300` | git clone/fetch 타임아웃(초) |
| `SCHEDULER_INTERVAL` | `1.0` | 스케줄러 tick 간격(초) |
| `TEST_STATUS_REFRESH_INTERVAL` | `30.0` | 테스트 현황 스냅샷 갱신 주기(초, 0 이하 = 비활성) |
| `TEST_STATUS_CACHE_TTL` | `30.0` | 현황 요약 폴백 캐시 TTL(초) |
| `JOB_EVENT_RETENTION_DAYS` | `14` | job 이벤트 로그 보존 기간(일) |
| `FUNC_EXTRACTOR_DIR` | `tools/func_extractor` | FunctionExtractor 배치 폴더(빈 값 = 내장 파서만) |
| `USE_DOCKER` / `DOCKER_*` | `false` | 컨테이너-per-job 실행 및 이미지/자원 설정 |

## 프로젝트 구조

```
genut_service/
├── main.py              # FastAPI 앱 팩토리, lifespan(스케줄러), 정적 서빙(SPA)
├── status_main.py       # 독립 테스트 현황 서버 앱(읽기 전용, status.html 서빙)
├── cli.py               # Typer CLI: serve / serve-status
├── config.py            # .env → Settings
├── db/{base,models}.py  # 엔진/세션(SQLite WAL), ORM 모델(+test_status_snapshots)
├── schemas/             # Pydantic 입출력
├── api/                 # 라우터 (products, files, jobs, genuts, workers, test_status)
├── services/            # 비즈니스 로직 (FastAPI 비의존) — auto_run/function_extractor/
│                        #   test_status(+snapshot) 등
├── scheduler/           # engine(claim/finish), lock, janitor, loop(+스냅샷 리프레셔), auto_tick
├── runner/              # genut_runner, worker, git_ops, env_builder, executors
└── docker/              # DockerExecutor, images/Dockerfile.runner
frontend/                # React 앱 (index.html=메인, status.html=독립 현황 엔트리)
tools/func_extractor/    # (선택) 우분투 버전별 FunctionExtractor 실행파일
tests/                   # unit/api/scheduler/runner/e2e + fake_genut(가상 GENUT)
```

## 코드 수정 후 웹페이지에 반영하기

핵심: 서버(`genut-service serve`)는 `frontend/dist`를 **요청마다 디스크에서 읽어** 서빙하므로 **프론트 재빌드는 서버 재시작이 필요 없지만**, **백엔드(파이썬) 코드 변경은 서버 재시작이 필요**하다(`--reload` 미사용 시).

| 수정 대상 | 운영형(8000 한 곳) | 개발형(Vite 5173, HMR) |
|-----------|-------------------|------------------------|
| 프론트엔드 | `npm --prefix ./frontend run build` → 브라우저 `Ctrl+Shift+R` | 저장 시 HMR 자동 반영 |
| 백엔드 | 서버 재시작(또는 `serve --reload`) | 동일 |
| DB 모델 변경 | `alembic revision --autogenerate -m "..."` → `alembic upgrade head` | 동일 |

개발형은 터미널 두 개로 `genut-service serve`(8000) + `npm --prefix ./frontend run dev`(5173)를 띄우고 **http://localhost:5173** 에 접속한다. 반영 후에는 규칙대로 **테스트 통과 확인 후 영어로 커밋**한다.

## 데모 프로덕트 (전체 검증용)

우분투 CMake 빌드 가능한 가상 프로덕트 2종이 public repo로 준비되어 있다. clone 직후 서비스가 인식하도록 포터블 `build/compile_commands.json`이 커밋되어 있다.

| repo | 언어 | 구성 |
|------|------|------|
| [haangman/genut-demo-c](https://github.com/haangman/genut-demo-c) | C | `demo_c/src` 3파일 10함수 (호출 체인 modulo→divide→subtract→add) |
| [haangman/genut-demo-cpp](https://github.com/haangman/genut-demo-cpp) | C++ (클래스) | `src` 3클래스 × 3메서드 (BankAccount/Vector2D/TextBuffer) |

등록 값 예시는 각 repo의 README 참고 (`compile_db_rel=build`, `out_tests_rel=unittests`, `cmake -S . -B build …`).

## Postgres 이식

코드는 DB 비의존(표준 SQLAlchemy, JSON 타입, String enum)이다.

```bash
pip install -e ".[postgres]"
export DB_URL=postgresql+psycopg://user:pass@host:5432/genut
alembic upgrade head
```

SQLite 전용 코드는 `db/base.py`의 PRAGMA(WAL 등, `sqlite` URL일 때만 적용)뿐이다.

## 문서

- 개발 규칙·명령어: [CLAUDE.md](./CLAUDE.md)
- 구현·검증 상세 기록: [PROGRESS.md](./PROGRESS.md)
