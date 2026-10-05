import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _requirements() -> set[str]:
    lines = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip() and not line.startswith("#")}


def test_pyproject_and_requirements_pin_the_same_versions():
    # requirements.txt alimenta o Docker e o CI; pyproject.toml, o `pip install .`.
    # Uma versão trocada em só um dos dois faria os ambientes divergirem.
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    declared = set(project["dependencies"]) | set(project["optional-dependencies"]["dev"])
    assert declared == _requirements()
