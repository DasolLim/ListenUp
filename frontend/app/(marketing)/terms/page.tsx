import type { Metadata } from "next";
import Link from "next/link";
import LegalPage, { LegalSection } from "@/components/marketing/LegalPage";

export const metadata: Metadata = { title: "Terms — ListenUp" };

/*
 * NOT YET REVIEWED BY A LAWYER. Two clauses below carry real weight and should
 * not be softened without advice: the requirement that you have permission
 * before enrolling somebody else's voice (which is what keeps BIPA consent
 * meaningful), and the emergency clause — this is an accessibility tool, and a
 * deaf user relying on it in a safety-critical moment is a foreseeable use.
 */

export default function TermsPage() {
  return (
    <LegalPage
      title="Terms of use"
      updated="2026-08-18"
      summary={
        <>
          ListenUp turns speech into captions and translations. It is an assistive tool, not a
          certified interpreter — it will sometimes get words, names and tone wrong. Two things we
          ask of you: get permission before you enrol someone else&apos;s voice, and do not rely on
          ListenUp where being misunderstood would be dangerous.
        </>
      }
    >
      <LegalSection heading="What ListenUp is">
        <p>
          A live captioning and translation tool. It listens to a conversation through one
          microphone, writes what it hears, tries to say who said it, and can translate and explain
          what was meant.
        </p>
      </LegalSection>

      <LegalSection heading="Accuracy — please read this one">
        <p>
          Speech recognition, speaker identification and machine translation all make mistakes.
          Background noise, several people talking at once, accents, and unfamiliar names all make
          them worse. ListenUp may attribute a sentence to the wrong person, or translate a phrase
          in a way that changes its meaning.
        </p>
        <p>
          <strong className="text-ink">
            Do not rely on ListenUp for medical, legal, financial or emergency communication
          </strong>
          , or anywhere a misunderstanding could cause harm. In those settings use a qualified human
          interpreter or captioner. We provide the tool as-is and cannot be responsible for
          decisions made on the strength of an imperfect caption.
        </p>
      </LegalSection>

      <LegalSection heading="Other people's voices">
        <p>
          You may only create a voice profile for someone who has agreed to it. The app asks you to
          confirm this, and records that confirmation — please do not treat it as a checkbox. In
          several places, including Illinois, Texas, the EU and Quebec, a person&apos;s voiceprint
          is protected biometric information and collecting it without their consent is unlawful.
        </p>
        <p>
          Anyone whose voice you have enrolled can ask for it to be deleted, through you or by
          writing to us directly, and we will delete it.
        </p>
      </LegalSection>

      <LegalSection heading="Recording other people">
        <p>
          Laws about recording and transcribing conversations differ by country and by state, and
          some require every participant to consent. Making sure you may caption a given
          conversation is your responsibility, not ours.
        </p>
      </LegalSection>

      <LegalSection heading="Your account">
        <p>
          You need to be old enough to enter a contract where you live, and at least 13. Keep your
          sign-in details to yourself; you are responsible for what happens under your account. Do
          not use ListenUp to break the law, to harass anyone, or to attack the service.
        </p>
      </LegalSection>

      <LegalSection heading="Plans and payment">
        <p>
          The free tier needs no payment details. Paid plans are billed monthly in advance through
          Stripe and renew until you cancel; cancelling stops the next renewal and you keep your
          plan until the period ends. Allowances are stated on your{" "}
          <Link href="/settings" className="text-accent-strong underline underline-offset-2">
            Settings
          </Link>{" "}
          page and reset each billing period.
        </p>
      </LegalSection>

      <LegalSection heading="Ending it">
        <p>
          You can stop using ListenUp and delete your account at any time. We may suspend an account
          that is breaking these terms or putting the service at risk, and will tell you why where
          we can.
        </p>
      </LegalSection>

      <LegalSection heading="Changes and contact">
        <p>
          If these terms change we will update this page and the date at the top. If a change
          materially affects you we will say so before it takes effect. Questions:{" "}
          <a
            href="mailto:hello@listenup.app"
            className="text-accent-strong underline underline-offset-2"
          >
            hello@listenup.app
          </a>
          . How we handle data is in the{" "}
          <Link href="/privacy" className="text-accent-strong underline underline-offset-2">
            privacy policy
          </Link>
          .
        </p>
      </LegalSection>
    </LegalPage>
  );
}
