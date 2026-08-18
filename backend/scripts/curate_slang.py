"""Curation job: gap log → reviewed KB entries.

Slang ages faster than any model does, so the corpus has to be fed. This reads
the gaps real users hit, resolves them against the web, and queues them for a
human. Nothing here runs during a request — it is a batch job, run by hand or on
a schedule.

    python -m scripts.curate_slang resolve            # queue new candidates
    python -m scripts.curate_slang list [--all]       # review the queue
    python -m scripts.curate_slang promote <term>     # approve → live in the KB
    python -m scripts.curate_slang reject <term> [why]

`resolve` uses the mock resolver unless SLANG_RESOLVER_SERVICE=real, so the loop
can be exercised end to end without spending anything. The real resolver appends
`:online` to OPENROUTER_MODEL so the answer comes from the current web rather
than the model's memory — which is the memory that failed and put the term in
the gap log to begin with.

Promotion is deliberately manual. This corpus feeds STT biasing, translation and
explanations at once, and its readers cannot hear the original to check a wrong
definition against.
"""

from __future__ import annotations

import asyncio
import sys

from services.genz.curation import (
    PENDING,
    Candidate,
    PendingStore,
    promote,
    reject,
    resolve_gaps,
)


def _print_candidate(c: Candidate) -> None:
    mark = {"pending": "?", "promoted": "+", "rejected": "-"}.get(c.status, " ")
    print(f" {mark} {c.term}   ({c.status}, hit {c.seen}×, via {c.resolver})")
    if c.meaning:
        print(f"     {c.meaning}")
    if c.note:
        print(f"     note: {c.note}")
    for url in c.sources:
        print(f"     source: {url}")


def cmd_resolve() -> int:
    stats = asyncio.run(resolve_gaps())
    print(
        f"gaps seen {stats['seen']} · already in KB {stats['already_known']} · "
        f"already decided {stats['already_decided']} · "
        f"queued {stats['resolved']} · auto-rejected {stats['auto_rejected']}"
    )
    if stats["resolved"]:
        print("\nReview them with:  python -m scripts.curate_slang list")
    return 0


def cmd_list(show_all: bool) -> int:
    store = PendingStore()
    rows = store.all() if show_all else store.by_status(PENDING)
    if not rows:
        print("nothing awaiting review" if not show_all else "queue is empty")
        return 0
    for candidate in sorted(rows, key=lambda c: -c.seen):
        _print_candidate(candidate)
    if not show_all:
        print(f"\n{len(rows)} awaiting review. Promote with: promote <term>")
    return 0


def cmd_promote(term: str) -> int:
    result = promote(term)
    if result is None:
        print(f"no pending candidate for {term!r} (already promoted, or rejected)")
        return 1
    print(f"promoted {result.term!r} — it is now retrievable from the KB")
    return 0


def cmd_reject(term: str, note: str) -> int:
    if not reject(term, note):
        print(f"no candidate for {term!r}")
        return 1
    print(f"rejected {term!r}; it will not be queued again")
    return 0


def main() -> int:
    args = sys.argv[1:]
    command = args[0] if args else "list"
    if command == "resolve":
        return cmd_resolve()
    if command == "list":
        return cmd_list("--all" in args)
    if command == "promote" and len(args) > 1:
        return cmd_promote(args[1])
    if command == "reject" and len(args) > 1:
        return cmd_reject(args[1], " ".join(args[2:]))
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
