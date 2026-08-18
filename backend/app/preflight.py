"""Refuse to start a production deploy that is missing its configuration.

Every external service in this app falls back to a mock when its variable is
unset. That is a deliberate constraint (INTRODUCTION §6 — develop and test
without burning credits) and it is exactly right for development. In production
it is the most dangerous default the app has, because **a misconfigured deploy
looks completely healthy**: it starts, `/health` returns 200, and the first real
user is served a mock transcript of a fixture conversation. Nothing errors. The
failure arrives days later as "the captions are nonsense".

So the check runs only when `APP_ENV=production`, and it is deliberately noisy
about the two things a deploy gets wrong: a real provider with no credential,
and a mock left switched on.

Pure by design — it takes the environment as an argument rather than reading
`os.environ` — so a test can state a deploy's config exactly, and so this module
has nothing to mock.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum


class Severity(Enum):
    #: The deploy is wrong and must not serve traffic.
    ERROR = "error"
    #: The deploy works, but costs more or is harder to operate than it should.
    WARNING = "warning"


@dataclass(frozen=True)
class Problem:
    severity: Severity
    message: str
    #: What to do about it. A preflight that says "invalid configuration" has
    #: moved the debugging session rather than shortened it.
    fix: str


@dataclass(frozen=True)
class _Service:
    """One swappable provider, and what each of its real values needs."""

    var: str
    default: str
    #: Values that mean "not a real provider". Empty when every value is real —
    #: the browser TTS tier is free and genuine, not a stand-in.
    mock_values: tuple[str, ...]
    #: value -> the credential that value cannot work without.
    credentials: Mapping[str, str]
    #: What a user sees when this is left on a mock.
    symptom: str


SERVICES = (
    _Service(
        "TRANSCRIPTION_SERVICE", "mock", ("mock",),
        {"real": "ASSEMBLYAI_API_KEY"},
        "captions replay a fixture conversation instead of the microphone",
    ),
    _Service(
        "SPEAKER_ID_SERVICE", "mock", ("mock",), {},
        "speakers are separated by a stand-in embedder, so naming is meaningless",
    ),
    _Service(
        "TRANSLATION_SERVICE", "mock", ("mock",),
        {"google": "GOOGLE_CLOUD_PROJECT_ID"},
        "translations are canned strings",
    ),
    _Service(
        "ENHANCED_TRANSLATION_SERVICE", "mock", ("mock",),
        {"real": "OPENROUTER_API_KEY"},
        "slang notes come from fixtures, so only known terms are ever explained",
    ),
    _Service(
        "GENZ_EXPLAINER_SERVICE", "mock", ("mock",), {},
        "Explain a term answers from fixtures",
    ),
    _Service(
        "TTS_SERVICE", "browser", (),
        {"elevenlabs": "ELEVENLABS_API_KEY"},
        "",
    ),
)

#: Needed whatever the providers are set to.
REQUIRED = {
    "SUPABASE_URL": "the project URL from Supabase → Settings → API",
    "SUPABASE_ANON_KEY": "the publishable key from Supabase → Settings → API",
}

#: Not fatal, but each one costs money or visibility.
ADVISORY = {
    "REDIS_URL": (
        "no REDIS_URL: the translation and TTS caches fall back to per-process "
        "memory, so a repeated phrase is billed again on every instance",
        "add an Upstash Redis URL — the cache is what makes repeats free",
    ),
    "SENTRY_DSN": (
        "no SENTRY_DSN: backend errors will only exist in log lines nobody reads",
        "set the DSN from your Sentry project",
    ),
}


def check_production_config(env: Mapping[str, str]) -> list[Problem]:
    """Everything wrong with this deploy, worst first. Empty means good to serve.

    Returns rather than raises so a caller can log warnings and fail only on
    errors, and so the whole list is reported at once — finding one missing
    variable per restart is a miserable way to deploy.
    """
    if env.get("APP_ENV", "").strip().lower() != "production":
        return []

    found: list[Problem] = []

    for service in SERVICES:
        value = (env.get(service.var) or service.default).strip().lower()
        if value in service.mock_values:
            found.append(Problem(
                Severity.ERROR,
                f"{service.var}={value} in production — {service.symptom}",
                f"set {service.var} to a real provider "
                f"({' or '.join(sorted(service.credentials)) or 'see .env.example'})",
            ))
            continue
        credential = service.credentials.get(value)
        if credential and not (env.get(credential) or "").strip():
            found.append(Problem(
                Severity.ERROR,
                f"{service.var}={value} but {credential} is not set",
                f"set {credential}, or switch {service.var} to another provider",
            ))

    for var, where in REQUIRED.items():
        if not (env.get(var) or "").strip():
            found.append(Problem(
                Severity.ERROR, f"{var} is not set — authentication cannot work",
                f"set {var} to {where}",
            ))

    origin = (env.get("FRONTEND_ORIGIN") or "").strip()
    if not origin:
        found.append(Problem(
            Severity.ERROR,
            "FRONTEND_ORIGIN is not set — CORS will reject the real site, and the "
            "browser reports that as a frontend bug",
            "set it to the deployed web origin, e.g. https://listenup.app",
        ))
    elif "localhost" in origin or "127.0.0.1" in origin:
        found.append(Problem(
            Severity.ERROR,
            f"FRONTEND_ORIGIN={origin} in production — every request from the "
            "deployed site will fail CORS preflight",
            "set it to the deployed web origin, not a development one",
        ))

    for var, (message, fix) in ADVISORY.items():
        if not (env.get(var) or "").strip():
            found.append(Problem(Severity.WARNING, message, fix))

    return found


def format_problems(problems: list[Problem]) -> str:
    return "\n".join(f"  [{p.severity.value}] {p.message}\n      fix: {p.fix}" for p in problems)
