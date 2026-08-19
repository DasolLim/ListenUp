/**
 * Turn grouping and speaker-identity colour rules.
 *
 * Run: `node scripts/verify-turngroups.mjs` from /frontend.
 *
 * There is no test runner in this app, and these rules are the part of the
 * transcript most worth pinning: they decide whether one person's lines stay
 * one turn when the diarization label churns, and whether two people sharing a
 * label are kept apart. Both are answers a reader cannot check by ear.
 *
 * Loaded through the shared harness, which transpiles the module in-process
 * with the project's own compiler rather than bundling it.
 */
import { harness, loadTs } from "./lib/harness.mjs";

const { turnGroups, identityColor, linePosition, stamp, gapLabel } = await loadTs(
  new URL("../lib/turnGroups.ts", import.meta.url)
);

const h = harness();
const check = h.check;

let n = 0;
const seg = (speaker, speakerName, start, end, isFinal = true) => ({
  id: `s${n++}`,
  speaker,
  speakerName,
  text: "x",
  start,
  end,
  isFinal,
});

console.log("\nturn grouping");

// 1. consecutive lines from one speaker collapse into one group
{
  const g = turnGroups([seg("Speaker 1", null, 0, 1), seg("Speaker 1", null, 1.1, 2)]);
  check("one speaker, two lines -> 1 group of 2", [g.length, g[0].lines.length], [1, 2]);
}

// 2. a different speaker starts a new group
{
  const g = turnGroups([seg("Speaker 1", null, 0, 1), seg("Speaker 2", null, 1.1, 2)]);
  check("speaker change -> 2 groups", g.length, 2);
}

// 3. label churn must NOT split one named person
{
  const g = turnGroups([seg("Speaker 1", "Mom", 0, 1), seg("Speaker 2", "Mom", 1.1, 2)]);
  check("label churn under one name -> 1 group", [g.length, g[0].lines.length], [1, 2]);
}

// 4. one label covering two named people MUST split
{
  const g = turnGroups([seg("Speaker 1", "Mom", 0, 1), seg("Speaker 1", "Dad", 1.1, 2)]);
  check("one label, two people -> 2 groups", g.length, 2);
}

// 5. a long pause breaks the run and is labelled
{
  const g = turnGroups([seg("Speaker 1", null, 0, 1), seg("Speaker 1", null, 61, 62)]);
  check("60s gap -> 2 groups", g.length, 2);
  check("gap labelled", [g[1].gapBefore, g[1].gapLabel], [true, "1 min later"]);
}

// 6. a short pause does not
{
  const g = turnGroups([seg("Speaker 1", null, 0, 1), seg("Speaker 1", null, 19, 20)]);
  check("19s gap -> still 1 group", g.length, 1);
}

// 7. the first group never carries a divider
{
  const g = turnGroups([seg("Speaker 1", null, 0, 1)]);
  check("first group has no divider", g[0].gapBefore, false);
}

// 8. nothing is dropped
{
  const segments = [
    seg("Speaker 1", null, 0, 1),
    seg("Speaker 2", null, 1.1, 2),
    seg("Speaker 1", null, 2.1, 3),
    seg("Speaker 1", null, 3.1, 4),
    seg("Speaker 3", null, 90, 91),
  ];
  const g = turnGroups(segments);
  const lines = g.flatMap((group) => group.lines.map((l) => l.id));
  check("every segment appears exactly once", lines, segments.map((s) => s.id));
}

// 9. an interim line groups with its speaker like any other
{
  const g = turnGroups([seg("Speaker 1", null, 0, 1), seg("Speaker 1", null, 1.1, 2, false)]);
  check("interim joins the run", [g.length, g[0].lines.length], [1, 2]);
}

console.log("\nidentity colour");

// 10. stable per identity, assigned in first-appearance order
{
  const segments = [seg("Speaker 1", null, 0, 1), seg("Speaker 2", null, 1, 2)];
  const c = identityColor(segments);
  check("first speaker -> 0, second -> 1", [c("Speaker 1"), c("Speaker 2")], [0, 1]);
}

// 11. one person keeps one colour through label churn
{
  const segments = [
    seg("Speaker 1", "Mom", 0, 1),
    seg("Speaker 2", "Dad", 1, 2),
    seg("Speaker 3", "Mom", 2, 3),
  ];
  const c = identityColor(segments);
  check("Mom keeps her colour across labels", [c("Mom"), c("Dad")], [0, 1]);
}

// 12. past four speakers the tints wrap rather than going undefined
{
  const segments = ["a", "b", "c", "d", "e"].map((s, i) => seg(s, null, i, i + 1));
  const c = identityColor(segments);
  check("fifth speaker wraps to tint 0", [c("d"), c("e")], [3, 0]);
}

// 13. an unknown key is never undefined (it indexes the rail array)
{
  check("unknown identity -> 0", identityColor([])("nobody"), 0);
}

console.log("\nline position");
check("single line", linePosition(0, 1), "only");
check("first of three", linePosition(0, 3), "first");
check("middle of three", linePosition(1, 3), "middle");
check("last of three", linePosition(2, 3), "last");
check("first of two", linePosition(0, 2), "first");
check("last of two", linePosition(1, 2), "last");

console.log("\ntimestamps");
check("0s", stamp(0), "0:00");
check("9s", stamp(9), "0:09");
check("65s", stamp(65), "1:05");
check("negative clamps", stamp(-5), "0:00");
check("gap in seconds", gapLabel(45), "45 sec later");
check("gap in minutes", gapLabel(120), "2 min later");
check("gap in hours", gapLabel(7200), "2 hr later");

h.done();
