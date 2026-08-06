import Navbar from "@/components/Navbar";
import StartCaptionsButton from "@/components/StartCaptionsButton";

// The app uses the same top navbar as the website: one responsive product,
// not a separate "app". On desktop it reads as a web nav; on mobile the nav
// collapses to the drawer (with Tools) for app-style navigation.
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Navbar />
      <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 pb-24 sm:px-6">
        {children}
      </main>
      <StartCaptionsButton />
    </>
  );
}
