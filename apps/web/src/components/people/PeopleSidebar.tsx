import { AlertCircle, Loader2, ScanFace, Users } from "lucide-react";
import type { PersonSummary } from "@/api";
import { PersonCard } from "./PersonCard";

export function PeopleSidebar({
  projectId,
  faceCropEnabled,
  people,
  peopleLoading,
  peopleError,
  selectedPersonId,
  onSelectPerson,
}: {
  projectId: number;
  faceCropEnabled: boolean;
  people: PersonSummary[];
  peopleLoading: boolean;
  peopleError: Error | null;
  selectedPersonId: number | null;
  onSelectPerson: (personId: number) => void;
}) {
  return (
    <section className="space-y-3">
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
      ) : people.length === 0 ? (
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
              onSelect={() => onSelectPerson(person.id)}
            />
          ))}
        </div>
      )}
    </section>
  );
}
