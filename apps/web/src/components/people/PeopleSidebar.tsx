import { AlertCircle, CheckSquare2, Loader2, ScanFace, Users, X } from "lucide-react";
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
  onSelectAllPeople,
  onClearSelectedPeople,
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
  onSelectAllPeople: () => void;
  onClearSelectedPeople: () => void;
  onArchivePerson: (personId: number) => void;
  onDeletePerson: (personId: number) => void;
  onUnarchivePerson: (personId: number) => void;
}) {
  const visibleSelectedCount = people.filter((person) => selectedPersonIds.includes(person.id)).length;

  return (
    <section className="min-h-0 space-y-2 lg:h-full lg:overflow-y-auto lg:overscroll-contain lg:pr-1" aria-labelledby="people-list-title">
      <div className="sticky top-0 z-10 rounded-lg border border-hairline bg-canvas/95 p-3 shadow-sm backdrop-blur-sm">
        <div className="flex min-h-9 items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Users className="h-4 w-4 text-primary" aria-hidden="true" />
            <h2 id="people-list-title" className="text-body-sm font-semibold text-ink">人物列表</h2>
          </div>
          <div className="flex items-center gap-1">
            <span className="rounded-full bg-secondary-bg px-2.5 py-1 text-caption-sm font-medium tabular-nums text-secondary">{people.length}</span>
            {people.length > 0 && visibleSelectedCount < people.length && (
              <button
                type="button"
                onClick={onSelectAllPeople}
                aria-label="全选当前结果"
                className="inline-flex min-h-11 items-center gap-1 rounded-md px-2 text-caption-sm font-medium text-secondary hover:bg-surface-soft hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-outer"
              >
                <CheckSquare2 className="h-4 w-4" aria-hidden="true" />
                全选
              </button>
            )}
            {selectedPersonIds.length > 0 && (
              <button
                type="button"
                onClick={onClearSelectedPeople}
                aria-label="清空人物选择"
                className="inline-flex min-h-11 items-center gap-1 rounded-md px-2 text-caption-sm font-medium text-secondary hover:bg-surface-soft hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-outer"
              >
                <X className="h-4 w-4" aria-hidden="true" />
                清空
              </button>
            )}
          </div>
        </div>
        {selectedPersonIds.length > 0 && (
          <p className="mt-1 text-caption-sm text-primary" role="status" aria-atomic="true">
            已选择 {selectedPersonIds.length} 人，可在上方批量管理
          </p>
        )}
      </div>

      {peopleLoading ? (
        <div className="bg-canvas rounded-xl border border-hairline p-6 flex items-center gap-3 text-mute">
          <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
          正在加载人物列表...
        </div>
      ) : peopleError ? (
        <div className="bg-canvas rounded-xl border border-hairline p-6 flex items-center gap-3 text-danger">
          <AlertCircle className="h-4 w-4" aria-hidden="true" />
          {peopleError.message}
        </div>
      ) : people.length === 0 && archivedPeople.length === 0 ? (
        <div className="bg-canvas rounded-xl border border-hairline p-8 text-center text-mute">
          <ScanFace className="mx-auto mb-3 h-8 w-8" aria-hidden="true" />
          还没有人物分组。请先在 AI / Face 配置中启用人脸识别，然后执行项目级人脸扫描。
        </div>
      ) : (
        <div className="space-y-2">
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
            <details className="group rounded-lg border border-hairline bg-surface-soft">
              <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between px-3 text-body-sm font-medium text-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-outer [&::-webkit-details-marker]:hidden">
                <span>archive 文件夹（不再管理）</span>
                <span className="rounded-full bg-canvas px-2 py-0.5 text-caption-sm tabular-nums">{archivedPeople.length}</span>
              </summary>
              <div className="space-y-1 border-t border-hairline px-3 py-2 text-caption-sm text-mute">
                {archivedPeople.map((person) => (
                  <div
                    key={person.id}
                    className="flex items-center justify-between gap-2 rounded-md border border-hairline bg-canvas px-2.5 py-2"
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
                      className="min-h-9 rounded-md border border-hairline px-2 text-caption-sm text-ink hover:bg-surface-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-outer"
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
