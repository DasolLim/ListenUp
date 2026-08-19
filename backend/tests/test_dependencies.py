"""Everything the app imports must be declared in a requirements file.

`app/routes/billing.py` does `import stripe` at module scope, `app/main.py`
imports the billing router, and **`stripe` appears in no requirements file at
all**. It is not a transitive dependency of anything either — a clean install
simply does not have it.

Nothing caught this. The local virtualenv has stripe because somebody installed
it by hand at some point, and CI has never run on the code that needs it: a
clean `pip install -r requirements-dev.txt` followed by `pytest` fails at
collection, because collecting imports `app.main`.

It surfaced when the container was first built and refused to start:

    File "/srv/app/routes/billing.py", line 28, in <module>
        import stripe
    ModuleNotFoundError: No module named 'stripe'

That is a deploy that never serves a request. This test finds the same class of
defect offline, in milliseconds, without a container.
"""

import ast
import sys
from importlib.metadata import packages_distributions
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
SOURCE_DIRS = ("app", "services")
REQUIREMENTS = ("requirements.txt", "requirements-ml.txt", "requirements-dev.txt")

#: Imported by name from inside this repo rather than installed.
FIRST_PARTY = {"app", "services", "scripts", "tests"}


def imported_modules() -> dict[str, set[Path]]:
    """Top-level module name -> the files that import it.

    Every import is collected, not only module-scope ones: a lazy import of an
    undeclared package still fails, just later and on a user's request rather
    than at startup.
    """
    found: dict[str, set[Path]] = {}
    for directory in SOURCE_DIRS:
        for path in (BACKEND / directory).rglob("*.py"):
            tree = ast.parse(path.read_text(), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    # `level > 0` is a relative import — always first-party.
                    names = [node.module] if node.module and not node.level else []
                else:
                    continue
                for name in names:
                    root = name.split(".")[0]
                    found.setdefault(root, set()).add(path.relative_to(BACKEND))
    return found


def declared_distributions() -> set[str]:
    """Distribution names named in any requirements file, normalised.

    `httpx>=0.27`, `uvicorn[standard]>=0.30` and `sentry-sdk[fastapi]` all
    reduce to their distribution name.
    """
    declared: set[str] = set()
    for filename in REQUIREMENTS:
        for line in (BACKEND / filename).read_text().splitlines():
            line = line.strip()
            if not line or line.startswith(("#", "-")):
                continue
            name = line.split("[")[0].split("=")[0].split(">")[0].split("<")[0]
            declared.add(name.strip().lower().replace("_", "-"))
    return declared


def test_every_third_party_import_is_declared():
    third_party = {
        module: files
        for module, files in imported_modules().items()
        if module not in FIRST_PARTY and module not in sys.stdlib_module_names
    }
    mapping = packages_distributions()
    declared = declared_distributions()

    undeclared: list[str] = []
    for module, files in sorted(third_party.items()):
        distributions = mapping.get(module)
        if distributions is None:
            # Installed nowhere we can see. Either it is vendored, or the import
            # is already broken locally — a louder failure than this test.
            continue
        names = {d.lower().replace("_", "-") for d in distributions}
        if not names & declared:
            where = ", ".join(sorted(str(f) for f in files)[:3])
            undeclared.append(f"{module} (from {'/'.join(sorted(names))}) — imported by {where}")

    assert not undeclared, (
        "Imported but declared in no requirements file. A deploy built from "
        "these files will fail to start:\n  " + "\n  ".join(undeclared)
    )


def test_the_scan_actually_sees_imports():
    """Guard on the guard. If the AST walk silently found nothing — a moved
    directory, a rename — the test above would pass by scanning an empty set."""
    modules = imported_modules()
    assert len(modules) > 20, f"only {len(modules)} modules scanned; the walk is broken"
    assert "fastapi" in modules and "httpx" in modules
