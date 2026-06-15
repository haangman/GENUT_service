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

## 마일스톤

`M0` 스캐폴딩 → `M1` 데이터 모델 → `M2` 프로덕트 등록 → `M3` 파일트리/compile_commands 검사 → `M4` 요청 제출 → `M5` 스케줄러/동시성 → `M6` GENUT 등록 → `M7` runner+fake+가상프로덕트 → `M8` Docker → `M9` 모니터링 → `M10` prod 서빙/Postgres.
