"""Which origins may call this API.

A Capacitor app does not run on the website's origin. The iOS WebView serves the
bundle from `capacitor://localhost` and Android (with `androidScheme: "https"`)
from `https://localhost`, so those are the `Origin` values the shipped app sends
on every request. They are **platform constants, not deployment configuration** —
nobody chooses them and no deploy changes them — which is why they are written
here rather than expected in an environment variable somebody would have to
know to set.

Everything that *is* a deployment choice comes from the environment.
"""

from collections.abc import Mapping

#: What a Capacitor WebView sends. Both, always: iOS and Android produce
#: different origins from one codebase, so allowing only the platform you
#: happened to test on ships broken on the other.
CAPACITOR_ORIGINS = ("capacitor://localhost", "https://localhost")

DEFAULT_WEB_ORIGIN = "http://localhost:3000"


def allowed_origins(env: Mapping[str, str]) -> list[str]:
    """Every origin permitted to make a browser request, in priority order.

    Refuses `*` rather than passing it through. A wildcard is the obvious way to
    make a stubborn CORS error go away, and it is the one this API must not
    take: it carries bearer tokens and biometric voice data. Starlette would
    also silently drop credentials for a wildcard, so the "fix" would appear to
    work while breaking authentication in a way nobody would connect to CORS.
    """
    web = (env.get("FRONTEND_ORIGIN") or DEFAULT_WEB_ORIGIN).strip()
    extra = [
        origin.strip()
        for origin in (env.get("EXTRA_CORS_ORIGINS") or "").split(",")
        if origin.strip()
    ]

    for origin in [web, *extra]:
        if "*" in origin:
            raise ValueError(
                f"Refusing the CORS origin {origin!r}: this API carries bearer "
                "tokens and biometric data, so '*' is never the right answer. "
                "List the origins explicitly in FRONTEND_ORIGIN and "
                "EXTRA_CORS_ORIGINS."
            )

    # dict.fromkeys rather than a set: order is stable, which keeps the logged
    # configuration readable and diffable between deploys.
    return list(dict.fromkeys([web, *CAPACITOR_ORIGINS, *extra]))
