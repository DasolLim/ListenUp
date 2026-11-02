import Navbar from "@/components/shell/Navbar";
import StartCaptionsButton from "@/components/captions/StartCaptionsButton";

// The app uses the same top navbar as the website: one responsive product,
// not a separate "app". On desktop it reads as a web nav; on mobile the nav
// collapses to the drawer (with Tools) for app-style navigation.
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Navbar />
      {/* Safe-area padding so the transcript is not tucked under a notch or a
          home indicator. `pb-24` already reserves room for the A11y bar; this
          adds whatever the device itself claims on top of that. */}
      <main
        id="main"
        className="mx-auto w-full max-w-6xl flex-1 px-[max(1rem,env(safe-area-inset-left))] py-8 pb-[calc(6rem+env(safe-area-inset-bottom))] sm:px-6"
      >
        {children}
      </main>
      <StartCaptionsButton />
    </>
  );
}
