import Navbar from "@/components/Navbar";

export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Navbar />
      <main id="main" className="mx-auto w-full max-w-5xl flex-1 px-4 py-8 pb-20">
        {children}
      </main>
    </>
  );
}
