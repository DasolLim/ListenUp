"use client";

import { useCallback, useState } from "react";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

export type ProfileOption = { id: string; display_name: string };

/**
 * Tap a speaker's label to say who they actually are.
 *
 * This is the moment the product's naming is worth anything: the system has
 * guessed "Speaker 2" and the person reading is the only one who knows it's
 * Mom. The correction renames the label for the rest of the session *and* sends
 * that turn's audio back as a labelled example, so the profile recognises her
 * faster next time.
 *
 * Extracted from the captions component when the translate tool's voice pane
 * needed it too. Both surfaces show the same transcript of the same
 * conversation, so a name correctable in one and frozen in the other would be a
 * difference with no reason a user could infer.
 *
 * Profiles are fetched lazily, on first open: most sessions never correct
 * anything, and this is a request on behalf of a signed-in user that would
 * otherwise fire on every page load.
 */
export function useSpeakerCorrection(correct: (label: string, profileId: string | null) => void) {
  const [options, setOptions] = useState<ProfileOption[]>([]);
  const [correcting, setCorrecting] = useState<string | null>(null);

  const open = useCallback(
    async (speakerLabel: string) => {
      if (options.length === 0) {
        const { authHeader } = await import("@/lib/auth/token");
        const headers = await authHeader();
        if (headers.Authorization) {
          const response = await fetch(`${BACKEND}/profiles`, { headers });
          if (response.ok) setOptions(await response.json());
        }
      }
      setCorrecting(speakerLabel);
    },
    [options.length]
  );

  const apply = useCallback(
    (profileId: string | null) => {
      // `null` is a real answer, not a cancel: "I don't know who that is"
      // clears a wrong name, and never forcing one is the rule (INTRODUCTION §7).
      if (correcting) correct(correcting, profileId);
      setCorrecting(null);
    },
    [correcting, correct]
  );

  const cancel = useCallback(() => setCorrecting(null), []);

  return { options, correcting, open, apply, cancel };
}
