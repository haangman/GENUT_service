# GENUT_service 진행 상세 기록

작성 2026-06-15 · 최종 갱신 2026-06-16. 본 문서는 현재까지 구현·검증한 내용을 상세히 정리한다.
원격: https://github.com/haangman/GENUT_service (branch `main`, public).

---

## 1. 프로젝트 개요 / 목표

`GENUT_service`는 외부 테스트 자동생성 CLI 도구 **GENUT**를 **여러 워커로 병렬 실행**하여, 약 **200개**의 대상 프로덕트(C/C++/kunit)에 단위 테스트를 생성하는 서비스다. FastAPI 백엔드 + React 운영/사용 웹 UI로 구성하며, 기능을 작은 단위로 점진적으로 구현한다.

**개발 규칙(고정):** 코드 수정 시 ① 관련 테스트 생성/갱신 → ② 전체 테스트 통과 확인 → ③ **영어 커밋** → 푸시. 사용자 소통·주석은 한국어, 커밋 메시지는 영어.

---

## 2. GENUT(외부 도구) 규격 — 사용자 제공

서비스에 **repo로 등록**되어, 매 실행 시 최신 코드로 clone 후 CLI로 호출된다.

- **CLI 옵션**: `--file-list`(절대경로 txt, 내부 소스도 절대경로) · `--compile-dp-path`(compile_commands.json 폴더 절대경로) · `--out-test-folder-path`(절대경로) · `--max-attempts`(기본 10) · `--debug` · `--enable-assure` · `--function-name`(선택)
- **동작**: 함수마다 여러 테스트를 한 번에 생성, **positive:negative = 50:50**. 생성 테스트를 프로젝트에 통합 후 configure→build→test 실행, 에러를 max-attempts까지 자가 수정.
- **.env**: `TEST_GENERATION_MODE`(c|cpp|kunit) · `DS_ASSIST_CREDENTIAL_KEY`(LLM API 키) · `DS_ASSIST_USER_ID` · `DS_ASSIST_SEND_SYSTEM_NAME` · `CMAKE_CONFIGURE_CMD` · `CMAKE_BUILD_CMD` · `TEST_RUN_CMD`

> 로컬 `Downloads\GENUT\GENUT`(GTest 스킬)과는 **다른** 도구다.

---

## 3. 핵심 설계 결정 (확정)

| 항목 | 결정 |
|---|---|
| 백엔드 | FastAPI + SQLAlchemy 2.0(SQLite→Postgres, Alembic) |
| 인프라 | **자체 완결형** 인앱 스케줄러(외부 브로커 없음) |
| 실행 격리 | job마다 **Docker 컨테이너**(`use_docker=true`); 기본은 호스트 실행 |
| 프론트엔드 | React 18 + Vite + TS, Tailwind, TanStack Query, Zustand, RHF+Zod, Vitest+RTL+MSW |
| compile_commands.json | 프로덕트 repo 커밋본을 지정 상대경로에서 직접 읽음 |
| TEST_GENERATION_MODE | **프로덕트** 속성 |
| 워커 모델 | **등록 GENUT 1개 = 워커 1개**. N개 GENUT → 동시 N개 서로 다른 프로덕트 |
| GENUT 실행 | 등록 시 `run_command` 지정(기본 `python -m genut`), 서비스가 표준 플래그를 붙여 실행 |
| 배타성 | 한 프로덕트는 동시에 1개 job만(`product_locks.product_id` PK). 동일 프로덕트 동시 요청은 1개 실행·나머지 대기 |

---

## 4. 아키텍처 / 디렉터리

```
genut_service/
├── main.py              # FastAPI 앱 팩토리, lifespan(스케줄러 자동기동), 정적 서빙(SPA)
├── config.py            # .env → Settings (DB_URL, WORKSPACE_ROOT, GENUT_RUN_TIMEOUT,
│                        #   SCHEDULER_INTERVAL/AUTOSTART, USE_DOCKER, DOCKER_* 등)
├── enums.py             # TestGenerationMode/JobStatus/WorkerStatus/EventLevel/JobPhase
├── paths.py             # 상대경로 정규화(\→/, .. 거부)
├── workspace.py         # 프로덕트 repo 체크아웃 캐시(ensure_product_checkout)
├── db/{base,models}.py  # 엔진/세션(SQLite WAL pragma), ORM 모델
├── schemas/             # Pydantic (common/product/filetree/job/genut/worker)
├── api/                 # 라우터: products, files, jobs, genuts, workers + deps
├── services/            # product/filetree/compile_db/job/genut/monitoring (FastAPI 비의존)
├── scheduler/           # engine(claim_jobs/finish_job), lock, janitor, loop(Scheduler/run_pending)
├── runner/              # genut_runner, worker(process_job), git_ops, env_builder,
│                        #   executors(HostExecutor), subprocess_util
└── docker/              # client(is_docker_available/DockerExecutor), images/Dockerfile.runner
frontend/src/
├── lib/{apiClient,queryClient}  api/{products,tree,jobs,genuts,workers}  types/api.ts
├── components/PageHeader  app/AppLayout  router.tsx
└── features/
    ├── request/   RequestPage, ProductPicker, FileTree, SelectedFilesPanel,
    │              RequestActions, store(zustand), folderImport, sourceFiles
    ├── products/  ProductsPage, ProductForm, productSchema
    ├── genuts/    GenutsPage, GenutForm, genutSchema(genutEditSchema)
    └── workers/   MonitoringPage
tests/                   # unit/api/scheduler/runner/e2e/docker + fake_genut/(가상 GENUT)
migrations/              # Alembic (env.py + versions/)
```
계층: **api → services → db**. `scheduler`/`runner`는 FastAPI 비의존(HTTP 없이 단위테스트 가능).

---

## 5. 데이터 모델 (SQLAlchemy)

- **products**: name(unique), product_code, git_url, git_ref, `compile_db_rel`, `out_tests_rel`, `cmake_configure_cmd`, `cmake_build_cmd`, `test_run_cmd`, `test_generation_mode`, active. (+ 순서 있는 **patches** 1—N)
- **patches**: product_id, order_index, name, content(unified diff). UNIQUE(product_id, order_index).
- **genut_instances**(=워커): name(unique), repo_url, repo_ref, `ds_assist_credential_key`(secret·응답 제외), `ds_assist_send_system_name`, max_attempts(기본10), `run_command`, enabled, worker_status(idle|busy|error|disabled), current_job_id(soft 참조).
- **jobs**: product_id, genut_instance_id, status, function_name, `file_list`(JSON, included), `excluded_files`(JSON), attempt, submitted/started/finished_at, result_summary, error.
- **job_events**: job_id, ts, level, phase, message, payload(JSON) — append-only 로그.
- **product_locks**: `product_id`(PK), job_id, genut_instance_id, acquired_at — **PK가 프로덕트당 락 1개 보장**.

마이그레이션: `f944f16d574a_create_core_tables`. `alembic check` drift 없음.

---

## 6. 스케줄러 / 동시성 모델

- **claim_jobs(session)**: enabled·idle 워커에 queued job을 배정. 프로덕트당 1개, 락 보유 프로덕트 제외, idle 워커 수만큼. job→running, 워커→busy, `product_locks` insert.
- **finish_job(session, job_id, status, ...)**: 종료 상태 기록 + 락 해제 + 워커→idle.
- **lock.try_acquire_lock / release_lock**: PK 충돌(IntegrityError)이 배타성의 원자적 근거.
- **loop.Scheduler**(운영): 매 tick `claim_jobs` 후 **비차단 디스패치**(`asyncio.to_thread`로 실행, 완료 대기 안 함) → 워커가 비는 즉시 다음 job을 잡는 롤링 병렬. lifespan에서 `scheduler_autostart`면 기동(테스트는 off). 시작 시 janitor 1회.
- **loop.run_pending(session, process)**: 결정론적(동기) — E2E/테스트에서 사용.
- **janitor.release_stale_locks**: 종료/소실 job의 락 해제 + 해당 busy 워커 idle 복구.

**불변식**(테스트로 보장):
1. 동일 프로덕트 동시 처리 금지
2. N개 워커 → 동시 N개 서로 다른 프로덕트
3. 동일 프로덕트 fan-in → 1개 실행·나머지 대기(`waiting_on_product`)
4. 실패 격리 — 한 job 실패가 다른 job/락/워커에 영향 없음

---

## 7. Runner / 실행

`runner/genut_runner.run(job, product, genut, *, workspace_root, debug, enable_assure, ..., make_executor)`:
1. product 코드 준비 — **`code_path`가 있으면 그 영속 경로에 제자리 업데이트**(`git_ops.ensure_checkout`: `.git` 있으면 `fetch + reset --hard origin/<ref>`, **`git clean` 미사용** → `out_tests_rel` 아래 생성 테스트(untracked) 보존; 없으면 clone), 없으면 기존대로 `job_<id>/product`에 임시 clone. clone/업데이트 후 **`git log`(최근 커밋)를 job 로그로 출력**(`git_ops.recent_log`, 실패해도 무시). 이어서 순서대로 patch 적용(`git_ops.apply_patch`는 **멱등** — `git apply --reverse --check`로 이미 적용분은 건너뜀)
2. GENUT 코드 준비 — `code_path` 있으면 영속 경로 업데이트, 없으면 `job_<id>/genut`에 임시 clone. 역시 clone/업데이트 후 **`git log`를 job 로그로 출력**
2-1. **ASSURE 코드 준비(선택)** — `assure_repo_url`이 있으면 **GENUT 코드와 같은 depth(형제 디렉터리 `<genut_dir>_assure`)** 에 받는다. GENUT가 영속(`code_path`)이면 ASSURE도 영속(제자리 업데이트), 임시면 임시 clone. clone/업데이트 후 `git log`도 출력
3. `.env` 조립(`env_builder`: DS_ASSIST_*는 GENUT, CMAKE_*·TEST_RUN_CMD·MODE는 프로덕트)
4. executor 선택(Host=항등 경로, **Docker=컨테이너 경로 매핑**)
5. 상대→절대(executor 경로공간) 변환, included만 `filelist.txt`에 절대경로로 기록
6. 준비 내용 로그(`on_event`): workspace·compile-db·out 경로, **file-list 내용**, **`.env` 내용(비밀 키 값 마스킹)**, 실제 실행 명령
7. **(옵션) GENUT 가상환경 준비** — `genut_use_venv`(기본 True)면 GENUT 디렉터리의 `.venv`를 준비. **이미 있으면(루트 `pyvenv.cfg`로 판단, OS 무관) 재생성하지 않고 재사용**, 없으면 `python -m venv`로 생성(영속 `code_path`면 다음 job에서 재사용됨) → `requirements.txt` 있으면 `pip install -r`(재사용 시에도 수행해 최신화) → `run_command`의 선행 인터프리터(`python`류)를 venv python으로 치환(=venv 진입). 실패 시 `VenvError`로 job FAILED. executor가 OS별 python 경로 제공(Host=`sys.executable`/`Scripts|bin`, Docker=`python`/`bin`)
8. `run_command` 실행 — `on_event`가 있으면 **출력을 줄 단위로 스트리밍**(`subprocess_util.run_streaming`), 없으면 일괄 실행
9. `out/result.json` 수집 → result_summary, 성공 판정(exit code + result.json status)

`runner/worker.process_job`: 배정 job 실행 → 각 단계/출력 이벤트를 **DB(JobEvent)와 파일(`<workspace>/job_<id>/job.log`)에 동시 기록**(시작~끝) → DONE/FAILED(`finish_job`). patch/git/임의 예외는 그 job만 FAILED(격리).

**Docker**: `DockerExecutor`가 job 워크스페이스를 `/work`에 bind-mount, `docker run --rm -v <job>:/work -w ... <image> <argv>`. `Dockerfile.runner`(gcc/clang/cmake/ninja/git/python). docker 미설치 환경에서는 docker-마커 테스트 자동 skip.

---

## 8. API 표면 (`/api`, 목록은 `{items,total,page,page_size}`)

- Products: `POST/GET/PUT/DELETE /products(/{id})` (+patches, +`code_path`: 코드 영속 경로 선택·절대/상대)
- Files: `GET /products/{id}/tree?path=`, `POST /products/{id}/compile-check {files}` → `{included,excluded}`
- Jobs: `POST /jobs {product_id,files,function_name?}`, `GET /jobs?status=&product_id=&page=`, `GET /jobs/{id}`, `GET /jobs/{id}/logs?since=`(증분 이벤트), `GET /jobs/{id}/log/download`(전체 진행 로그 파일; 실행 중엔 그 시점까지·`.env` 키 마스킹)
- GENUTs: `POST/GET/PUT/DELETE /genuts(/{id})` (credential 키 write-only·응답 제외, +`ds_assist_user_id`·`assure_repo_url`·`code_path` 선택)
- Monitoring: `GET /workers`, `GET /queue`(각 항목 `waiting_on_product`)
- 정적: 비-API 경로는 `frontend/dist/index.html`로 SPA fallback

---

## 9. 프론트엔드 (4 페이지)

1. **테스트 요청**: 프로덕트 선택 → 지연 파일트리(폴더 일괄 가져오기, 확장자 allowlist by mode) → compile_commands 검사로 included/excluded 분리(미포함 별도 표시·제출 제외) → 함수명(선택) → 제출. 선택 변경 시 stale → 재검사 전 제출 차단.
2. **프로덕트**: 목록 + 등록 폼(patch field-array) + **수정**(PUT, 기존값 프리필) + 삭제.
3. **GENUT**: 목록 + 등록 폼(키 write-only) + **수정**(키 비우면 기존 유지) + 삭제.
4. **모니터링**: 워커 그리드 · 요청 큐(대기 사유 배지) · job 이력. 작업 클릭 시 **실시간 로그 뷰어**(`?since=` 커서로 증분 누적, 종료 시 폴링 중단, 자동 스크롤) + **로그 파일 다운로드** 링크.

---

## 10. 테스트 전략

- **fake GENUT**(`tests/fake_genut/fake_genut.py`): 실 GENUT 계약 모사. 함수당 50:50 생성, `--function-name/--debug/--enable-assure` 반영, 시나리오(`GENUT_SCENARIO.json`)로 success/hard_fail/crash 및 `sleep_seconds`(관측용, 기본0) 구동, `result.json`에 env/file_list/compile_db provenance 기록. BOM 내성(utf-8-sig).
- **가상 프로덕트**(conftest `make_virtual_product`): 로컬 git repo. `fake_genut_repo` 픽스처는 fake를 담은 로컬 git repo.
- **레이어**: unit(paths/compile_db/env_builder/마스킹) · scheduler(claim/finish 불변식 4종, 결정론) · API(TestClient) · runner-subprocess(오케스트레이션·provenance·file-list·patch 실패·collection·single-fn·hard_fail·crash·스트리밍 이벤트) · subprocess(run_streaming) · 로그 다운로드(전체 내용·키 마스킹·404) · E2E(실 스케줄러 통과·실패 격리) · scheduler-loop(배리어 동시성) · docker(자동 skip). fake `sleep_seconds`/진행 라인.
- 프론트(Vitest+RTL+MSW): 폼 검증/제출/수정, 파일트리·폴더가져오기, compile-check·submit, 로그 뷰어 **증분 폴링·다운로드 링크** 등.
- 현재 **백엔드 64 passed, 1 deselected(docker) · 프론트 24 passed**.

---

## 11. 마일스톤 & 커밋 이력

| 마일스톤 | 내용 | 커밋 |
|---|---|---|
| M0 | 백엔드 스캐폴드 / 프론트 스캐폴드 | `ead4761` / `ba60bd8` |
| M1 | 데이터 모델 + Alembic | `2f032af` |
| M2 | 프로덕트 등록 API + 페이지 | `f69bf56` |
| M3 | 파일트리 + compile-check + 요청 페이지 코어 | `5a120dc` |
| M4 | 요청 제출 + compile-check/submit UI | `8b60b12` |
| M5 | 스케줄러 claim/finish + 배타 | `47b84fb` |
| M6 | GENUT 등록 API + 페이지 | `99cbfb8` |
| M7 | runner + fake + 가상프로덕트 + E2E | `b3a1941` |
| M8 | Docker 컨테이너-per-job | `97ae517` |
| M9 | 모니터링 엔드포인트/janitor + 페이지 | `fc1ca09` |
| M10 | prod 정적 서빙 + Postgres 이식 문서/옵션 | `1de541d` |
| 추가 | CLI `serve` 픽스 | `ed16afc` |
| 추가 | 산출물 추적 정리 | `1171f5d`, `0b37558` |
| 추가 | 프로덕트/GENUT **수정** 기능 | `3a437c4` |
| 추가 | fake `sleep_seconds` | `89f4893` |
| 추가 | **BOM 내성 + 비차단 스케줄러 루프** | `a854825` |
| 추가 | requirements.txt + .venv 실행 안내 | `88ae1fb` |
| 추가 | requirements 인코딩(한글 주석 cp949) 수정 | `090ce96` |
| 추가 | 테스트 이식성(sys.executable) + Linux/WSL 문서 | `cbfc89c` |
| 추가 | **GENUT 출력 실시간 스트리밍 로그** | `553a44c` |
| 추가 | 로그 뷰어 **증분(since) 폴링** | `7d189f9` |
| 추가 | **전체 진행 로그 파일 + 실행 중 다운로드** | `5e73e5e` |

---

## 12. 검증 결과

### 12.1 웹 페이지 (Playwright 라이브)
4개 페이지 모두 정상: 프로덕트/GENUT 등록·수정·삭제, 요청 페이지(트리·compile-check·제출), 모니터링(워커·큐·이력·로그). 콘솔 오류 0건.

### 12.2 병렬 실행 (실제 서버, GENUT 5 · 프로덕트 21)
- **5-way 병렬**: 서로 다른 프로덕트 5개 동시 제출 → 워커 5개 동시 busy(job #52~56). 모니터링 UI로 확인.
- **동일 프로덕트 배타**: 한 프로덕트에 3건 → busy=1(워커 4개 유휴인데도), 나머지 2건 `waiting_on_product=true`. 타임스탬프상 **완전 순차**(겹침 0): 57→58→59, 락 해제 후 ~0.3초 내 인계.
- 초기 20건 일괄: 모두 done, 락 누수 0, 타임스탬프 겹침 분석 peak=5 / 동일프로덕트 max=1.

### 12.3 검증 중 발견·수정한 이슈
- **CLI `serve`**: 단일 Typer 명령이라 서브커맨드 인식 실패 → 콜백 추가(`ed16afc`).
- **BOM 비내성**(중요): PowerShell `Set-Content -Encoding utf8`이 BOM을 붙여 `json.loads` 실패 → 전 파일 excluded → file_list 빈 채로 생성(테스트 0). `compile_db_service`·fake를 `utf-8-sig`로 수정 + 회귀 테스트(`a854825`). 실 Windows compile_commands.json도 BOM이 흔하므로 유효한 견고성 개선.
- **스케줄러 루프 비효율**: "배치 전체 완료까지 대기 후 claim" → 첫 tick에 1개만 잡히면 단독 실행으로 워커 유휴. **비차단 디스패치**로 개선(`a854825`).
- **requirements 한글 주석**: 새 venv의 기본 pip가 cp949로 디코딩하다 실패 → ASCII 주석으로 수정(`090ce96`). 클린 클론에서 전 과정 재현·검증.
- **테스트의 `python` 하드코딩**: Linux/WSL(`python3`)에서 runner 테스트 실패 → `sys.executable` 사용(`cbfc89c`).

### 12.4 작업 로그(실시간·전체·다운로드)
- 단계별 로그를 남긴다: `[schedule]`→`[clone]`/`[patch]`→`[prepare]`(workspace·compile-db·out 경로, **file-list 내용**, **`.env` 내용·키 마스킹**)→`[run] $실제 명령`+출력 라인(스트리밍)→`[collect]`. DB(JobEvent, 실시간 뷰어)와 `job.log` 파일에 동시 기록.
- **실시간(부분) 다운로드** `GET /api/jobs/{id}/log/download`: 라이브 검증에서 25초 작업이 다운로드 시점에 따라 **17줄 → 44줄**로 증가, 시작~`[collect]`까지 포함. `.env`는 `DS_ASSIST_CREDENTIAL_KEY=********`로 마스킹(실제 키 `demo-key` 비노출).
- 로그 뷰어는 마지막 이벤트 id 이후(`?since=`)만 받아 누적, 종료(done/failed) 시 폴링 중단 + 자동 스크롤.

---

## 13. 실행 방법

```bash
# 백엔드 (프로젝트 루트, Windows: .venv 사용)
.venv\Scripts\python.exe -m pytest                 # 테스트 (기본 -m "not docker and not slow")
.venv\Scripts\python.exe -m genut_service serve --host 127.0.0.1 --port 8000
#   → http://127.0.0.1:8000  (API + 빌드된 프론트 SPA 동시 서빙, 백그라운드 스케줄러 가동)

# 프론트엔드
npm --prefix ./frontend test
npm --prefix ./frontend run build                  # → frontend/dist (서버가 정적 서빙)
npm --prefix ./frontend run dev                     # 개발 서버(:5173, /api→:8000 프록시)

# DB 마이그레이션
.venv\Scripts\alembic.exe upgrade head
```

---

## 14. 데모 데이터 & 병렬 재검증 절차

데모용 로컬 git repo는 **프로젝트 repo 밖** `C:\Users\김은희\Downloads\genut_demo\`에 있다(추적 안 함):
- `genut/` : fake GENUT(`fake_genut.py`) + `requirements.txt`(six — runner의 `.venv` 설치 검증용), 등록 시 `run_command="python fake_genut.py"`, repo_url=이 경로
- `product/` : demo-calc용
- `p01`~`p20` : 각 `src/mod.cpp`(고유 함수) + `build/compile_commands.json` + `GENUT_SCENARIO.json`(`sleep_seconds`로 관측 시간 조절)

재검증: 서버 기동 → `/api/genuts`·`/api/products`에 등록(POST, **한글 경로 → UTF-8 바이트 body**) → `/api/jobs` 제출 → `/api/workers`·`/api/queue` 폴링 또는 DB의 started/finished_at 구간 겹침으로 peak 동시성 산출.
주의: PowerShell `Set-Content -Encoding utf8`은 BOM을 붙인다(서비스는 utf-8-sig로 내성 확보됨). 무BOM이 필요하면 `[IO.File]::WriteAllText`.

---

## 15. 알려진 가정 / 미정

- 실 GENUT 진입점/결과 포맷 미상 → `run_command`로 추상화, 결과는 exit code+`result.json`(없으면 추론).
- 실 Postgres·실 Docker 환경 미검증(코드는 비의존; 전환 절차는 CLAUDE.md).
- compile_commands 매칭은 정규화 절대 `file` + basename fallback(실제 샘플로 정교화 여지).
- 인증 없음(신뢰 네트워크 가정).

## 16. 다음 단계 후보

- 동일 프로덕트 대기/실패 격리 UI 시연 자동화, 더 큰 규모(워커 N 증설) 부하, 작업 취소/재시도, job 결과(생성 테스트) 다운로드, 인증, Postgres/Docker 실환경 검증, 주기적 janitor.
