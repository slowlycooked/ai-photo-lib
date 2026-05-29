import { AlertCircle, Check, Clipboard, FlaskConical, Loader2, RotateCcw, Save, Trash2 } from "lucide-react";
import {
  useProjectPromptSettings,
  type ModelFormSnapshot,
} from "@/hooks/useProjectPromptSettings";
import { CapabilityMaturityBadge } from "@/components/common/CapabilityMaturityBadge";
import { ConfigTestResult } from "@/components/settings/ConfigTestResult";
import { CAPABILITY_MATURITY } from "@/lib/capabilityMaturity";
import { Label, SettingsCard } from "./SettingsPrimitives";

function copyText(text: string, onDone: (msg: string) => void) {
  navigator.clipboard
    .writeText(text)
    .then(() => onDone("已复制到剪贴板"))
    .catch(() => onDone("复制失败，请检查浏览器权限"));
}

export function PromptSettingsSection({
  projectId,
  modelForm,
  onMessage,
}: {
  projectId: number;
  modelForm: ModelFormSnapshot;
  onMessage: (message: string) => void;
}) {
  const {
    templatesLoading,
    templates,
    selectedTemplateId,
    setSelectedTemplateId,
    templateName,
    setTemplateName,
    advancedMode,
    setAdvancedMode,
    basicFocus,
    setBasicFocus,
    basicExtra,
    setBasicExtra,
    advancedPrompt,
    setAdvancedPrompt,
    generatedPrompt,
    effectivePrompt,
    currentTemplate,
    savePrompt,
    savePromptPending,
    activateTemplate,
    activateTemplatePending,
    resetPrompt,
    resetPromptPending,
    deletePrompt,
    deletePromptPending,
    testPhotoId,
    setTestPhotoId,
    testPhotos,
    photosIsError,
    photosError,
    testPrompt,
    testPromptPending,
    testResult,
    testHistory,
    clearTestHistory,
    loadHistoryResult,
    latestFailed,
  } = useProjectPromptSettings({ projectId, modelForm, onMessage });

  return (
    <>
      <SettingsCard title="2. Prompt 模板与版本管理">
        {templatesLoading ? (
          <div className="flex items-center gap-2 text-mute"><Loader2 className="w-4 h-4 animate-spin" />加载中…</div>
        ) : (
          <>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
              <div className="space-y-2 lg:col-span-1">
                <Label>当前模板版本</Label>
                <div className="max-h-72 overflow-y-auto border border-hairline rounded-md divide-y divide-hairline">
                  {templates.map((template) => (
                    <button
                      key={template.id}
                      onClick={() => setSelectedTemplateId(template.id)}
                      className={[
                        "w-full px-3 py-2 text-left text-body-sm",
                        selectedTemplateId === template.id ? "bg-secondary-bg" : "hover:bg-surface-card",
                      ].join(" ")}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-medium text-ink truncate">v{template.version} · {template.name}</span>
                        {template.is_active && <span className="text-caption-sm text-primary">启用中</span>}
                      </div>
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-3 lg:col-span-2">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div>
                    <Label>模板名称</Label>
                    <input
                      value={templateName}
                      onChange={(e) => setTemplateName(e.target.value)}
                      className="w-full px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md"
                    />
                  </div>
                  <div>
                    <Label>编辑模式</Label>
                    <div className="flex gap-2">
                      <button
                        onClick={() => setAdvancedMode(false)}
                        className={[
                          "px-3 py-1.5 rounded-md text-btn-sm border",
                          !advancedMode ? "bg-secondary-bg border-primary text-primary" : "border-hairline",
                        ].join(" ")}
                      >
                        基础模式
                      </button>
                      <button
                        onClick={() => setAdvancedMode(true)}
                        className={[
                          "px-3 py-1.5 rounded-md text-btn-sm border",
                          advancedMode ? "bg-secondary-bg border-primary text-primary" : "border-hairline",
                        ].join(" ")}
                      >
                        高级模式
                      </button>
                    </div>
                  </div>
                </div>

                {!advancedMode ? (
                  <div className="space-y-3">
                    <div>
                      <Label>分析重点（每行一项）</Label>
                      <textarea
                        value={basicFocus}
                        onChange={(e) => setBasicFocus(e.target.value)}
                        rows={6}
                        className="w-full px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md"
                      />
                    </div>
                    <div>
                      <Label>额外要求</Label>
                      <textarea
                        value={basicExtra}
                        onChange={(e) => setBasicExtra(e.target.value)}
                        rows={3}
                        placeholder="例如：优先识别旅行、户外、家庭聚会、城市地标。"
                        className="w-full px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md"
                      />
                    </div>
                    <div>
                      <Label>生成后的 Prompt 预览</Label>
                      <pre className="max-h-52 overflow-auto text-caption-sm bg-surface-soft border border-hairline rounded-md px-3 py-2 whitespace-pre-wrap break-all">
                        {generatedPrompt}
                      </pre>
                    </div>
                  </div>
                ) : (
                  <div>
                    <Label>完整 Prompt（高级模式）</Label>
                    <div className="mb-2 text-caption-sm text-amber-600 flex items-center gap-1">
                      <AlertCircle className="w-3.5 h-3.5" />
                      高级模式可能导致模型输出无法解析，仅建议用于调试。
                    </div>
                    <textarea
                      value={advancedPrompt}
                      onChange={(e) => setAdvancedPrompt(e.target.value)}
                      rows={14}
                      className="w-full px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md font-mono"
                    />
                  </div>
                )}

                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={savePrompt}
                    disabled={savePromptPending}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-primary text-white text-btn-sm font-bold disabled:bg-stone"
                  >
                    {savePromptPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                    保存为新版本
                  </button>
                  <button
                    onClick={() => currentTemplate && activateTemplate(currentTemplate.id)}
                    disabled={!currentTemplate || activateTemplatePending}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-hairline text-btn-sm hover:bg-surface-card disabled:opacity-50"
                  >
                    <Check className="w-3.5 h-3.5" />
                    设为启用
                  </button>
                  <button
                    onClick={resetPrompt}
                    disabled={resetPromptPending}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-hairline text-btn-sm hover:bg-surface-card disabled:opacity-50"
                  >
                    <RotateCcw className="w-3.5 h-3.5" />
                    恢复默认
                  </button>
                  <button
                    onClick={() => {
                      if (!currentTemplate) return;
                      if (!window.confirm(`确认删除模板「v${currentTemplate.version} · ${currentTemplate.name}」？`)) {
                        return;
                      }
                      deletePrompt(currentTemplate.id);
                    }}
                    disabled={!currentTemplate || currentTemplate.is_active || deletePromptPending}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-danger text-danger text-btn-sm hover:bg-danger/5 disabled:opacity-50"
                    title={currentTemplate?.is_active ? "启用中的模板不能删除，请先切换到其他模板" : "删除当前模板"}
                  >
                    {deletePromptPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                    删除模板
                  </button>
                  <button
                    onClick={() => copyText(effectivePrompt, onMessage)}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-hairline text-btn-sm hover:bg-surface-card"
                  >
                    <Clipboard className="w-3.5 h-3.5" />
                    复制当前 Prompt
                  </button>
                </div>
              </div>
            </div>
          </>
        )}
      </SettingsCard>

      <SettingsCard
        title={
          <span className="flex flex-wrap items-center gap-2">
            <span>3. Prompt 测试区</span>
            <CapabilityMaturityBadge item={CAPABILITY_MATURITY.prompt_testing} />
          </span>
        }
      >
        <p className="text-caption-sm text-mute">{CAPABILITY_MATURITY.prompt_testing.hint}</p>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          <div>
            <Label>选择测试图片</Label>
            <select
              value={testPhotoId ?? ""}
              onChange={(e) => setTestPhotoId(e.target.value ? Number(e.target.value) : null)}
              className="w-full px-3 py-2 text-body-sm bg-surface-card border border-hairline rounded-md"
            >
              <option value="">请选择图片</option>
              {testPhotos.map((photo) => (
                <option key={photo.id} value={photo.id}>
                  #{photo.id} · {photo.file_name}
                </option>
              ))}
            </select>
            {photosIsError ? (
              <p className="text-caption-sm text-danger mt-1">
                测试图片加载失败：{photosError instanceof Error ? photosError.message : "未知错误"}
              </p>
            ) : testPhotos.length === 0 ? (
              <p className="text-caption-sm text-mute mt-1">
                当前项目暂无可测试图片，请先在任务中心扫描该项目照片库。
              </p>
            ) : null}
          </div>

          <div className="flex items-end gap-2">
            <button
              onClick={testPrompt}
              disabled={testPromptPending || !testPhotoId}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-primary text-white text-btn-sm font-bold disabled:bg-stone"
            >
              {testPromptPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FlaskConical className="w-3.5 h-3.5" />}
              测试当前 Prompt
            </button>
          </div>
        </div>

        {testResult ? (
          <ConfigTestResult
            title="Vision Prompt 测试结果"
            success={testResult.success}
            latencyMs={testResult.duration_ms}
            errorMessage={testResult.error}
            summary={[
              { label: "Template Version", value: currentTemplate ? `v${currentTemplate.version}` : "-" },
              { label: "JSON Parse Strategy", value: modelForm.json_parse_strategy },
              { label: "Image ID", value: testPhotoId != null ? String(testPhotoId) : "-" },
            ]}
            requestPayload={{
              image_id: testPhotoId,
              prompt_template_id: currentTemplate?.id ?? null,
              override_prompt: effectivePrompt,
              provider: modelForm.provider,
              endpoint_url: modelForm.endpoint_url,
              model_name: modelForm.model_name,
              json_parse_strategy: modelForm.json_parse_strategy,
            }}
            rawOutput={testResult.raw_output}
            parsedOutput={testResult.parsed_json}
          />
        ) : (
          <div className="border border-hairline rounded-md p-3 bg-surface-soft text-body-sm text-mute">
            (暂无测试结果)
          </div>
        )}

        <div className="pt-2 border-t border-hairline">
          <div className="flex items-center justify-between gap-2 mb-2">
            <h3 className="text-body-sm font-semibold text-ink">最近测试历史</h3>
            <button
              onClick={clearTestHistory}
              disabled={testHistory.length === 0}
              className="text-caption-sm text-danger hover:text-danger-pressed disabled:text-stone"
            >
              清空历史
            </button>
          </div>
          {testHistory.length === 0 ? (
            <p className="text-caption-sm text-mute mb-3">暂无测试历史</p>
          ) : (
            <div className="space-y-2 mb-3">
              {testHistory.map((item) => (
                <details key={item.id} className="bg-surface-soft border border-hairline rounded-md px-3 py-2">
                  <summary className="cursor-pointer text-body-sm text-ink flex items-center justify-between gap-2">
                    <span>
                      {new Date(item.tested_at).toLocaleString()} · {item.file_name}
                    </span>
                    <span className={item.result.success ? "text-green-700 text-caption-sm" : "text-amber-700 text-caption-sm"}>
                      {item.result.success ? "解析成功" : "解析失败"}
                    </span>
                  </summary>
                  <div className="mt-2 space-y-2">
                    <p className="text-caption-sm text-mute">
                      image #{item.image_id} · template v{item.template_version ?? "-"} · {item.result.duration_ms}ms
                    </p>
                    <div className="flex gap-2">
                      <button
                        onClick={() => loadHistoryResult(item)}
                        className="text-caption-sm text-primary hover:text-primary-pressed"
                      >
                        载入结果
                      </button>
                      <button
                        onClick={() => copyText(item.result.raw_output, onMessage)}
                        className="text-caption-sm text-primary hover:text-primary-pressed"
                      >
                        复制原始输出
                      </button>
                    </div>
                    {item.result.error && (
                      <p className="text-caption-sm text-danger whitespace-pre-wrap break-all">{item.result.error}</p>
                    )}
                  </div>
                </details>
              ))}
            </div>
          )}

          <h3 className="text-body-sm font-semibold text-ink mb-2">最近失败输出</h3>
          {latestFailed.length === 0 ? (
            <p className="text-caption-sm text-mute">暂无失败任务记录</p>
          ) : (
            <div className="space-y-2">
              {latestFailed.slice(0, 3).map((job) => (
                <details key={job.id} className="bg-surface-soft border border-hairline rounded-md px-3 py-2">
                  <summary className="cursor-pointer text-body-sm text-ink">
                    #{job.id} · {job.file_name ?? `photo:${job.photo_id}`} · prompt v{job.prompt_version ?? "-"}
                  </summary>
                  <div className="mt-2 space-y-2">
                    <div>
                      <p className="text-caption-sm text-mute">parse_error</p>
                      <pre className="text-caption-sm whitespace-pre-wrap break-all">{job.parse_error || "(空)"}</pre>
                    </div>
                    <div>
                      <p className="text-caption-sm text-mute">raw_model_output</p>
                      <pre className="max-h-40 overflow-auto text-caption-sm whitespace-pre-wrap break-all">{job.raw_model_output || "(空)"}</pre>
                    </div>
                  </div>
                </details>
              ))}
            </div>
          )}
        </div>
      </SettingsCard>
    </>
  );
}
