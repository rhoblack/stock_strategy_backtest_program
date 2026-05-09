"""pytest 공통 설정 및 픽스처.

각 모듈별 픽스처는 tests/<module>/conftest.py에 둔다.
"""

import sys
from pathlib import Path

# backend/ 디렉토리를 sys.path에 추가하여 `from app...` import 가능하게 함.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
