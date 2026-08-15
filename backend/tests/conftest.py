"""Tests are hermetic: always mock services, regardless of the root .env
(app.main loads it at import, and a developer's .env may say `real`)."""

import os

os.environ["TRANSCRIPTION_SERVICE"] = "mock"
os.environ["SPEAKER_ID_SERVICE"] = "mock"
os.environ["TRANSLATION_SERVICE"] = "mock"
os.environ["ENHANCED_TRANSLATION_SERVICE"] = "mock"
os.environ["GENZ_EXPLAINER_SERVICE"] = "mock"
os.environ["TEXT_EMBEDDER"] = "hashing"
os.environ["TTS_SERVICE"] = "browser"  # free tier; never call a paid voice API in tests
os.environ.pop("MOCK_FIXTURE", None)

# The slang KB writes ingested terms and gap-log lines to GENZ_DATA_DIR. Left at
# its default that is the checked-out `services/genz/data/`, so running the suite
# files real curation demand for strings like "zzblargh nonsense" — 128 such lines
# had accumulated by the time this was noticed. Task 3 promotes gaps into the KB,
# which makes a polluted log a correctness problem, not just untidiness.
import tempfile  # noqa: E402

os.environ["GENZ_DATA_DIR"] = tempfile.mkdtemp(prefix="listenup-genz-test-")

from contextlib import contextmanager  # noqa: E402

import pytest  # noqa: E402

TEST_USER = "11111111-1111-1111-1111-111111111111"


@pytest.fixture(autouse=True)
def _no_leaked_mock_fixture():
    """Clear MOCK_FIXTURE between tests.

    The transcribe socket writes the requested fixture into the environment, so
    without this a test that asks for one silently changes what every later
    test transcribes — including tests that deliberately send no fixture at all.
    """
    yield
    os.environ.pop("MOCK_FIXTURE", None)


@pytest.fixture(autouse=True)
def _isolated_translation_cache(monkeypatch):
    """Every test gets its own empty, memory-backed translation cache.

    Without this a developer with Redis running gets different results from CI:
    entries survive between tests and between runs, so a "cache hit" assertion
    can pass for the wrong reason or fail because an earlier test already
    populated the key. Two modules already did this locally; doing it globally
    means a new test can't accidentally depend on the machine it runs on.
    """
    from services.translate import cache as cache_module

    isolated = cache_module.TranslationCache()
    isolated._connected = True  # skip the Redis probe → memory backend
    monkeypatch.setattr(cache_module, "_cache", isolated)


@contextmanager
def acting_as(tier: str = "pro", **used: int):
    """Run a request as a subscriber on `tier`, having already used `**used`.

    Overrides the one dependency every gated route resolves through, so a test
    picks a plan and a spend level rather than stubbing PostgREST. Usage keys are
    the plan metrics: captions, translated, explain, cloud_tts.

        with acting_as("basic", translated=155_000):
            assert client.post("/translate", json=...).status_code == 402

    Recording usage inside the block is a no-op: `record` swallows the missing
    Supabase config, which is the same fail-open path production takes when the
    database is unreachable.
    """
    from app.main import app
    from app.plans import PLANS
    from app.routes.billing import Caller, caller
    from app.usage import EMPTY, Usage

    totals = dict(EMPTY)
    totals.update(used)
    row = (
        {}
        if tier == "free"
        else {
            "user_id": TEST_USER,
            "status": "active",
            "tier": tier,
            "stripe_customer_id": "cus_test",
            "current_period_end": "2099-01-01T00:00:00+00:00",
        }
    )
    who = Caller(
        TEST_USER,
        "test-token",
        row,
        PLANS[tier],
        Usage(totals, period_start="2026-08-12T00:00:00+00:00",
              period_end="2026-09-12T00:00:00+00:00"),
    )

    app.dependency_overrides[caller] = lambda: who
    try:
        yield who
    finally:
        app.dependency_overrides.pop(caller, None)
