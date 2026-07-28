# API로 프로덕트 / GENUT 등록하기

웹 UI 없이 REST API만으로 프로덕트와 GENUT(워커)를 등록·수정·삭제하는 방법을 정리한다.
웹 UI 자체가 이 API를 호출하므로, API로 등록한 항목은 UI에 그대로 보이고 반대도 같다.
대량(수십~수백 개) 등록 자동화, CI 연동, 스크립트 운영에 사용한다.

- **Base URL**: `http://<host>:8000/api` (예: `http://127.0.0.1:8000/api`)
- **인증**: 없음(신뢰 네트워크 전제)
- **Content-Type**: `application/json` — **본문은 반드시 UTF-8**
- 대화형 스키마 문서: 서버 실행 후 `http://<host>:8000/docs` (Swagger UI)

---

## 1. GENUT(워커) 등록

등록된 GENUT 1개 = 워커 1개. N개 등록하면 서로 다른 프로덕트 N개가 동시에 실행된다.

### 1.1 생성 — `POST /api/genuts`

```bash
curl -X POST http://127.0.0.1:8000/api/genuts \
  -H "Content-Type: application/json" \
  -d '{
    "name": "worker-1",
    "repo_url": "ssh://git@git.example.com/tools/GENUT.git",
    "repo_ref": "main",
    "run_command": "python -m genut",
    "ds_assist_credential_key": "<LLM API 키>",
    "ds_assist_send_system_name": "my-system",
    "ds_assist_user_id": "user01",
    "max_attempts": 10,
    "llm_model": "gptOss",
    "code_path": "/data/genut/workers/worker-1"
  }'
```

| 필드 | 필수 | 기본값 | 설명 |
|---|---|---|---|
| `name` | ✅ | — | 워커 이름. **유일해야 함**(중복 시 409) |
| `repo_url` | ✅ | — | GENUT 도구 repo 주소. 매 job마다 최신으로 갱신됨 |
| `repo_ref` | | `main` | 브랜치/태그명. `origin/`·`refs/heads/` 접두는 자동 제거됨. 존재하지 않는 ref면 job이 명확한 오류로 실패 |
| `ds_assist_credential_key` | ✅ | — | LLM API 키. **write-only** — 이후 어떤 응답에도 포함되지 않음 |
| `ds_assist_send_system_name` | ✅ | — | 키를 사용하는 시스템 이름 |
| `ds_assist_user_id` | | null | 선택 사용자 id |
| `run_command` | | `python -m genut` | CLI 실행 명령. 서비스가 표준 플래그(`--file-list` 등)를 뒤에 붙임 |
| `max_attempts` | | `10` | 테스트 생성 재시도 상한(≥1) |
| `llm_model` | | `gptOss` | `gptOss` \| `SSCR_SE` — GENUT `.env`의 `LLM_MODEL`로 전달 |
| `assure_repo_url` | | null | 지정 시 ASSURE repo도 함께 체크아웃(`--enable-assure`용) |
| `code_path` | | null | **영속 코드 경로**. 지정 시 `<code_path>/GENUT`(및 `/ASSURE`)에 제자리 업데이트 — `.venv` 재사용으로 job 시작이 빨라짐. 미지정 시 job마다 임시 clone |
| `enabled` | | `true` | false면 스케줄러가 job을 배정하지 않음 |

응답: `201` + 등록된 GENUT(JSON). `id`, `worker_status`(idle) 포함, credential 키는 제외.

### 1.2 수정 — `PUT /api/genuts/{id}`

**부분 수정**: 보낸 필드만 갱신된다. `ds_assist_credential_key`를 생략(또는 null)하면
기존 키가 유지된다 — 키 교체 시에만 값을 보낸다.

```bash
curl -X PUT http://127.0.0.1:8000/api/genuts/1 \
  -H "Content-Type: application/json" \
  -d '{"repo_ref": "release-2.0", "max_attempts": 5}'
```

### 1.3 조회/삭제

- `GET /api/genuts?page=1&page_size=50` → `{items, total, page, page_size}`
- `GET /api/genuts/{id}`
- `DELETE /api/genuts/{id}` → `204`. 실행 중 job이 있으면 `409`

---

## 2. 프로덕트 등록 (수동 실행용)

### 2.1 생성 — `POST /api/products`

```bash
curl -X POST http://127.0.0.1:8000/api/products \
  -H "Content-Type: application/json" \
  -d '{
    "project": "Ulysses",
    "name": "my-driver",
    "product_code": "P-100",
    "git_url": "ssh://user@gerrit.example.com:29418/platform/my-driver",
    "git_ref": "main",
    "git_update_mode": "reset",
    "code_path": "/data/genut/products/my-driver",
    "compile_db_rel": "build",
    "out_tests_rel": "UnitTest",
    "cmake_configure_cmd": "cmake -S . -B build -G Ninja",
    "cmake_build_cmd": "cmake --build build",
    "test_run_cmd": "ctest --test-dir build",
    "test_generation_mode": "cpp",
    "exclude_globs": ["*test*", "*/legacy/*"],
    "patches": [
      {"name": "gerrit-1234", "content": "diff --git a/... (unified diff 전문)", "order_index": 0}
    ]
  }'
```

| 필드 | 필수 | 기본값 | 설명 |
|---|---|---|---|
| `project` | | `Ulysses` | `Ulysses` \| `Thetis`. 배타 규칙은 (project, name) 기준 |
| `name` | ✅ | — | 프로덕트 이름. **중복 허용**(id로 구분). 같은 (project, name)은 동시에 1개 job만 실행 |
| `product_code` | ✅ | — | 등록 ID(표시용) |
| `git_url` | ✅ | — | 프로덕트 repo 주소 |
| `git_ref` | | `main` | 브랜치명. `origin/` 접두 자동 제거·미존재 ref는 실행 시 명확히 실패 |
| `git_update_mode` | | `reset` | `reset`=원격 최신 강제 일치(로컬 커밋 삭제) \| `rebase`=로컬 커밋(cherry-pick) 유지, 충돌 시 job 실패 |
| `code_path` | | null | 영속 체크아웃 경로(절대 권장). 지정 시 매 job 제자리 업데이트 + 생성 테스트가 영속으로 남음. **자동 실행 모드는 필수** |
| `compile_db_rel` | ✅ | — | compile_commands.json이 있는 폴더(프로덕트 루트 기준 상대) |
| `out_tests_rel` | ✅ | — | 생성 테스트 출력 폴더(상대). 갱신(reset) 시에도 보존됨 |
| `cmake_configure_cmd` / `cmake_build_cmd` / `test_run_cmd` | ✅ | — | GENUT `.env`로 전달되는 빌드/테스트 명령 |
| `test_generation_mode` | | `cpp` | `c` \| `cpp` \| `kunit` |
| `exclude_globs` | | `[]` | 테스트 대상 수집 시 path 기준 제외 글롭 |
| `patches` | | `[]` | 체크아웃 직후 `order_index` 순으로 멱등 적용되는 unified diff 목록 |
| `active` | | `true` | |

응답: `201` + 프로덕트(JSON, `id` 포함).

### 2.2 수정/조회/삭제

- `PUT /api/products/{id}` — **부분 수정**(보낸 필드만). `patches`를 보내면 전체 교체
- `GET /api/products?page=&page_size=&q=<이름 검색>` / `GET /api/products/{id}`
- `DELETE /api/products/{id}` → `204`. 관련 job 이력도 함께 삭제. 실행 중 job이 있으면 `409`

---

## 3. 자동 실행 프로덕트 등록

주기마다 변경 감지(auto_diff)·누락 테스트 스캔(auto_scan)이 돌고 함수 단위 GENUT job이
자동 큐잉된다. **전용 엔드포인트**를 사용한다(일반 엔드포인트와 달리 스캐폴딩 생성 포함).

### 3.1 생성 — `POST /api/products/auto`

2.1의 필드에 아래가 추가/강제된다:

| 필드 | 필수 | 설명 |
|---|---|---|
| `product_code` | ✅ | **`auto`로 시작해야 함**(아니면 400) |
| `code_path` | ✅(사실상) | 자동 실행은 영속 체크아웃 필수 — 없으면 준비 job이 오류로 실패 |
| `auto_interval_seconds` | ✅ | 자동 수행 주기(초). 예: 86400=1일 |
| `auto_file_list` | ✅ | 자동 생성 대상 파일 목록(루트 기준 상대). UI의 "대상 파일 미리보기" 확정본에 해당 |
| `cmake_template` | | 파일별 CMakeLists 양식(placeholder `filename` → 파일 stem). 비우면 기본 gtest 양식 |

```bash
curl -X POST http://127.0.0.1:8000/api/products/auto \
  -H "Content-Type: application/json" \
  -d '{
    "name": "auto-driver", "product_code": "auto-P100",
    "git_url": "...", "git_ref": "main",
    "code_path": "/data/genut/products/auto-driver",
    "compile_db_rel": "build", "out_tests_rel": "UnitTest",
    "cmake_configure_cmd": "cmake -S . -B build", "cmake_build_cmd": "cmake --build build",
    "test_run_cmd": "ctest --test-dir build", "test_generation_mode": "cpp",
    "auto_interval_seconds": 86400,
    "auto_file_list": ["src/aaa.c", "src/bbb.c"]
  }'
```

저장 시 동작: 체크아웃을 준비하고 `out_tests_rel`에 CMakeLists 스캐폴딩
(양식1 `add_subdirectory(...)` + 파일별 양식2)을 생성/갱신한다.
**`test_generation_mode: kunit`이면 스캐폴딩을 만들지 않는다**(커널 빌드는 CMake 무관).

### 3.2 수정 / 즉시 실행

- `PUT /api/products/{id}/auto` — 전체 값으로 수정(스캐폴딩 재생성 포함)
- `POST /api/products/{id}/auto/run` — **주기와 무관하게 지금 1사이클 큐잉**(감지→스캔).
  이전 사이클이 진행 중이면 409

---

## 4. 등록 후 테스트 생성 요청 (참고)

```bash
# 수동 job 제출 — files는 프로덕트 루트 기준 상대경로 목록
curl -X POST http://127.0.0.1:8000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{"product_id": 1, "files": ["src/aaa.c"], "function_name": null}'

# 상태 폴링
curl http://127.0.0.1:8000/api/jobs/1
```

compile_commands.json에 없는 파일은 자동으로 `excluded_files`로 분리되어 실행에서 빠진다.

---

## 5. 대량 등록 스크립트 예시 (Python)

```python
import json, urllib.request

BASE = "http://127.0.0.1:8000/api"

def post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode("utf-8"),   # 한글 포함 시에도 UTF-8 바이트로
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))

# 워커 5개
for i in range(1, 6):
    post("/genuts", {
        "name": f"worker-{i}",
        "repo_url": "ssh://git@git.example.com/tools/GENUT.git",
        "ds_assist_credential_key": "KEY",
        "ds_assist_send_system_name": "my-system",
        "code_path": f"/data/genut/workers/worker-{i}",
    })

# 프로덕트 N개 (CSV/목록에서 읽어 반복)
for row in load_products():   # name, code, url, ...
    post("/products", {
        "name": row.name, "product_code": row.code, "git_url": row.url,
        "compile_db_rel": "build", "out_tests_rel": "UnitTest",
        "cmake_configure_cmd": row.configure, "cmake_build_cmd": row.build,
        "test_run_cmd": row.test, "test_generation_mode": row.mode,
        "code_path": f"/data/genut/products/{row.name}",
    })
```

---

## 6. 흔한 오류와 인코딩 주의

| 상태 | 의미 |
|---|---|
| `422` | 필드 검증 실패 — 응답 `detail`에 필드와 사유. 예: ref가 `origin/`뿐, code_path 빈 값 |
| `409` | GENUT 이름 중복 / 실행 중 항목 삭제 / auto 사이클 중복 실행 |
| `404` | 대상 id 없음 |
| `400` | auto 접두 누락(`/products/auto`), git 실패(다운로드 등) |

**Windows/PowerShell 주의**: 한글이 들어간 본문을 `curl.exe -d`나 `Invoke-RestMethod`로
보낼 때 콘솔 인코딩(cp949) 때문에 깨질 수 있다. 안전한 방법:

```powershell
# 본문을 UTF-8(BOM 없음) 파일로 저장 후 전송
[IO.File]::WriteAllText("body.json", $json, (New-Object Text.UTF8Encoding $false))
curl.exe -X POST http://127.0.0.1:8000/api/products -H "Content-Type: application/json" --data-binary "@body.json"
```

또는 위 5장의 Python 스크립트처럼 UTF-8 바이트로 직접 인코딩해 보내는 것을 권장한다.
(참고: JSON **본문**의 UTF-8 BOM은 서버가 허용하므로 `Set-Content -Encoding utf8`로 만든
파일도 동작한다. 다만 이 프로젝트에서 BOM은 다른 곳(compile_commands.json 등 파일 계열)
에서 문제를 일으킨 전력이 있어, 습관적으로 무BOM을 권장한다.)
