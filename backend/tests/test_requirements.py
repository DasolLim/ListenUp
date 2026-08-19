"""The ML pins must name versions that actually exist.

`requirements-ml.txt` asked for `torchaudio>=2.13`. **There is no torchaudio
2.13** — the project's latest is 2.11.0, because torchaudio's version numbers
lag torch's (torch 2.13 pairs with torchaudio 2.11). The pin was unsatisfiable
on every platform, and nothing noticed for two reasons: the local virtualenv was
built before the pin drifted and already had 2.11.0 installed, and CI never
installs `requirements-ml.txt` at all.

It surfaced the first time the Docker image was built, as a `pip` resolution
failure — which is to say it would have surfaced on the first Railway deploy.

This test compares each pin against what is **installed**, which catches an
aspirational pin without needing a network or a container. It skips when the ML
extras are absent, because CI deliberately does not install them.
"""

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import pytest
from packaging.requirements import Requirement

REQUIREMENTS = Path(__file__).resolve().parents[1] / "requirements-ml.txt"


def pins() -> list[Requirement]:
    return [
        Requirement(line.strip())
        for line in REQUIREMENTS.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]


@pytest.mark.parametrize("pin", pins(), ids=lambda p: p.name)
def test_the_installed_version_satisfies_the_pin(pin: Requirement):
    try:
        installed = version(pin.name)
    except PackageNotFoundError:
        pytest.skip(f"{pin.name} not installed — ML extras are optional in CI")
    assert pin.specifier.contains(installed, prereleases=True), (
        f"requirements-ml.txt asks for {pin}, but {pin.name} {installed} is "
        f"installed. Either the pin names a version that does not exist, or "
        f"this environment is stale — check which before changing either."
    )
