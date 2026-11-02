import math

from services.speaker_id.matcher import Match, Profile, SpeakerMatcher


def unit(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vector))
    return [x / norm for x in vector]


# Orthogonal-ish synthetic voices in 4-dim space (matcher is dimension-agnostic).
MOM = unit([1.0, 0.1, 0.0, 0.0])
DAD = unit([0.0, 1.0, 0.1, 0.0])
STRANGER = unit([0.0, 0.0, 0.0, 1.0])


def make_matcher(margin: float = 0.05) -> SpeakerMatcher:
    return SpeakerMatcher(
        [Profile("p1", "Mom", [MOM]), Profile("p2", "Dad", [DAD])],
        threshold=0.6,
        margin=margin,
    )


def test_clear_match_returns_name() -> None:
    result = make_matcher().match(unit([0.95, 0.15, 0.0, 0.0]))
    assert isinstance(result, Match)
    assert result.display_name == "Mom"
    assert result.similarity > 0.9


def test_below_threshold_returns_none() -> None:
    assert make_matcher().match(STRANGER) is None


def test_borderline_similarity_stays_generic() -> None:
    # ~0.55 to Mom: below the 0.6 threshold → no name, per "never force a name".
    nearly = unit([0.55, 0.0, 0.0, 0.835])
    assert make_matcher().match(nearly) is None


def test_ambiguous_between_two_profiles_stays_generic() -> None:
    # Exactly equidistant between two enrolled voices, both above threshold:
    # too close to call → stay generic rather than risk the wrong name.
    matcher = SpeakerMatcher(
        [Profile("p1", "Mom", [unit([1.0, 0.0, 0.0, 0.0])]),
         Profile("p2", "Dad", [unit([0.0, 1.0, 0.0, 0.0])])],
        threshold=0.6,
        margin=0.05,
    )
    assert matcher.match(unit([1.0, 1.0, 0.0, 0.0])) is None  # 0.707 vs 0.707


def test_multi_embedding_profile_uses_best_sample() -> None:
    altered = unit([0.6, 0.0, 0.8, 0.0])  # far from MOM's original
    single = SpeakerMatcher([Profile("p1", "Mom", [MOM])], threshold=0.75, margin=0.05)
    multi = SpeakerMatcher(
        [Profile("p1", "Mom", [MOM, unit([0.62, 0.0, 0.78, 0.0])])],
        threshold=0.75,
        margin=0.05,
    )
    assert single.match(altered) is None, "single-sample profile misses the altered voice"
    result = multi.match(altered)
    assert result is not None and result.display_name == "Mom"


def test_duplicate_profiles_same_person_still_match() -> None:
    # Two enrollments of the SAME person (same name) that both score high must
    # NOT read as ambiguous — the margin guards different people, not duplicates.
    matcher = SpeakerMatcher(
        [
            Profile("p1", "Mom", [MOM]),
            Profile("p2", "Mom", [unit([0.99, 0.11, 0.0, 0.0])]),  # 2nd enrollment
        ],
        threshold=0.6,
        margin=0.05,
    )
    result = matcher.match(unit([0.97, 0.12, 0.0, 0.0]))
    assert result is not None and result.display_name == "Mom"


def test_no_profiles_returns_none() -> None:
    assert SpeakerMatcher([], threshold=0.6, margin=0.05).match(MOM) is None
