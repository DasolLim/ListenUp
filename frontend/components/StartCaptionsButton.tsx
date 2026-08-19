"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { MicIcon } from "@/components/shell/icons";

/**
 * One tap to captions, from anywhere in the app.
 *
 * The product's real moment is someone standing in a pharmacy while a stranger
 * talks at them. Getting there used to cost four taps — dashboard, family,
 * tier, start — and the moment does not wait. This is the phone-camera
 * argument: the control lives where you already are, because navigating to it
 * is the part that fails.
 *
 * `?start=1` tells the captions page to open the microphone on arrival, so the
 * tap that got you here is also the tap that starts listening.
 *
 * Hidden on the captions page itself, where the real Start control lives and a
 * second one would just compete with it.
 */
export default function StartCaptionsButton() {
  const pathname = usePathname();
  if (pathname?.startsWith("/captions")) return null;

  return (
    <Link
      href="/captions?start=1"
      // Bottom-right on phones where a thumb lives, inline-safe on desktop.
      // pb-24 on the app <main> already reserves room so this never covers
      // content at the end of a page.
      className="btn-primary fixed right-4 bottom-4 z-40 inline-flex min-h-14 items-center gap-2 rounded-full px-5 text-[15px] font-semibold shadow-glass sm:right-6 sm:bottom-6"
    >
      <MicIcon />
      Start captions
    </Link>
  );
}
