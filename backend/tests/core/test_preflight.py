"""A deploy that is missing config should fail at startup, not at first use.

Every service in this app falls back to a mock when its env var is unset, which
is exactly right for development and exactly wrong for production: a deploy with
no `ASSEMBLYAI_API_KEY` starts cleanly, reports healthy, and then serves the
first real user a mock transcript of a fixture conversation. The failure surfaces
as "captions are nonsense", days later, to a user.

`check_production_config` is pure — it takes the environment as a mapping rather
than reading `os.environ` — so these tests can state a deploy's config exactly
without fighting `conftest.py`, which pins every service to `mock`.
"""

from app.preflight import Severity, check_production_config

PROD = {
    "APP_ENV": "production",
    "TRANSCRIPTION_SERVICE": "real",
    "ASSEMBLYAI_API_KEY": "sk-test",
    "TRANSLATION_SERVICE": "google",
    "GOOGLE_CLOUD_PROJECT_ID": "proj",
    "ENHANCED_TRANSLATION_SERVICE": "real",
    "GENZ_EXPLAINER_SERVICE": "real",
    "OPENROUTER_API_KEY": "or-test",
    "SPEAKER_ID_SERVICE": "real",
    "SUPABASE_URL": "https://x.supabase.co",
    "SUPABASE_ANON_KEY": "anon",
    "FRONTEND_ORIGIN": "https://listenup.app",
    "REDIS_URL": "rediss://x",
}


def problems(env: dict[str, str], severity: Severity | None = None) -> list[str]:
    found = check_production_config(env)
    return [p.message for p in found if severity is None or p.severity == severity]


def test_a_complete_production_config_has_no_errors():
    assert problems(PROD, Severity.ERROR) == []


def test_a_real_stt_provider_without_its_key_is_an_error():
    """The exact deploy that starts healthy and serves fixture captions."""
    env = PROD | {"ASSEMBLYAI_API_KEY": ""}
    assert any("ASSEMBLYAI_API_KEY" in m for m in problems(env, Severity.ERROR))


def test_each_real_service_requires_its_own_credential():
    for service, flag, key in [
        ("TRANSCRIPTION_SERVICE", "real", "ASSEMBLYAI_API_KEY"),
        ("TRANSLATION_SERVICE", "google", "GOOGLE_CLOUD_PROJECT_ID"),
        ("ENHANCED_TRANSLATION_SERVICE", "real", "OPENROUTER_API_KEY"),
        ("TTS_SERVICE", "elevenlabs", "ELEVENLABS_API_KEY"),
    ]:
        env = PROD | {service: flag}
        env.pop(key, None)
        assert any(key in m for m in problems(env, Severity.ERROR)), (
            f"{service}={flag} did not require {key}"
        )


def test_running_on_mocks_in_production_is_an_error():
    """Shipping the mock provider is the failure this whole module exists for:
    it is the one misconfiguration that looks completely healthy."""
    env = PROD | {"TRANSCRIPTION_SERVICE": "mock"}
    assert any("mock" in m.lower() for m in problems(env, Severity.ERROR))


def test_development_is_left_alone():
    """Mocks are the correct default outside production (INTRODUCTION §6) — this
    check must never make a developer set up credentials to run the app."""
    assert check_production_config({"TRANSCRIPTION_SERVICE": "mock"}) == []


def test_a_missing_cache_is_a_warning_not_an_error():
    """Redis is what makes a repeated phrase free. Without it the app still
    works and every cache hit becomes a billed call instead — a cost defect, not
    an outage, so it must not stop a deploy."""
    env = dict(PROD)
    env.pop("REDIS_URL")
    assert problems(env, Severity.ERROR) == []
    assert any("REDIS" in m for m in problems(env, Severity.WARNING))


def test_the_frontend_origin_must_be_set_and_must_not_be_localhost():
    """CORS defaults to a localhost origin. A production deploy that keeps it
    rejects every request from the real site — and the browser reports it as a
    CORS error, which reads like a frontend bug."""
    missing = problems(PROD | {"FRONTEND_ORIGIN": ""}, Severity.ERROR)
    assert any("FRONTEND_ORIGIN" in m for m in missing)
    assert any(
        "FRONTEND_ORIGIN" in m
        for m in problems(PROD | {"FRONTEND_ORIGIN": "http://localhost:3000"}, Severity.ERROR)
    )


def test_every_problem_says_what_to_do_about_it():
    """A preflight that says 'invalid configuration' has moved the debugging
    session, not shortened it."""
    for problem in check_production_config({"APP_ENV": "production"}):
        assert problem.fix, f"{problem.message} has no remedy"
        assert len(problem.message) > 20
