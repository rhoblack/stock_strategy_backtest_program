"""Phase 1 / Step 1 smoke test.

프로젝트 골격이 제대로 구성됐는지 확인하는 최소 테스트.
실제 기능 테스트는 모듈별 디렉토리에서 작성.
"""


def test_app_package_importable():
    import app

    assert app.__version__ == "0.0.1"


def test_core_modules_importable():
    from app.core import config, exceptions, logging  # noqa: F401

    assert config.settings.project_root.exists()


def test_exception_codes_unique():
    from app.core import exceptions

    error_classes = [
        cls
        for cls in vars(exceptions).values()
        if isinstance(cls, type)
        and issubclass(cls, exceptions.AppError)
        and cls is not exceptions.AppError
    ]
    codes = [cls.code for cls in error_classes]
    assert len(codes) == len(set(codes)), "에러 코드가 중복됩니다"


def test_exception_to_dict_format():
    from app.core.exceptions import InvalidStrategyJsonError

    err = InvalidStrategyJsonError("매수 조건이 필요합니다.")
    assert err.to_dict() == {
        "error": {
            "code": "INVALID_STRATEGY_JSON",
            "message": "매수 조건이 필요합니다.",
            "details": [],
        }
    }


def test_module_directories_exist():
    """설계서 architecture 3절의 모든 모듈 디렉토리가 존재해야 함."""
    from app.core.config import settings

    app_dir = settings.project_root / "app"
    expected = [
        "core",
        "api",
        "db",
        "models",
        "schemas",
        "services",
        "strategy",
        "strategy/conditions",
        "backtest",
        "portfolio",
        "market_data",
        "reports",
        "exporters",
    ]
    for module_path in expected:
        assert (app_dir / module_path).is_dir(), f"{module_path} 디렉토리 없음"
        assert (app_dir / module_path / "__init__.py").exists(), (
            f"{module_path}/__init__.py 없음"
        )
