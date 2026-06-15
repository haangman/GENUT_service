# GENUT_service

GENUT(테스트 자동생성 도구)를 여러 워커로 **병렬 실행**하여, 다수의 대상 프로덕트(C/C++/kunit)에 대해 단위 테스트를 생성하는 서비스다.

- 백엔드: FastAPI + SQLAlchemy(SQLite→Postgres) + 인앱 스케줄러(자체 완결형 큐/락)
- 워커 실행: job마다 Docker 컨테이너 격리
- 프론트엔드: React + Vite (`frontend/`)

자세한 개발 규칙은 [CLAUDE.md](./CLAUDE.md), 설계/로드맵은 계획 문서를 참고한다.

## 개발 환경 (백엔드)

```bash
python -m venv .venv
. .venv/Scripts/activate        # Windows (bash). PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest                          # 전체 테스트
genut-service serve             # 개발 서버 (http://127.0.0.1:8000)
```

## 마일스톤

`M0` 스캐폴딩 → `M1` 데이터 모델 → `M2` 프로덕트 등록 → `M3` 파일트리/compile_commands 검사 → `M4` 요청 제출 → `M5` 스케줄러/동시성 → `M6` GENUT 등록 → `M7` runner+fake+가상프로덕트 → `M8` Docker → `M9` 모니터링 → `M10` prod 서빙/Postgres.
