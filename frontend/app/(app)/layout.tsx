import Sidebar from "@/components/shell/Sidebar";
import Topbar from "@/components/shell/Topbar";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto flex w-full max-w-[1400px] flex-1 gap-6 p-4 sm:p-6">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col gap-6">
        <Topbar />
        <main id="main" className="flex-1">
          {children}
        </main>
      </div>
    </div>
  );
}
