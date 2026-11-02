import type { Metadata } from "next";
import { Inter, Poppins } from "next/font/google";
import A11yBar from "@/components/shell/A11yBar";
import "./globals.css";

const poppins = Poppins({
  variable: "--font-poppins",
  weight: ["600", "700", "800"],
  subsets: ["latin"],
});

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "ListenUp — captions that know who's talking",
  description:
    "Live speaker-named captions and cultural translation for deaf and hard-of-hearing users, travelers, and immigrants.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${poppins.variable} ${inter.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2 focus:outline-2 dark:focus:bg-black"
        >
          Skip to main content
        </a>
        {children}
        <A11yBar />
      </body>
    </html>
  );
}
