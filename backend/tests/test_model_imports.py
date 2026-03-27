"""Import smoke tests for backend ORM model modules."""

from importlib import import_module
from pathlib import Path


def test_all_model_modules_are_importable() -> None:
    """Fail fast if a model module is referenced but missing from the package."""
    models_dir = Path(__file__).resolve().parents[1] / "app" / "models"
    module_names = sorted(
        path.stem
        for path in models_dir.glob("*.py")
        if path.name != "__init__.py" and not path.name.startswith("_")
    )

    for module_name in module_names:
        import_module(f"app.models.{module_name}")


def test_models_package_imports_cleanly() -> None:
    """Ensure app.models package-level imports stay valid."""
    import_module("app.models")
