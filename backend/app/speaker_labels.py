"""Provider diarization label → the "Speaker N" a reader sees.

Split out of the websocket route because it is a decision the product makes,
not a detail of the transport: the speaker-identity evaluation harness has to
drive the same mapping the socket does, and it was reaching into a route module
to get at it.
"""

# INTRODUCTION §5: cap at 4–5 speakers. Four named lanes (matching the four
# speaker tints in the UI) + everyone past the cap collapses into "Other".
NAMED_SPEAKER_CAP = 4


class SpeakerMapper:
    """Stable provider-label → display-label mapping, capped.

    Diarization labels are the key, but they are not the identity: one voice is
    routinely split across several of them, which is how a single person came
    out as Speaker 1, 2 and 3. `alias()` lets the voice clustering fold one
    label onto another, so the display label follows the person.

    Aliasing rather than re-keying on voice ids on purpose: the numbering, the
    cap and the tap-to-correct lookup all key on the provider label already, and
    a second namespace flowing through the same map would let interim turns
    (labelled before any audio has been judged) and final turns consume separate
    Speaker slots — which exhausts the cap and renumbers everyone.
    """

    def __init__(self) -> None:
        self._order: dict[str, str] = {}
        # provider label → the label whose display name it borrows.
        self._alias: dict[str, str] = {}
        # Numbers issued so far. Monotonic on purpose: see `_next_label`.
        self._issued = 0

    def alias(self, raw: str, onto: str) -> None:
        """Fold `raw` onto the speaker already displayed for `onto`."""
        if raw == onto:
            return
        self._alias[raw] = self._alias.get(onto, onto)
        # Release the slot this label held on its own. A label is usually
        # displayed once (as an interim) before the audio is judged, and leaving
        # that reservation behind spends the speaker cap on people who turned
        # out not to exist — a two-person conversation reaching "Other".
        self._order.pop(raw, None)

    def _next_label(self) -> str:
        """The next speaker number, never one already shown this session.

        Monotonic rather than lowest-unused. Reusing a released number meant
        "Speaker 2" could be Julie early in a conversation and Mom later, which
        is worse than the gap it saves: a reader following a conversation by
        label has no way to know the number changed hands. Numbers are cheap;
        the identity behind one has to be stable for the whole session.

        The cap counts speakers *currently* displayed, so folding a label frees
        capacity without recycling its number.
        """
        if len(self._order) >= NAMED_SPEAKER_CAP:
            return "Other"
        self._issued += 1
        return f"Speaker {self._issued}"

    def label(self, raw: str) -> str:
        raw = self._alias.get(raw, raw)
        if raw not in self._order:
            self._order[raw] = self._next_label()
        return self._order[raw]

    def raw_for(self, label: str) -> str | None:
        for raw, mapped in self._order.items():
            if mapped == label:
                return raw
        return None
