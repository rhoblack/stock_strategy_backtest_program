"""pytest 공통 설정 및 픽스처.

각 모듈별 픽스처는 tests/<module>/conftest.py에 둔다.

표준 fixture 경로 (12번 §15.2):
  FIXTURES_DIR — tests/fixtures/  : 공유 전략 JSON 등 소규모 fixture 파일
  GOLDEN_DIR   — tests/golden/    : golden test 전용 (fixtures/ strategies/ expected/)

@pytest.mark.realdata 마커:
  pykrx 네트워크 호출이 필요한 테스트에만 사용.
  기본 pytest 실행에서 자동 skip 됨.
  활성화: PYTEST_REALDATA=1 환경변수 또는 --realdata 플래그.
"""

import os
import sys
from pathlib import Path

import pytest

# backend/ 디렉토리를 sys.path에 추가하여 `from app...` import 가능하게 함.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# fixture 경로 상수 — 테스트에서 FIXTURES_DIR / "strategy_*.json" 으로 사용
TESTS_DIR = Path(__file__).parent
FIXTURES_DIR = TESTS_DIR / "fixtures"
GOLDEN_DIR = TESTS_DIR / "golden"


def pytest_configure(config: pytest.Config) -> None:
    """realdata 마커를 ini에 등록 (--strict-markers 경고 방지)."""
    config.addinivalue_line(
        "markers",
        "realdata: 실 시장데이터(pykrx 네트워크) 필요 테스트. "
        "PYTEST_REALDATA=1 환경변수 또는 --realdata 플래그로 활성화.",
    )


def pytest_addoption(parser: pytest.Parser) -> None:
    """--realdata CLI 플래그 등록."""
    import contextlib

    with contextlib.suppress(ValueError):
        parser.addoption(
            "--realdata",
            action="store_true",
            default=False,
            help="pykrx 실데이터 테스트 활성화",
        )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """realdata 마커가 없으면 @pytest.mark.realdata 테스트를 자동 skip."""
    realdata_enabled: bool = config.getoption(
        "--realdata", default=False
    ) or os.environ.get("PYTEST_REALDATA", "") == "1"
    if realdata_enabled:
        return
    skip_marker = pytest.mark.skip(
        reason="실데이터 테스트 비활성화 (PYTEST_REALDATA=1 또는 --realdata 필요)"
    )
    for item in items:
        if item.get_closest_marker("realdata"):
            item.add_marker(skip_marker)
