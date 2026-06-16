# GENUT_service

GENUT(테스트 자동생성 도구)를 여러 워커로 **병렬 실행**하여, 다수의 대상 프로덕트(C/C++/kunit)에 대해 단위 테스트를 생성하는 서비스다.

- 백엔드: FastAPI + SQLAlchemy(SQLite→Postgres) + 인앱 스케줄러(자체 완결형 큐/락)
- 워커 실행: job마다 Docker 컨테이너 격리
- 프론트엔드: React + Vite (`frontend/`)

자세한 개발 규칙은 [CLAUDE.md](./CLAUDE.md), 설계/로드맵은 계획 문서를 참고한다.

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

# 테스트
pytest                                   # 또는: python -m pytest
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
- **인코딩 함정 없음**: cp949 관련 문제(BOM/requirements 한글 주석)는 Windows-한국어 로케일 특유다. Linux(UTF-8)에선 발생하지 않고, git CRLF 경고도 없다.
- 워크스페이스(`WORKSPACE_ROOT`)와 작업 디렉터리는 네이티브 Linux FS에 두자(도커 bind-mount 성능/정합성).

## 마일스톤

`M0` 스캐폴딩 → `M1` 데이터 모델 → `M2` 프로덕트 등록 → `M3` 파일트리/compile_commands 검사 → `M4` 요청 제출 → `M5` 스케줄러/동시성 → `M6` GENUT 등록 → `M7` runner+fake+가상프로덕트 → `M8` Docker → `M9` 모니터링 → `M10` prod 서빙/Postgres.
