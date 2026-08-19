/**
 * What the server can say about a transcript, and what it does to one.
 *
 * Run: `node scripts/verify-caption-stream.mjs` from /frontend.
 *
 * Four of these rules lived inside the websocket `onmessage` handler, where the
 * only way to reach them was to open a socket in a browser — and three of them
 * are corrections to what is *already on screen*, which is precisely the class
 * a reader cannot check by ear: a name back-filled onto the wrong person's
 * earlier lines, or a merge that fails to regroup two halves of one voice.
 */
import { harness, loadTs } from "./lib/harness.mjs";

const { applyCaptionMessage, segmentFrom } = await loadTs(
  new URL("../lib/captionStream.ts", import.meta.url)
);

const h = harness();

const line = (over = {}) => ({
  id: "a",
  speaker: "Speaker 1",
  speakerName: null,
  text: "hello",
  start: 0,
  end: 1,
  isFinal: true,
  ...over,
});

const say = (over = {}) => ({
  type: "segment",
  speaker: "Speaker 1",
  speakerName: null,
  text: "hello",
  start: 0,
  end: 1,
  isFinal: true,
  turnId: 0,
  ...over,
});

const apply = (list, message) => applyCaptionMessage(list, message, "s1", 0);

h.section("segment ids are scoped to the session");
{
  // The provider's turn ids restart at zero every session. Consumers cache
  // per-segment work against this id — translations, "already spoken" — and
  // those caches outlive a session, so a bare turn id meant the first line of a
  // new conversation silently inherited the previous one's translation and was
  // never re-requested.
  const first = segmentFrom(say(), "session-a", 0);
  const second = segmentFrom(say(), "session-b", 0);
  h.check("the same turn id in two sessions is two segments", first.id === second.id, false);
  const noTurnId = segmentFrom({ ...say(), turnId: undefined }, "session-a", 7);
  h.check("a provider that sends no turn id still gets an id", noTurnId.id, "turn-session-a-7");
}

h.section("an utterance is one bubble, however often it is revised");
{
  const interim = apply([], say({ isFinal: false, text: "hel" }));
  h.check("the interim appears", interim.length, 1);
  const revised = apply(interim, say({ isFinal: false, text: "hello th" }));
  h.check("a revision replaces rather than appends", revised.length, 1);
  h.check("the newest text wins", revised[0].text, "hello th");
  const finalised = apply(revised, say({ text: "hello there" }));
  h.check("the final replaces the interim", [finalised.length, finalised[0].text], [1, "hello there"]);
  const late = apply(finalised, say({ isFinal: false, text: "hel" }));
  h.check("a late interim never overwrites a final", late[0].text, "hello there");
}

h.section("a name back-fills only where nobody has been named");
{
  // `fillOnly` marks an automatic identification. One diarization label can
  // carry different people across a session, so overwriting every bubble would
  // rewrite the earlier speaker's lines with the current speaker's name.
  const list = [
    line({ id: "a", speaker: "Speaker 1", speakerName: "Mom" }),
    line({ id: "b", speaker: "Speaker 1", speakerName: null }),
    line({ id: "c", speaker: "Speaker 2", speakerName: null }),
  ];
  const filled = apply(list, {
    type: "speakerUpdate",
    speaker: "Speaker 1",
    speakerName: "Dad",
    fillOnly: true,
  });
  h.check("the unnamed line is filled", filled[1].speakerName, "Dad");
  h.check("the already-named line is left alone", filled[0].speakerName, "Mom");
  h.check("another speaker is untouched", filled[2].speakerName, null);
}

h.section("a human correction overwrites");
{
  const list = [line({ id: "a", speakerName: "Mom" }), line({ id: "b", speakerName: null })];
  const corrected = apply(list, {
    type: "speakerUpdate",
    speaker: "Speaker 1",
    speakerName: "Julie",
  });
  h.check("every bubble under that label takes the correction",
    corrected.map((s) => s.speakerName), ["Julie", "Julie"]);
}

h.section("a correction can also say 'nobody'");
{
  const list = [line({ id: "a", speakerName: "Mom" })];
  const cleared = apply(list, {
    type: "speakerUpdate",
    speaker: "Speaker 1",
    speakerName: null,
  });
  h.check("the wrong name is removed", cleared[0].speakerName, null);
}

h.section("a merge regroups what is already on screen");
{
  // Live diarization decides with no lookahead, so its first call on a voice is
  // made on almost no evidence. Rewriting the label rather than adding a name
  // is deliberate: the bubbles regroup and recolour, because grouping and
  // colour key on identity.
  const list = [
    line({ id: "a", speaker: "Speaker 1" }),
    line({ id: "b", speaker: "Speaker 2" }),
    line({ id: "c", speaker: "Speaker 3" }),
  ];
  const merged = apply(list, { type: "speakerMerge", from: "Speaker 2", to: "Speaker 1" });
  h.check("the absorbed label is rewritten",
    merged.map((s) => s.speaker), ["Speaker 1", "Speaker 1", "Speaker 3"]);
  h.check("no caption is lost", merged.length, 3);
}

h.section("the end of a session settles what was still in progress");
{
  const list = [line({ id: "a" }), line({ id: "b", isFinal: false })];
  const done = apply(list, { type: "done" });
  h.check("nothing is left interim", done.map((s) => s.isFinal), [true, true]);
  h.check("no caption is dropped", done.length, 2);
}

h.section("one-second speaker flips between the same neighbour are noise");
{
  const list = [
    line({ id: "a", speaker: "Speaker 1", start: 0, end: 3 }),
    line({ id: "b", speaker: "Speaker 2", start: 3, end: 3.5 }),
  ];
  const after = apply(list, say({ turnId: 2, speaker: "Speaker 1", start: 3.5, end: 6 }));
  h.check("the blip joins its neighbours",
    after.map((s) => s.speaker), ["Speaker 1", "Speaker 1", "Speaker 1"]);

  const long = [
    line({ id: "a", speaker: "Speaker 1", start: 0, end: 3 }),
    line({ id: "b", speaker: "Speaker 2", start: 3, end: 6 }),
  ];
  const kept = apply(long, say({ turnId: 2, speaker: "Speaker 1", start: 6, end: 9 }));
  h.check("a real turn is not swallowed",
    kept.map((s) => s.speaker), ["Speaker 1", "Speaker 2", "Speaker 1"]);
}

h.section("messages that say nothing about the transcript leave it alone");
{
  const list = [line()];
  for (const message of [
    { type: "ready", mode: "batch" },
    { type: "usage", used: 1, limit: 2 },
    { type: "paused" },
    { type: "error", message: "boom" },
  ]) {
    h.check(`${message.type} does not touch the transcript`, apply(list, message), list);
  }
}

h.done();
