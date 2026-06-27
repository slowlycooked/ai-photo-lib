import { AlertCircle, Loader2, ScanFace, Users } from "lucide-react";
import type { PersonSummary } from "@/api";
import { PersonCard } from "./PersonCard";

export function PeopleSidebar({
  projectId,
  faceCropEnabled,
  people,
  archivedPeople,
  manualArchivedPersonIds,
  selectedPersonIds,
  peopleLoading,
  peopleError,
  selectedPersonId,
  actionBusy,
  onSelectPerson,
  onToggleSelectPerson,
  onArchivePerson,
  onDeletePerson,
  onUnarchivePerson,
}: {
  projectId: number;
  faceCropEnabled: boolean;
  people: PersonSummary[];
  archivedPeople: PersonSummary[];
  manualArchivedPersonIds: Set<number>;
  selectedPersonIds: number[];
  peopleLoading: boolean;
  peopleError: Error | null;
  selectedPersonId: number | null;
  actionBusy: boolean;
  onSelectPerson: (personId: number) => void;
  onToggleSelectPerson: (personId: number, checked: boolean) => void;
  onArchivePerson: (personId: number) => void;
  onDeletePerson: (personId: number) => void;
  onUnarchivePerson: (personId: number) => void;
}) {
  return (
    <section className="min-h-0 space-y-3 lg:h-full lg:overflow-y-auto lg:overscroll-contain lg:pr-1">
      <div className="bg-canvas rounded-xl border border-hairline p-4">
        <div className="flex items-center gap-2 mb-2">
          <Users className="w-4 h-4 text-primary" />
          <h2 className="text-body-sm font-semibold text-ink">人物列表</h2>
        </div>
        <p className="text-caption-sm text-mute">
          先展示当前项目里已有的人物分组。后续会在这里接合并、拆分、待确认筛选。
        </p>
      </div>

      {peopleLoading ? (
        <div className="bg-canvas rounded-xl border border-hairline p-6 flex items-center gap-3 text-mute">
          <Loader2 className="w-4 h-4 animate-spin" />
          正在加载人物列表...
        </div>
      ) : peopleError ? (
        <div className="bg-canvas rounded-xl border border-hairline p-6 flex items-center gap-3 text-danger">
          <AlertCircle className="w-4 h-4" />
          {peopleError.message}
        </div>
      ) : people.length === 0 && archivedPeople.length === 0 ? (
        <div className="bg-canvas rounded-xl border border-hairline p-8 text-center text-mute">
          <ScanFace className="w-8 h-8 mx-auto mb-3" />
          还没有人物分组。请先在 AI / Face 配置中启用人脸识别，然后执行项目级人脸扫描。
        </div>
      ) : (
        <div className="space-y-3">
          {people.map((person) => (
            <PersonCard
              key={person.id}
              projectId={projectId}
              faceCropEnabled={faceCropEnabled}
              person={person}
              selected={selectedPersonId === person.id}
              checked={selectedPersonIds.includes(person.id)}
              showCheckbox
              actionBusy={actionBusy}
              onSelect={() => onSelectPerson(person.id)}
              onToggleChecked={(checked) => onToggleSelectPerson(person.id, checked)}
              onArchive={() => onArchivePerson(person.id)}
              onDelete={() => {
                if (!window.confirm("删除人物前，请确保没有 active assignment。确认继续？")) return;
                onDeletePerson(person.id);
              }}
            />
          ))}

          {archivedPeople.length > 0 && (
            <details className="rounded-xl border border-hairline bg-surface-soft" open={false}>
              <summary className="cursor-pointer list-none px-4 py-3 text-body-sm font-medium text-mute flex items-center justify-between">
                <span>archive 文件夹（不再管理）</span>
                <span className="text-caption-sm">{archivedPeople.length}</span>
              </summary>
              <div className="px-4 pb-3 space-y-1 text-caption-sm text-mute">
                {archivedPeople.map((person) => (
                  <div
                    key={person.id}
                    className="rounded-md border border-hairline bg-canvas px-2.5 py-2 flex items-center justify-between gap-2"
                  >
                    <button
                      type="button"
                      onClick={() => onSelectPerson(person.id)}
                      className={[
                        "text-left text-caption-sm hover:text-ink",
                        selectedPersonId === person.id ? "text-ink font-medium" : "text-mute",
                      ].join(" ")}
                    >
                      #{person.id} · {person.display_name}
                    </button>
                    <button
                      type="button"
                      onClick={() => onUnarchivePerson(person.id)}
                      className="px-2 py-0.5 rounded border border-hairline text-[11px] text-ink hover:bg-surface-card"
                    >
                      恢复管理
                    </button>
                  </div>
                ))}
              </div>
            </details>
          )}
        </div>
      )}
    </section>
  );
}
