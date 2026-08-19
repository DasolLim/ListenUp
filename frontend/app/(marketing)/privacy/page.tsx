import type { Metadata } from "next";
import Link from "next/link";
import LegalPage, { LegalSection } from "@/components/marketing/LegalPage";

export const metadata: Metadata = { title: "Privacy — ListenUp" };

/*
 * NOT YET REVIEWED BY A LAWYER. The biometric section below describes real
 * obligations under Illinois BIPA, GDPR Article 9 and Quebec Law 25, and voice
 * profiles here are collected from *third parties* — the account holder's
 * mother, not the account holder. That is precisely the fact pattern BIPA suits
 * are built on, and statutory damages are per violation.
 *
 * Every factual claim below was checked against the schema in
 * backend/db/migrations/ and against the code, so this is an accurate
 * description of what the product does. It is not a substitute for review.
 */

export default function PrivacyPage() {
  return (
    <LegalPage
      title="Privacy"
      updated="2026-08-18"
      summary={
        <>
          ListenUp listens so you can read. We do not store your audio, and we do not store your
          transcripts at all — when a session ends, the conversation is gone. The one thing we do
          keep is a numeric fingerprint of a voice, and only when the person it belongs to has said
          yes.
        </>
      }
    >
      <LegalSection heading="Audio">
        <p>
          While a session is running, audio from your microphone is streamed to our speech-to-text
          provider so it can be turned into captions. We do not write that audio to disk, and we do
          not keep it after the session. Short buffers exist in memory for the few seconds needed to
          recognise speech and to tell voices apart.
        </p>
      </LegalSection>

      <LegalSection heading="Transcripts">
        <p>
          <strong className="text-ink">We do not store transcripts.</strong> Captions and
          translations exist in your browser while the session is open. Close it and they are gone —
          there is no history, no search and nothing for us to hand over.
        </p>
      </LegalSection>

      <LegalSection heading="Voice profiles — biometric data">
        <p>
          If you name a speaker, ListenUp can store a{" "}
          <strong className="text-ink">voice profile</strong> so that person is recognised next
          time. This is biometric information, and we treat it that way.
        </p>
        <ul className="ml-5 list-disc space-y-2">
          <li>
            A profile is a{" "}
            <strong className="text-ink">192-number mathematical representation</strong> of a voice,
            not a recording. It cannot be played back and it cannot be turned back into speech.
          </li>
          <li>
            A profile is only created with the{" "}
            <strong className="text-ink">explicit consent of the person whose voice it is</strong> —
            not merely the consent of the account holder. We record who consented, the exact wording
            they agreed to, and when.
          </li>
          <li>
            Profiles are visible only to the account that created them, enforced at the database
            level.
          </li>
          <li>
            The person enrolled may withdraw consent at any time, and the profile and every sample
            under it are deleted.
          </li>
        </ul>
        <p>
          We do not use voice profiles to train models, we do not sell or share them, and we do not
          use them to identify anyone outside your own sessions.
        </p>
      </LegalSection>

      <LegalSection heading="What we store">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[34rem] border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-white/50">
                <th className="py-2 pr-4 font-semibold text-ink">Data</th>
                <th className="py-2 font-semibold text-ink">Why</th>
              </tr>
            </thead>
            <tbody className="align-top">
              {[
                ["Your email address", "To sign you in."],
                ["Speaker names you type (e.g. “Mom”)", "To label captions."],
                ["Voice profiles (192 numbers each)", "To recognise a speaker next time."],
                ["Consent records", "To prove consent was given, and by whom."],
                [
                  "Custom voice identifiers",
                  "Only if you record a voice for read-aloud. We store the provider's reference and the consent, never the audio.",
                ],
                [
                  "Usage counters",
                  "Aggregated totals per billing period, to enforce your plan's allowance.",
                ],
                [
                  "Subscription identifiers",
                  "Only if you subscribe. Card details are handled by Stripe and never reach us.",
                ],
                [
                  "Words you ask us to explain",
                  "Stored without any link to your account, so the slang dictionary can learn what it is missing.",
                ],
              ].map(([what, why]) => (
                <tr key={what} className="border-b border-white/30">
                  <td className="py-2 pr-4 text-ink">{what}</td>
                  <td className="py-2">{why}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </LegalSection>

      <LegalSection heading="Who else processes your data">
        <p>
          ListenUp uses these services to work. Each receives only what it needs, and none of them
          receive your voice profiles.
        </p>
        <ul className="ml-5 list-disc space-y-1">
          <li>
            <strong className="text-ink">AssemblyAI</strong> — speech recognition (receives session
            audio)
          </li>
          <li>
            <strong className="text-ink">Google Cloud Translation</strong> — translation (receives
            text)
          </li>
          <li>
            <strong className="text-ink">OpenRouter</strong> — slang and cultural explanation
            (receives text)
          </li>
          <li>
            <strong className="text-ink">ElevenLabs</strong> — optional premium read-aloud voices
            (receives text)
          </li>
          <li>
            <strong className="text-ink">Supabase</strong> — database and sign-in
          </li>
          <li>
            <strong className="text-ink">Stripe</strong> — payments
          </li>
          <li>
            <strong className="text-ink">Sentry</strong> and{" "}
            <strong className="text-ink">PostHog</strong> — error reporting and product analytics.
            Session recording is off.
          </li>
        </ul>
      </LegalSection>

      <LegalSection heading="How long we keep things">
        <p>
          Voice profiles, consent records and speaker names are kept until you or the enrolled
          person deletes them, or until you close your account — deleting an account deletes
          everything attached to it. Usage counters are kept per billing period so we can show you
          your history. Audio and transcripts are not kept at all.
        </p>
      </LegalSection>

      <LegalSection heading="Your rights">
        <p>
          From{" "}
          <Link href="/settings" className="text-accent-strong underline underline-offset-2">
            Settings
          </Link>{" "}
          you can export everything we hold about your speaker profiles as a file, and delete any
          profile — which removes its voice data and its samples immediately. Deleting your account
          removes the rest.
        </p>
        <p>
          Depending on where you live you may also have the right to object to processing, to
          correct your data, or to complain to a regulator. Write to us and we will help.
        </p>
      </LegalSection>

      <LegalSection heading="Children">
        <p>
          ListenUp is not intended for children under 13, and we do not knowingly create accounts
          for them. If a voice profile has been created for a child without the consent of a parent
          or guardian, tell us and we will delete it.
        </p>
      </LegalSection>

      <LegalSection heading="Changes and contact">
        <p>
          If we change how any of this works we will update this page and the date at the top.
          Questions, requests, or a consent you want withdrawn:{" "}
          <a
            href="mailto:privacy@listenup.app"
            className="text-accent-strong underline underline-offset-2"
          >
            privacy@listenup.app
          </a>
          .
        </p>
      </LegalSection>
    </LegalPage>
  );
}
