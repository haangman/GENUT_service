# GENUT_service Docker 적용 설계 / 작업 인계 문서

> **이 문서의 목적**: GENUT_service에 Docker를 어떤 경계로 적용할지에 대한 권장안과,
> 그것을 실제로 구현하기 위한 **자기완결적 작업 지시서**다. 다른 Claude/개발자가 이 문서만
> 읽고 현재 코드 제약을 이해한 뒤 바로 착수할 수 있도록 현재 구조·파일·심볼·함정·증분 계획을
> 모두 담았다. 코드 식별자는 원문 유지, 설명은 한국어. 작업 규칙: **수정마다 관련 테스트
> 생성/갱신 → 전체 테스트 통과 → 영어 커밋**(루트 `CLAUDE.md` 참조).

작성 2026-06-18.

---

## 0. TL;DR (권장 결론)

**프론트엔드·코어·GENUT·프로덕트를 4개의 상주(long-running) 컨테이너로 쪼개지 말 것.**
대신 **3개의 관심사**로 나눈다:

1. **상주 서비스 컨테이너 1개** = 코어(FastAPI + 인앱 스케줄러 + 러너 오케스트레이션) + **빌드된 프론트엔드 동봉**
2. **job마다 생성되는 일회성 실행 컨테이너 N개** = GENUT 실행 + 프로덕트 빌드/테스트 (`docker run --rm`) — 이미 `DockerExecutor`로 설계됨
3. **영속 볼륨(+선택 Postgres 컨테이너)** = DB와 워크스페이스(누적되는 테스트 코드·체크아웃·로그)

- 프론트엔드 = "컨테이너"가 아니라 **빌드 산출물**(멀티스테이지로 코어 이미지에 복사).
- 프로덕트 = "컨테이너"가 아니라 **볼륨 위의 데이터**.
- GENUT+프로덕트 빌드/테스트 = 상주 서비스가 아니라 **per-job 일회성 컨테이너**.
- 워커/스케줄러 = **코어와 같은 컨테이너에 유지(분리 금지)** — 이유는 §3.

---

## 1. 현재 아키텍처와 제약 (반드시 먼저 이해할 것)

계층: **api → services → db**. `scheduler`/`runner`는 FastAPI 비의존(HTTP 없이 단위테스트 가능).
전체 개요는 루트 `PROGRESS.md` 참조. 아래는 Docker 결정에 직접 영향을 주는 사실만 정리한다.

### 1.1 코어 = 단일 프로세스, 외부 브로커 없음
- `genut_service/main.py`: FastAPI 앱 팩토리. `lifespan`에서 `scheduler_autostart`면 `Scheduler.start()` 호출. 비-API 경로는 `frontend/dist/index.html`로 SPA fallback, `/assets`는 `StaticFiles` 마운트(`mount_frontend`).
- `genut_service/scheduler/loop.py`: `Scheduler`가 매 tick `claim_jobs` 후 `asyncio.to_thread`로 **비차단 디스패치**(롤링 병렬). `run_pending`은 결정론적(테스트/E2E용). `Scheduler.start()`는 기동 시 1회 `mark_interrupted_jobs` + `release_stale_locks` 수행.
- `genut_service/scheduler/engine.py`: **단일 writer**가 `claim_jobs`(idle 워커↔queued job 배정)/`finish_job` 수행. 배타성은 `product_locks.product_id` PK가 보장(`scheduler/lock.py`의 `try_acquire_lock` IntegrityError).
- **함의**: 작업 분배에 RabbitMQ/Redis 같은 **외부 브로커가 없다.** DB(SQLite/Postgres)와 인메모리 상태만으로 큐·락·취소를 처리한다.

### 1.2 force-kill(취소)는 같은 프로세스의 공유 메모리에 의존
- `genut_service/runner/process_registry.py`: 스레드 안전 `job_id → 현재 subprocess(Popen)` 레지스트리. `cancel(job_id)`가 플래그 set + 등록된 Popen `terminate→kill`.
- `genut_service/runner/worker.py` `process_job`: `on_process`로 실행 중 subprocess를 `register`. 정상/예외 어느 경로든 `is_canceled`를 먼저 검사해 `CANCELED`로 마무리.
- `genut_service/api/jobs.py` `POST /jobs/{id}/cancel`: **API 스레드**가 `process_registry.cancel`을 호출 → **워커 스레드**가 띄운 Popen을 죽인다. **API와 워커가 같은 프로세스라서 가능**하다.
- **함의**: 워커를 별도 프로세스/컨테이너로 떼면 이 취소 메커니즘이 깨진다(브로커 + DB 시그널 기반 재설계 필요).

### 1.3 실행 격리는 이미 executor로 추상화됨 (per-job Docker 설계 존재)
- `genut_service/runner/genut_runner.py` `run(...)`: 워크스페이스 준비(product clone+patch, GENUT clone, ASSURE, `.env`, file-list) 후 **CLI 실행을 executor에 위임**. 상대→절대 경로 변환은 executor 경로공간에서 수행.
- `genut_service/runner/executors.py` `HostExecutor`: 항등 경로, `base_python=sys.executable`.
- `genut_service/docker/client.py` `DockerExecutor`: `job_root`를 컨테이너 `/work`에 bind-mount하고 그 안에서 실행. 핵심 동작:
  - 생성자: `DockerExecutor(image, job_root, container_root="/work", cpus, memory, docker_bin="docker")`, `self.job_root = Path(job_root).resolve()`.
  - `to_exec_path(host_path)`: `host_path.resolve().relative_to(self.job_root)` → `/work/<rel>`.
  - `run(argv, cwd_host, ...)`: **`docker run --rm -v {self.job_root}:{container_root} -w {to_exec_path(cwd_host)} [--cpus][--memory] {image} {argv}`**. `on_line`이 있으면 `subprocess_util.run_streaming`(스트리밍 + `on_start`로 Popen 노출).
- `genut_service/runner/worker.py`: `settings.use_docker`면 `make_executor = lambda job_root: DockerExecutor(settings.docker_image, job_root, cpus=settings.docker_cpus, memory=settings.docker_memory)`.
- `genut_service/docker/images/Dockerfile.runner`: `python:3.12-slim` + `git/build-essential/cmake/ninja/clang`, `WORKDIR /work`. **kunit 커널 툴체인은 아직 없음**(주석으로만 표시).
- `is_docker_available()`로 docker 미설치 환경은 자동 skip(테스트 마커 `docker`).

### 1.4 영속 상태: 프로덕트 체크아웃에 테스트가 누적됨
- `genut_service/workspace.py` `resolve_code_path`: `code_path`가 절대면 그대로, 상대면 `WORKSPACE_ROOT` 기준.
- 프로덕트: `code_path` 있으면 그 경로에 제자리 업데이트(`git_ops.ensure_checkout`: `fetch + reset --hard`, **`git clean` 미사용**). **생성 테스트 출력 폴더(`out_tests_rel`)는 `preserve`로 reset 전후 보관·복원** → staged/untracked 무관하게 누적 보존(`runner/genut_runner.py`, `runner/git_ops.py`).
- GENUT: `code_path` 있으면 `<code_path>/GENUT`, ASSURE는 `<code_path>/ASSURE`.
- **여러 GENUT가 여러 프로덕트에 동시 기록**: `product_locks`가 **프로덕트(이름)당 1 job**으로 직렬화하므로 같은 프로덕트 폴더에 동시 기록은 없다(서로 다른 프로덕트는 동시 진행).
- job 로그 파일: `WORKSPACE_ROOT/job_<id>/job.log`.

### 1.5 DB / 설정
- `genut_service/config.py` `Settings`(pydantic-settings, `.env`): `db_url`(기본 `sqlite:///./genut_service.db`), `workspace_root`(기본 `./_workspaces`), `genut_run_timeout=1800`, `genut_use_venv=True`, `git_timeout=300`, `scheduler_interval=1.0`, `scheduler_autostart=True`, **`use_docker=False`**, `docker_image="genut-runner:latest"`, `docker_cpus=2.0`, `docker_memory="2g"`.
- DB 비의존(표준 SQLAlchemy, JSON, String enum). SQLite 전용 코드는 `db/base.py`의 PRAGMA(`sqlite` URL일 때만). Postgres 전환: `pip install -e ".[postgres]"` + `DB_URL=postgresql+psycopg://...` + `alembic upgrade head`.
- `JobStatus`: `queued→running→done|failed|canceled|interrupted`(`interrupted`는 서버 재시작 시 기동 janitor가 마킹). `TERMINAL_STATUSES = {done, failed, canceled, interrupted}`.
- **DB·job 정보는 코어/프론트 재배포와 무관하게 보존되어야 한다.**

### 1.6 프론트엔드
- `frontend/`(React+Vite+TS). `npm --prefix ./frontend run build` → `frontend/dist`. 코어가 정적 서빙(요청마다 디스크에서 읽음 → **재빌드만으로 반영, 서버 재시작 불필요**). 런타임 서비스가 아님.

---

## 2. 권장 Docker 구조

### 2.1 토폴로지

```
┌───────────────────────────────────────────────────────────────┐
│ genut-service  (상주 컨테이너 1개)                              │
│  - FastAPI + 인앱 스케줄러 + 러너 오케스트레이션               │
│  - 빌드된 frontend/dist 동봉(멀티스테이지)                      │
│  mounts:                                                        │
│    - /var/run/docker.sock        ← per-job 컨테이너 기동(DooD)  │
│    - volume: genut_ws  → /work_root (워크스페이스)             │
│    - volume: genut_db  → DB 파일  (또는 Postgres 연결)         │
└───────────────────────────────────────────────────────────────┘
        │ docker run --rm (job마다, 형제 컨테이너로 기동)
        ▼
┌───────────────────────────────────────────────────────────────┐
│ genut-runner:<tag>  (일회성 컨테이너, job 종료 시 --rm 삭제)    │
│  - 툴체인(gcc/clang/cmake/ninja/python) + GENUT 실행            │
│  - -v genut_ws:/work  ← 같은 워크스페이스 볼륨 마운트          │
│    (프로덕트 체크아웃·누적 테스트·GENUT 코드·file-list·out)     │
└───────────────────────────────────────────────────────────────┘

┌──────────────────────────────┐
│ postgres (선택, 상주) + volume │   ← 단일 노드면 SQLite 볼륨으로도 가능
└──────────────────────────────┘
```

상주 컨테이너는 **genut-service(+선택 postgres)** 뿐. 나머지는 일회성 또는 볼륨.

### 2.2 한 줄 결정표

| 대상 | 권장 | 형태 |
|---|---|---|
| 프론트엔드 | 코어 이미지에 **동봉** | 빌드 산출물(멀티스테이지) |
| 코어 API + 스케줄러 + 러너 | **한 상주 컨테이너** | long-running |
| GENUT 실행 + 프로덕트 빌드/테스트 | **per-job 컨테이너** | `docker run --rm` |
| 프로덕트 코드(누적 테스트) | **영속 볼륨** | 데이터(컨테이너 아님) |
| DB / job 정보 | **영속 볼륨 또는 Postgres 컨테이너** | 데이터 |

---

## 3. 왜 이 경계인가 / 무엇을 분리하지 말아야 하나

- **프론트엔드 별도 상주 컨테이너 ✗**: 정적 산출물이라 런타임 서비스가 아님. 코어가 이미 `dist`를 서빙하고 재빌드만으로 반영된다. 독립 CDN/nginx가 꼭 필요할 때만 분리(이 규모엔 과함).
- **코어 ⟷ 워커/스케줄러 분리 ✗ (가장 중요)**: §1.1/§1.2의 *브로커리스 단일 writer 스케줄러* + *공유 메모리 force-kill* 이 깨진다. 분리하려면 (1) 작업 큐 브로커 도입, (2) 취소를 DB/메시지 시그널로 재설계, (3) 락 모델 재검토가 필요 → 큰 재작업이며 이 프로젝트가 의도적으로 피한 복잡성이다. **코어=API+스케줄러+러너는 한 컨테이너로 유지.**
- **GENUT/프로덕트 실행 분리 ✓**: 신뢰 불가 코드 빌드/LLM 구동/폭주 가능성 → 격리가 가장 필요한 곳. 이미 `DockerExecutor`로 per-job 격리 설계 존재. 상주가 아니라 **일회성**이 맞다(클린 teardown `--rm`, 리소스 제한, 툴체인 버전 분리).
- **프로덕트/DB 분리 ✓ (데이터로서)**: 코어/프론트가 자주 재배포돼도 누적 테스트와 job 이력이 보존돼야 하므로 **반드시 이미지 밖 볼륨/별도 DB**.
- **"모두 한 컨테이너" ✗ (PoC 제외)**: 격리 없음(프로덕트 빌드가 코어/서로에 영향), 거대 이미지(모든 언어 툴체인+node+서비스), 자주 바뀌는 코어와 무거운 안정 툴체인이 한 이미지에 결합.

---

## 4. 적용 시 함정과 필요한 코드 변경 (구현 핵심)

### 4.1 [필수] DooD 바인드 마운트 경로 변환
**문제**: 코어를 컨테이너화하면 코어가 호출하는 `docker run -v {job_root}:/work`의 `job_root`는 **호스트 데몬이 보는 경로**여야 한다. 현재 `DockerExecutor`는 `self.job_root`(=코어 컨테이너가 보는 경로, 예 `/work_root/job_5`)를 그대로 `-v`에 쓴다. 형제 컨테이너는 이 경로를 **호스트에서** 찾으므로 **존재하지 않는 경로 → 빈 디렉터리 마운트**가 된다.

**해결안(둘 중 하나):**
- **(A) named volume 참조(권장)**: 워크스페이스를 named volume(`genut_ws`)으로 두고, per-job 컨테이너를 `-v genut_ws:/work`(+ 서브경로는 `-w`로 지정)로 띄운다. 코어도 같은 named volume을 마운트한다. → `DockerExecutor`에 "호스트 마운트 소스(볼륨명/호스트경로)"와 "코어가 보는 경로"를 분리하는 설정 추가 필요.
- **(B) 경로 일치**: 코어 컨테이너에 워크스페이스 볼륨을 **호스트와 동일 절대경로**로 마운트(예 호스트 `/srv/genut/ws` → 코어도 `/srv/genut/ws`). 그러면 `self.job_root`가 호스트 경로와 같아져 현행 로직이 그대로 동작. 가장 적은 코드 변경.

**변경 파일**: `genut_service/docker/client.py`(DockerExecutor), `genut_service/runner/worker.py`(make_executor 팩토리에 호스트 경로 매핑 주입), `genut_service/config.py`(예: `docker_workspace_host_root` 또는 `docker_workspace_volume` 설정 추가).

### 4.2 [권장] 취소를 `docker kill`로 확실히
**현재**: `use_docker`면 `process_registry`에 등록되는 Popen은 `docker run` **클라이언트**다. 죽이면 로컬 CLI만 죽고 컨테이너 정리는 `--rm`에 의존(데몬이 reaping). 컨테이너가 즉시 멈춘다는 보장이 약하다.

**개선**: per-job 컨테이너에 `--name genut-job-<job_id>` 부여 → 취소 시 `docker kill genut-job-<job_id>` 호출. `process_registry`/`worker`/`DockerExecutor`가 컨테이너 이름을 알도록 연결. (호스트 실행 경로는 기존 Popen kill 유지.)

**변경 파일**: `genut_service/docker/client.py`(`--name` 추가, kill 헬퍼), `genut_service/runner/process_registry.py` 또는 `worker.py`(docker일 때 kill 전략 분기).

### 4.3 [정책] 툴체인 이미지 분기 (c/cpp/kunit)
- 현재 `Dockerfile.runner`는 단일 이미지(gcc/clang/cmake/ninja). **kunit(커널 빌드)** 은 커널 헤더/툴체인이 추가로 필요해 무겁다.
- 옵션: (1) 단일 fat 이미지로 시작, (2) **모드별 이미지**(`genut-runner-c`, `-cpp`, `-kunit`), (3) **프로덕트/GENUT별 이미지 지정**. 현재 `docker_image`는 전역 1개 → 프로덕트(또는 GENUT) 속성으로 이미지를 받도록 확장 고려.
- GENUT 자체의 파이썬 의존성은 `genut_use_venv`(per-job `.venv` + `requirements.txt`)로 이미 런타임 설치되므로 이미지에 굳이 넣지 않아도 됨(단, 매번 설치 비용 ↔ 이미지 사전설치 트레이드오프).

**변경 파일**: `genut_service/docker/images/`(Dockerfile들), `config.py`/`db/models.py`(이미지 선택 필드 추가 시), `worker.py`.

### 4.4 [정책] 빌드 산출물 누적 정리
- 영속 체크아웃에는 **테스트(보존 대상)** 뿐 아니라 `build/` 산출물(.o 등)도 untracked로 쌓인다(현재 `ensure_checkout`가 untracked 보존).
- 결정 필요: **테스트는 보존하되 build 디렉터리는 매 job 시작 시 정리**할지. 러너 레벨에서 `out_tests_rel`만 보존(이미 그러함)하고 빌드 디렉터리는 선택적으로 클린.

**변경 파일**: `genut_service/runner/genut_runner.py`(빌드 디렉터리 클린 옵션).

### 4.5 [운영] 동시성/리소스
- 동시 per-job 컨테이너 수 = idle 워커 수 = 등록 GENUT 수. 노드 코어/메모리 대비 워커 수와 `docker_cpus`/`docker_memory`를 맞춰야 ~200 프로덕트 부하에서 안전.
- per-job 컨테이너 네트워크 정책(LLM API 호출 필요 → egress 허용), 비밀(`DS_ASSIST_CREDENTIAL_KEY`)은 `.env` 파일로 워크스페이스에 기록되어 컨테이너에 마운트됨(로그 마스킹은 이미 적용). 시크릿 노출 표면 점검 필요.

### 4.6 [DB] SQLite vs Postgres
- 단일 노드면 SQLite 파일을 **볼륨**에 두면 충분(코어 한 프로세스만 접근하므로 WAL 동시성 이슈 적음).
- 더 견고/확장하려면 **Postgres 컨테이너 + 볼륨**. 코드는 비의존이라 `DB_URL`만 변경 + `alembic upgrade head`. compose에 `depends_on` + healthcheck.

---

## 5. 증분 구현 계획 (작업 단위 = 테스트 → 전체 테스트 → 영어 커밋)

> 현재 `use_docker=False`(호스트 실행)가 기본이고 Docker 경로는 마커로 분리되어 자동 skip된다.
> 아래는 우선순위 순. 한 번에 하나씩.

### Phase D1 — 코어 이미지화(프론트 동봉) + compose 골격 *(상주 서비스부터)*
- 멀티스테이지 `Dockerfile`(루트): stage1 `node`로 `frontend` 빌드 → `dist`; stage2 `python:3.12-slim`에 패키지 설치(`pip install .`) + `dist` 복사 + `alembic` 포함. `genut-service serve`로 기동.
- `docker-compose.yml`: `genut-service`(포트 8000, 볼륨 `genut_ws`/`genut_db`, `/var/run/docker.sock` 마운트), 선택 `postgres`.
- 이 단계는 **여전히 host 실행(use_docker=false)** 일 수 있음 — 단, per-job을 쓰려면 socket 필요(Phase D2).
- 검증: 컨테이너 기동 → `/health` 200 → 웹페이지 로드 → DB 볼륨 영속 확인(컨테이너 재생성 후 job 이력 유지).

### Phase D2 — DooD 경로 변환(§4.1) + per-job 컨테이너 정상화
- `DockerExecutor`/`worker`/`config`에 호스트 워크스페이스 매핑 도입(named volume 또는 경로 일치). `use_docker=true`에서 코어 컨테이너가 형제 per-job 컨테이너를 띄워 **실제로 워크스페이스가 마운트**되는지 확인.
- 테스트: `tests/test_docker_paths.py`(경로 매핑, docker 불필요) 확장 — 컨테이너화 매핑 규칙 단위 검증. `tests/test_docker.py`(`-m docker`, 실제 컨테이너) 보강.
- 검증(실 docker 환경/WSL2·Linux): 데모 프로덕트로 job 1건 → per-job 컨테이너에서 생성·빌드·테스트 → `out_tests_rel`에 결과 누적 확인.

### Phase D3 — 취소를 `docker kill`로(§4.2)
- per-job 컨테이너 `--name genut-job-<id>` + 취소 시 `docker kill`. force-kill E2E가 docker 경로에서도 `CANCELED`로 마무리되는지 검증.
- 테스트: `tests/test_runner.py`/`tests/test_e2e.py`의 강제 종료 테스트에 docker 변형 추가(마커 `docker`).

### Phase D4 — 툴체인/빌드 정책(§4.3/§4.4)
- 모드별(또는 프로덕트별) 이미지 선택 + kunit 이미지. 빌드 디렉터리 클린 옵션.
- 데이터 모델/스키마 확장 시 Alembic 마이그레이션 동반.

### Phase D5 — Postgres 전환(선택, §4.6)
- compose에 postgres + healthcheck, `DB_URL` 전환, `pip install -e ".[postgres]"`, 마이그레이션. 기존 SQLite 데이터 이관 스크립트(선택).

---

## 6. 검증 가이드

- **백엔드 단위/통합**: `pytest`(기본 `-m "not docker and not slow"`). Docker 경로: `pytest -m docker`(docker 필요, 없으면 자동 skip). 경로 매핑은 `tests/test_docker_paths.py`로 docker 없이도 검증 가능.
- **프론트**: `npm --prefix ./frontend test`, 빌드 `npm --prefix ./frontend run build`.
- **컨테이너 통합(수동, Linux/WSL2 권장 — Windows는 docker 미가용 시 host 실행)**:
  1. 러너 이미지 빌드: `docker build -t genut-runner:latest -f genut_service/docker/images/Dockerfile.runner .`
  2. compose up → `/health`, 웹페이지, job 제출 → per-job 컨테이너 동작/누적 테스트/취소/재시작 interrupted 확인.
  3. 코어 컨테이너 재생성 후 **DB·워크스페이스 영속** 확인.
- **불변식 회귀**: 동일 프로덕트 직렬화, N워커→N프로덕트 동시, 실패 격리, 강제 종료→CANCELED, 재시작→interrupted (각 PROGRESS §6/§7/§12 참조).

---

## 7. 결정이 필요한 사항 (작업 전 합의 권장)

1. **워크스페이스 마운트 방식**: named volume(A) vs 호스트 경로 일치(B). (B)가 코드 변경 최소.
2. **DB**: 단일 노드 SQLite 볼륨 유지 vs Postgres 컨테이너 도입 시점.
3. **툴체인 이미지**: 단일 fat vs 모드별 vs 프로덕트별 지정. kunit 지원 범위.
4. **빌드 산출물**: build 디렉터리 매 job 클린 여부(테스트는 항상 보존).
5. **배포 플랫폼**: Windows 개발(호스트 실행) ↔ Linux/WSL2 운영(실 docker). docker 미가용 환경은 host 실행으로 폴백(현 동작 유지).

---

## 8. 부록 — 관련 파일/설정 인덱스

| 관심사 | 파일 / 심볼 |
|---|---|
| 앱 팩토리·lifespan·정적 서빙 | `genut_service/main.py` (`lifespan`, `mount_frontend`) |
| 설정 | `genut_service/config.py` (`Settings`: `use_docker`, `docker_image`, `docker_cpus`, `docker_memory`, `workspace_root`, `db_url`, `genut_use_venv` …) |
| 스케줄러(단일 writer·락) | `genut_service/scheduler/{engine,loop,lock,janitor}.py` |
| 러너 오케스트레이션 | `genut_service/runner/genut_runner.py` (`run`) |
| 워커·executor 선택 | `genut_service/runner/worker.py` (`process_job`, `make_executor`) |
| Host/Docker 실행기 | `genut_service/runner/executors.py`, `genut_service/docker/client.py` (`DockerExecutor`, `to_exec_path`, `run`) |
| 스트리밍·서브프로세스 | `genut_service/runner/subprocess_util.py` (`run`, `run_streaming`, `on_start`) |
| 강제 종료 | `genut_service/runner/process_registry.py`, `genut_service/api/jobs.py` (`/cancel`) |
| 영속 체크아웃·테스트 보존 | `genut_service/workspace.py`, `genut_service/runner/git_ops.py` (`ensure_checkout(preserve=…)`) |
| 러너 툴체인 이미지 | `genut_service/docker/images/Dockerfile.runner` |
| 상태/종료 집합 | `genut_service/enums.py` (`JobStatus`, `TERMINAL_STATUSES`, `INFLIGHT_STATUSES`) |
| Docker 테스트 | `tests/test_docker.py`(`-m docker`), `tests/test_docker_paths.py`(경로 매핑) |
| 전체 진행 기록 | `PROGRESS.md` |
