"""pytest 공통 설정 및 픽스처.

각 모듈별 픽스처는 tests/<module>/conftest.py에 둔다.

표준 fixture 경로 (12번 §15.2):
  FIXTURES_DIR — tests/fixtures/  : 공유 전략 JSON 등 소규모 fixture 파일
  GOLDEN_DIR   — tests/golden/    : golden test 전용 (fixtures/ strategies/ expected/)
"""

import sys
from pathlib import Path

# backend/ 디렉토리를 sys.path에 추가하여 `from app...` import 가능하게 함.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# fixture 경로 상수 — 테스트에서 FIXTURES_DIR / "strategy_*.json" 으로 사용
TESTS_DIR = Path(__file__).parent
FIXTURES_DIR = TESTS_DIR / "fixtures"
GOLDEN_DIR = TESTS_DIR / "golden"
