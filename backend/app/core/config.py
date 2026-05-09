"""애플리케이션 설정.

Phase 1에서는 단순 dataclass 형태로 시작.
Phase 2에서 환경변수, .env 파일 지원을 추가할 예정.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """애플리케이션 설정. 불변 객체로 관리."""

    project_root: Path
    data_dir: Path
    log_level: str = "INFO"

    @classmethod
    def default(cls) -> "Settings":
        project_root = Path(__file__).resolve().parents[2]
        return cls(
            project_root=project_root,
            data_dir=project_root.parent / "data",
            log_level="INFO",
        )


settings = Settings.default()
