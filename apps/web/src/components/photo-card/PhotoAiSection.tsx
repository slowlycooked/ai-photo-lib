import { Brain, Loader2 } from "lucide-react";
import type { AIAnalysis } from "@/api/types";

interface PhotoAiSectionProps {
  aiData?: AIAnalysis;
  isLoading: boolean;
}

export function PhotoAiSection({ aiData, isLoading }: PhotoAiSectionProps) {
  return (
    <div className="pt-2 border-t border-hairline">
      <div className="flex items-center gap-2 mb-3">
        <Brain className="w-4 h-4 text-primary" />
        <span className="text-body-sm font-semibold text-ink">AI 分析结果</span>
        {isLoading && <Loader2 className="w-3.5 h-3.5 animate-spin text-mute" />}
      </div>

      {isLoading ? (
        <p className="text-caption-sm text-mute">加载中…</p>
      ) : aiData ? (
        <div className="space-y-3">
          {aiData.caption && (
            <div>
              <p className="text-caption-sm text-mute mb-1">描述</p>
              <p className="text-body-sm text-ink">{aiData.caption}</p>
            </div>
          )}

          {[
            { label: "场景", tags: aiData.scene_tags },
            { label: "物体", tags: aiData.object_tags },
            { label: "活动", tags: aiData.activity_tags },
            { label: "画质", tags: aiData.quality_tags },
          ].map(
            ({ label, tags }) =>
              tags && tags.length > 0 && (
                <div key={label}>
                  <p className="text-caption-sm text-mute mb-1">{label}</p>
                  <div className="flex flex-wrap gap-1">
                    {tags.map((tag) => (
                      <span
                        key={tag}
                        className="px-2 py-0.5 bg-secondary-bg rounded-full text-caption-sm text-ink"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              ),
          )}

          {aiData.ocr_text && aiData.ocr_text.trim() && (
            <div>
              <p className="text-caption-sm text-mute mb-1">OCR 文字</p>
              <p className="text-caption-sm text-ink whitespace-pre-wrap bg-secondary-bg rounded p-2">
                {aiData.ocr_text}
              </p>
            </div>
          )}

          <div className="flex flex-wrap gap-x-4 gap-y-1 text-caption-sm text-mute">
            {aiData.people_count !== null && aiData.people_count !== undefined && (
              <span>人物：{aiData.people_count} 人</span>
            )}
            {aiData.confidence !== null && aiData.confidence !== undefined && (
              <span>置信度：{(aiData.confidence * 100).toFixed(0)}%</span>
            )}
            {aiData.model_name && <span>模型：{aiData.model_name}</span>}
          </div>
        </div>
      ) : (
        <p className="text-caption-sm text-mute">尚未分析 — 请点击「开始分析」按钮。</p>
      )}
    </div>
  );
}
