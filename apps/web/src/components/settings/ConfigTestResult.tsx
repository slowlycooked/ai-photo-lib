import { AlertTriangle, CheckCircle2, Clock3 } from "lucide-react";

interface SummaryItem {
  label: string;
  value: string;
}

interface ConfigTestResultProps {
  title: string;
  success: boolean;
  latencyMs?: number | null;
  model?: string | null;
  errorMessage?: string | null;
  warningMessage?: string | null;
  summary?: SummaryItem[];
  requestPayload?: unknown;
  rawOutput?: unknown;
  parsedOutput?: unknown;
}

function renderBlockValue(value: unknown): string {
  if (value == null) return "(empty)";
  if (typeof value === "string") return value || "(empty)";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function Block({ title, value }: { title: string; value: unknown }) {
  return (
    <div>
      <p className="text-xs font-medium text-gray-700 mb-1">{title}</p>
      <pre className="text-xs bg-slate-900 text-slate-100 rounded p-2 overflow-auto max-h-64 whitespace-pre-wrap break-words">
        {renderBlockValue(value)}
      </pre>
    </div>
  );
}

export function ConfigTestResult({
  title,
  success,
  latencyMs,
  model,
  errorMessage,
  warningMessage,
  summary,
  requestPayload,
  rawOutput,
  parsedOutput,
}: ConfigTestResultProps) {
  return (
    <section className="rounded-md border border-hairline bg-surface-soft p-3 space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-ink">{title}</span>
        <span
          className={[
            "inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded",
            success ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700",
          ].join(" ")}
        >
          {success ? <CheckCircle2 className="w-3.5 h-3.5" /> : <AlertTriangle className="w-3.5 h-3.5" />}
          {success ? "Success" : "Failed"}
        </span>
        {latencyMs != null && (
          <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded bg-secondary-bg text-mute">
            <Clock3 className="w-3.5 h-3.5" />
            {latencyMs}ms
          </span>
        )}
        {model ? (
          <span className="text-xs px-2 py-0.5 rounded bg-secondary-bg text-ink font-mono">{model}</span>
        ) : null}
      </div>

      {errorMessage ? (
        <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded px-2 py-1">
          {errorMessage}
        </p>
      ) : null}

      {warningMessage ? (
        <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1">
          {warningMessage}
        </p>
      ) : null}

      {summary && summary.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {summary.map((item) => (
            <div key={item.label} className="rounded border border-hairline bg-canvas px-2.5 py-2">
              <p className="text-caption-sm text-mute">{item.label}</p>
              <p className="text-body-sm text-ink break-all">{item.value}</p>
            </div>
          ))}
        </div>
      ) : null}

      {requestPayload !== undefined ? <Block title="Request Payload" value={requestPayload} /> : null}
      {rawOutput !== undefined ? <Block title="Raw Output" value={rawOutput} /> : null}
      {parsedOutput !== undefined ? <Block title="Parsed Output" value={parsedOutput} /> : null}
    </section>
  );
}
