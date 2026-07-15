from __future__ import annotations

import ast
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "backend"

IMPORT_TO_REQUIREMENT = {
    "joblib": "joblib",
    "narwhals": "narwhals",
    "numpy": "numpy",
    "pandas": "pandas",
    "packaging": "packaging",
    "scipy": "scipy",
    "sklearn": "scikit-learn",
    "threadpoolctl": "threadpoolctl",
}

SKLEARN_RUNTIME_REQUIREMENTS = {
    "numpy",
    "scipy",
    "joblib",
    "threadpoolctl",
    "narwhals",
}


def _requirements_names() -> set[str]:
    names: set[str] = set()
    for raw_line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name = line.split("==", 1)[0].split(">=", 1)[0].split("<=", 1)[0].strip().lower()
        names.add(name)
    return names


def _local_backend_module_path(module_name: str) -> Path | None:
    if not module_name.startswith("backend."):
        return None
    relative = module_name.split(".")[1:]
    module_path = BACKEND_ROOT.joinpath(*relative).with_suffix(".py")
    if module_path.exists():
        return module_path
    package_path = BACKEND_ROOT.joinpath(*relative, "__init__.py")
    return package_path if package_path.exists() else None


def _resolve_relative_module(current_module: str, level: int, imported: str | None) -> str:
    parts = current_module.split(".")
    base = parts[: max(1, len(parts) - level)]
    if imported:
        base.extend(imported.split("."))
    return ".".join(base)


def _runtime_import_graph(start: Path) -> set[str]:
    queue = [start]
    seen_files: set[Path] = set()
    external_imports: set[str] = set()

    while queue:
        path = queue.pop()
        path = path.resolve()
        if path in seen_files:
            continue
        seen_files.add(path)
        current_module = "backend." + path.relative_to(BACKEND_ROOT).with_suffix("").as_posix().replace("/", ".")
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        for node in ast.walk(tree):
            module_name: str | None = None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top_level = alias.name.split(".", 1)[0]
                    if top_level == "backend":
                        local = _local_backend_module_path(alias.name)
                        if local:
                            queue.append(local)
                    elif top_level in IMPORT_TO_REQUIREMENT:
                        external_imports.add(top_level)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    module_name = _resolve_relative_module(current_module, node.level, node.module)
                elif node.module:
                    module_name = node.module

                if not module_name:
                    continue
                top_level = module_name.split(".", 1)[0]
                if top_level == "backend":
                    local = _local_backend_module_path(module_name)
                    if local:
                        queue.append(local)
                    for alias in node.names:
                        nested = _local_backend_module_path(f"{module_name}.{alias.name}")
                        if nested:
                            queue.append(nested)
                elif top_level in IMPORT_TO_REQUIREMENT:
                    external_imports.add(top_level)

    return external_imports


def test_requirements_txt_covers_backend_predict_runtime_import_graph() -> None:
    required_names = _requirements_names()
    external_imports = _runtime_import_graph(ROOT / "backend" / "predict.py")
    missing = {
        IMPORT_TO_REQUIREMENT[module_name]
        for module_name in external_imports
        if IMPORT_TO_REQUIREMENT[module_name] not in required_names
    }
    assert not missing, (
        "requirements.txt must remain sufficient for run.sh/backend.predict. "
        f"Missing packages for import graph: {sorted(missing)}"
    )
    assert "fastapi" not in required_names
    assert "google-genai" not in required_names
    assert "xgboost" not in required_names
    assert "sklearn" not in sys.stdlib_module_names


def test_requirements_txt_declares_sklearn_runtime_support_dependencies() -> None:
    """Guard the exact-sklearn CI job against incomplete --no-deps environments."""
    required_names = _requirements_names()
    missing = SKLEARN_RUNTIME_REQUIREMENTS - required_names
    assert not missing, (
        "requirements.txt must include sklearn runtime support packages used by "
        f"the evaluator installation path. Missing: {sorted(missing)}"
    )
