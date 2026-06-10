import { useState } from "react";
import { ProjectSwitcherSheet } from "@/components/ProjectSwitcherSheet";
import { useAuth } from "@/contexts/AuthContext";
import { useProjectContext } from "@/contexts/ProjectContext";

export function MobileAccountPage() {
  const auth = useAuth();
  const { projects, currentProject, currentProjectId, setCurrentProjectId } = useProjectContext();
  const [sheetOpen, setSheetOpen] = useState(false);

  return (
    <main className="mobile-page px-4 pb-20 pt-4">
      <section className="mx-auto max-w-3xl space-y-3 rounded-2xl border border-mobileHairline bg-mobileCard p-4">
        <h1 className="text-lg font-bold text-mobileInk">我的账户</h1>

        <div className="rounded-xl bg-mobileBg p-3 text-sm">
          <p className="text-mobileInk">{auth.session?.display_name ?? auth.session?.username}</p>
          <p className="mt-1 text-mobileMute">角色: {auth.session?.role ?? "-"}</p>
        </div>

        <button
          type="button"
          className="w-full rounded-xl border border-mobileHairline px-3 py-3 text-left text-sm"
          onClick={() => setSheetOpen(true)}
        >
          当前项目: <span className="font-semibold text-mobileInk">{currentProject?.name ?? "未选择"}</span>
        </button>

        <button
          type="button"
          className="h-11 w-full rounded-xl bg-mobileAccent text-sm font-semibold text-white active:bg-mobileAccentPressed"
          onClick={() => auth.logout()}
        >
          退出登录
        </button>
      </section>

      <ProjectSwitcherSheet
        open={sheetOpen}
        projects={projects}
        currentProjectId={currentProjectId}
        onClose={() => setSheetOpen(false)}
        onSelect={setCurrentProjectId}
      />
    </main>
  );
}
