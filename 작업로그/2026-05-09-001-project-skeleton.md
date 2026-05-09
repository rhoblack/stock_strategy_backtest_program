---
date: 2026-05-09
agent: main
phase: 1
status: completed
related_docs:
  - 상세설계/stock_strategy_lab_software_architecture.md
  - 상세설계/00_index.md
---

# Phase 1 / Step 1 — 백엔드 프로젝트 골격 셋업

## Plan

설계서 architecture 2~3절의 폴더 구조에 맞춰 backend 패키지 골격 생성. Phase 1에서 바로 쓸 모듈은 실제 파일 일부 작성하고, 나머지는 빈 `__init__.py`만 두어 의도를 명시.

- [x] backend/ 디렉토리 + 모듈 디렉토리 생성 (core/api/db/models/schemas/services/strategy/backtest/portfolio/market_data/reports/exporters)
- [x] tests/ 디렉토리 + 하위 디렉토리 생성
- [x] backend/pyproject.toml 작성 (Phase 1 최소 의존: pandas, numpy, pydantic + dev: pytest, ruff)
- [x] backend/app/core/config.py — 기본 설정 클래스
- [x] backend/app/core/exceptions.py — 커스텀 예외 계층
- [x] backend/app/core/logging.py — 기본 로거 설정
- [x] backend/tests/conftest.py — pytest 공통 픽스처 자리
- [x] backend/.gitignore (Python)
- [x] 패키지 import 가능 검증 (smoke test)

Phase 1에서 채우지 않을 항목은 빈 `__init__.py`만 두고 후속 Phase에서 채움. FastAPI 의존성도 Phase 4에서 추가.

## Execution

```text
backend/pyproject.toml                          Python 3.11+, pandas/numpy/pydantic + dev(pytest, ruff)
backend/.gitignore                              Python 표준 + data 폴더 제외
backend/app/__init__.py                         __version__ = "0.0.1"
backend/app/core/__init__.py                    빈 패키지
backend/app/core/config.py                      Settings dataclass + 기본 인스턴스
backend/app/core/exceptions.py:5                AppError 베이스 + to_dict()
backend/app/core/exceptions.py:25~              13개 도메인 예외 (10번 API 문서 7.1 기반)
backend/app/core/logging.py                     setup_logging / get_logger 헬퍼
backend/app/{api,db,models,schemas,services}/__init__.py    빈 자리 (후속 Phase)
backend/app/strategy/__init__.py
backend/app/strategy/conditions/__init__.py     Phase 1 / Step 4에서 조건 함수 추가 예정
backend/app/{backtest,portfolio,market_data,reports,exporters}/__init__.py
backend/tests/__init__.py
backend/tests/conftest.py                       sys.path에 backend 추가 (pytest용)
backend/tests/{strategy,backtest,portfolio,market_data,api,exporters}/__init__.py
backend/tests/fixtures/.gitkeep
backend/tests/test_smoke.py                     Phase 1/Step 1 검증 5건
```

설계 결정:
- backend/pyproject.toml에 FastAPI/SQLAlchemy를 미리 넣지 않음. 해당 Phase에서 추가하여 의존성 부담을 점진적으로 늘림.
- Settings를 `frozen=True` dataclass로 시작. 환경변수/.env 지원은 Phase 2에서 pydantic-settings로 확장.
- exceptions.py는 10번 API 문서의 에러 코드를 직접 클래스로 매핑. API 레이어가 잡아서 to_dict()로 응답하도록 설계.
- conftest.py에서 sys.path 조작은 임시 방편. `pip install -e .` 후에는 불필요해짐.

## Tests

환경 제약: 시스템 Python(MSYS2 ucrt64)에 pip이 없어 pytest 설치 불가. 동일 검증을 manual runner로 수행.

```text
PASS: test_app_package_importable
PASS: test_core_modules_importable
PASS: test_exception_codes_unique
PASS: test_exception_to_dict_format
PASS: test_module_directories_exist

총 5개 / 통과 5 / 실패 0
```

`backend/tests/test_smoke.py`에 동일 로직이 pytest 형식으로 들어 있으므로 venv가 셋업되면 그대로 `pytest` 실행 가능.

## Issues

- **시스템 Python pip 부재**: MSYS2 ucrt64 Python 3.12에는 pip/ensurepip이 모두 작동하지 않음. → 다음 단계 시작 전 venv 셋업이 선행되어야 함 (Follow-ups 참조).
- **터미널 한글 출력 깨짐**: cp949 환경에서 한글 print가 깨짐. 코드 동작에는 영향 없음. 향후 로깅에서 UTF-8 강제 검토.

## Result

- 추가 파일: 26개 (그 중 빈 `__init__.py` 13개, .gitkeep 1개, 실 코드 5개, 설정 2개, 테스트 2개, 작업로그 1개)
- backend/app/ 13개 모듈 디렉토리 모두 생성, import 정상
- 13개 도메인 예외 코드 정의, 중복 없음 검증 통과
- 테스트 인프라 준비 완료 (conftest.py + smoke test)
- 정확성 정책 13번에 영향 없는 셋업 작업 (정책 위반 가능성 없음)
- 결정론 / look-ahead 검증 항목 없음 (코드 로직 없음)

## Follow-ups

- **Step 2 (다음 작업)**: ConditionRegistry 코어 구현 (`app/strategy/registry.py`)
- **Phase 1 진행 중 추가 의존성**: dataclasses-json 또는 pydantic으로 strategy_json 검증 시점에 추가 검토
- **환경 셋업 (사용자 작업)**: 백엔드 개발용 venv 셋업 권장
  ```bash
  cd backend
  python -m venv .venv
  source .venv/Scripts/activate  # Windows Git Bash
  pip install -e ".[dev]"
  pytest
  ```
  MSYS2 Python 대신 공식 Python 또는 conda 권장.
- **CI 셋업 (Phase 1 종료 시점)**: GitHub Actions로 pytest + ruff 자동 실행 추가
- **Phase 2 진입 시**: backend/app/db/, models/, services/에 SQLAlchemy 모델 채우기

## 메인 세션 마무리 체크

- [x] status를 completed로 변경
- [x] 작업로그/README.md "최근 작업" 표에 1행 추가
- [x] Phase 상태가 변경되었으면 Phase 표 갱신
- [x] Follow-ups 중 다음 작업 후보로 옮길 항목 정리
