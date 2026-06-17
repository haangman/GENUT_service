# CLAUDE.md

이 파일은 [Claude Code](https://claude.com/claude-code)가 이 저장소에서 작업할 때 참고하는 가이드다.

## 프로젝트 개요

`GENUT_service`는 **GENUT(테스트 자동생성 CLI 도구)를 여러 워커로 병렬 실행**하여, 다수의 대상 프로덕트(C/C++/kunit)에 단위 테스트를 생성하는 서비스다.

- **GENUT**: 서비스에 repo로 등록되어 매 실행 시 최신 코드로 clone 후 CLI로 호출된다. CLI 옵션 `--file-list`(절대경로 txt)·`--compile-dp-path`·`--out-test-folder-path`·`--max-attempts`·`--debug`·`--enable-assure`·`--function-name`. 함수당 positive:negative 50:50 테스트 생성. `.env`로 `TEST_GENERATION_MODE`(c|cpp|kunit)·`DS_ASSIST_CREDENTIAL_KEY`·`DS_ASSIST_USER_ID`·`DS_ASSIST_SEND_SYSTEM_NAME`·`CMAKE_CONFIGURE_CMD`·`CMAKE_BUILD_CMD`·`TEST_RUN_CMD`를 받는다.
- **동시성**: 등록된 GENUT 1개 = 워커 1개. 한 프로덕트는 동시에 1개 job만(`product_locks` PK 배타). N개 GENUT → 서로 다른 N개 프로덕트 동시 실행. 동일 프로덕트 동시 요청은 1개만 실행, 나머지 대기.
- **실행 격리**: job마다 Docker 컨테이너(`use_docker=true`). 기본은 호스트 실행.

## 기술 스택

- **백엔드**: Python 3.12, FastAPI, SQLAlchemy 2.0(SQLite→Postgres), Alembic, pydantic-settings, Typer
- **프론트엔드**(`frontend/`): React 18 + Vite + TypeScript, React Router, TanStack Query, Zustand, React Hook Form + Zod, Tailwind, Vitest + RTL + MSW
- **인프라**: 자체 인앱 스케줄러(외부 브로커 없음) + Docker(컨테이너-per-job)

## 개발 환경 설정

```bash
python -m venv .venv
. .venv/Scripts/activate            # Windows bash. PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
cp .env.example .env                # 필요 시 값 수정
npm --prefix ./frontend install
```

## 주요 명령어

| 용도 | 명령어 |
|------|--------|
| 백엔드 테스트 | `pytest` (기본 `-m "not docker and not slow"`) |
| 도커 포함 테스트 | `pytest -m docker` (Docker 필요, 없으면 자동 skip) |
| DB 마이그레이션 | `alembic upgrade head` (스키마 변경 시 `alembic revision --autogenerate -m "..."`) |
| 백엔드 서버 | `genut-service serve` (http://127.0.0.1:8000) |
| 프론트 개발 서버 | `npm --prefix ./frontend run dev` (Vite, `/api`→127.0.0.1:8000 프록시) |
| 프론트 테스트 | `npm --prefix ./frontend test` |
| 프론트 빌드 | `npm --prefix ./frontend run build` → `frontend/dist` |

운영 시 `genut-service serve`가 `frontend/dist`를 정적 서빙(SPA fallback)하고 백그라운드 스케줄러를 돌린다.

## 프로젝트 구조

```
genut_service/
├── main.py              # FastAPI 앱 팩토리, lifespan(스케줄러), 정적 서빙
├── config.py            # .env → Settings
├── db/{base,models}.py  # 엔진/세션, ORM 모델
├── schemas/             # Pydantic 입출력
├── api/                 # 라우터 (products, files, jobs, genuts, workers)
├── services/            # 비즈니스 로직 (FastAPI 비의존)
├── scheduler/           # engine(claim/finish), lock, janitor, loop
├── runner/              # genut_runner, worker, git_ops, env_builder, executors, subprocess_util
└── docker/              # client(DockerExecutor), images/Dockerfile.runner
frontend/src/{lib,api,types,components,features/{request,products,genuts,workers}}
tests/                   # unit/api/scheduler/runner/e2e + fake_genut/ (가상 GENUT)
```

## 아키텍처 메모

- 계층: **api → services → db**. `scheduler`/`runner`는 FastAPI 비의존(HTTP 없이 단위테스트 가능).
- 스케줄러: 단일 writer가 `claim_jobs`(idle 워커↔queued job 배정, 프로덕트당 1개)와 `finish_job`(락 해제·워커 idle)을 수행. `product_locks.product_id` PK가 배타성을 보장.
- runner: 호스트에 워크스페이스 준비(product clone+patch, GENUT clone, `.env`, file-list) 후 CLI 실행을 executor(Host/Docker)에 위임. 상대→절대 경로 변환은 executor 경로 공간에서 수행.
- 테스트: fake GENUT(`tests/fake_genut`)와 가상 프로덕트(로컬 git repo) 픽스처로 E2E 검증. Docker 경로는 마커로 분리(자동 skip).

## Postgres 이식

코드는 DB 비의존(표준 SQLAlchemy, JSON 타입, String enum, unique 제약)이다. 전환:
```bash
pip install -e ".[postgres]"
export DB_URL=postgresql+psycopg://user:pass@host:5432/genut
alembic upgrade head
```
SQLite 전용 코드는 `db/base.py`의 PRAGMA(여기서 `sqlite` URL일 때만 적용)뿐이다.

---

## 개발 규칙 (반드시 준수)

### 1. 코드 수정 시 테스트 필수
- 수정 시 **관련 테스트를 생성/갱신**하고, **전체 테스트를 실행**해 통과를 확인한 뒤 진행한다.

### 2. Git 커밋 필수 (커밋 메시지는 영어)
- 수정+테스트 확인 후 **매번 커밋**한다. **커밋 메시지는 영어로** 작성한다.
- 원격: GitHub `haangman/GENUT_service` (public).

### 3. 점진적 개발
- 기능을 작은 단위로 나눠 구현하고, 각 단위마다 (테스트 → 전체 테스트 → 영어 커밋)을 적용한다.

### 코딩 컨벤션 / 언어
- 기존 코드 스타일(네이밍, 들여쓰기, 주석)을 따른다.
- 사용자와의 의사소통·코드 주석은 **한국어**, **커밋 메시지는 영어**, 기술 용어·식별자는 원문 유지.
