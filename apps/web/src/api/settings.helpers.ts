/**
 * Normalisation helpers for the DebugSettingsResponse payload.
 * Extracted from the original monolithic api.ts.
 */

import type {
  DebugMatrix,
  DebugMode,
  DebugPresetMode,
  DebugSettingsResponse,
  LogLevel,
} from "./types";

export const DEFAULT_DEBUG_PRESETS: Record<DebugPresetMode, DebugMatrix> = {
  OFF: {
    frontendLogLevel: "OFF",
    backendLogLevel: "OFF",
    aiLogLevel: "OFF",
    searchLogLevel: "OFF",
    sqlLogLevel: "OFF",
    taskLogLevel: "OFF",
  },
  BASIC: {
    frontendLogLevel: "INFO",
    backendLogLevel: "INFO",
    aiLogLevel: "INFO",
    searchLogLevel: "INFO",
    sqlLogLevel: "WARNING",
    taskLogLevel: "INFO",
  },
  DEBUG: {
    frontendLogLevel: "DEBUG",
    backendLogLevel: "DEBUG",
    aiLogLevel: "DEBUG",
    searchLogLevel: "DEBUG",
    sqlLogLevel: "DEBUG",
    taskLogLevel: "DEBUG",
  },
  TRACE: {
    frontendLogLevel: "TRACE",
    backendLogLevel: "TRACE",
    aiLogLevel: "TRACE",
    searchLogLevel: "TRACE",
    sqlLogLevel: "TRACE",
    taskLogLevel: "TRACE",
  },
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function normaliseDebugMode(value: unknown): DebugMode {
  if (typeof value !== "string") return "BASIC";
  const mode = value.trim().toUpperCase();
  if (
    mode === "OFF" ||
    mode === "BASIC" ||
    mode === "DEBUG" ||
    mode === "TRACE" ||
    mode === "CUSTOM"
  ) {
    return mode as DebugMode;
  }
  return "BASIC";
}

export function normaliseLogLevel(value: unknown, fallback: LogLevel): LogLevel {
  if (typeof value !== "string") return fallback;
  const level = value.trim().toUpperCase();
  if (
    level === "OFF" ||
    level === "ERROR" ||
    level === "WARNING" ||
    level === "INFO" ||
    level === "DEBUG" ||
    level === "TRACE"
  ) {
    return level as LogLevel;
  }
  if (level === "WARN") return "WARNING";
  return fallback;
}

function readLevel(
  source: Record<string, unknown>,
  camelKey: string,
  snakeKey: string,
  fallback: LogLevel,
): LogLevel {
  return normaliseLogLevel(source[camelKey] ?? source[snakeKey], fallback);
}

export function normaliseMatrix(rawMatrix: unknown, fallback: DebugMatrix): DebugMatrix {
  const source = isRecord(rawMatrix) ? rawMatrix : {};
  return {
    frontendLogLevel: readLevel(
      source,
      "frontendLogLevel",
      "frontend_log_level",
      fallback.frontendLogLevel,
    ),
    backendLogLevel: readLevel(
      source,
      "backendLogLevel",
      "backend_log_level",
      fallback.backendLogLevel,
    ),
    aiLogLevel: readLevel(source, "aiLogLevel", "ai_log_level", fallback.aiLogLevel),
    searchLogLevel: readLevel(
      source,
      "searchLogLevel",
      "search_log_level",
      fallback.searchLogLevel,
    ),
    sqlLogLevel: readLevel(
      source,
      "sqlLogLevel",
      "sql_log_level",
      normaliseLogLevel(source["db_log_level"], fallback.sqlLogLevel),
    ),
    taskLogLevel: readLevel(
      source,
      "taskLogLevel",
      "task_log_level",
      fallback.taskLogLevel,
    ),
  };
}

export function normalisePresets(
  rawPresets: unknown,
): Record<DebugPresetMode, DebugMatrix> {
  const source = isRecord(rawPresets) ? rawPresets : {};
  return {
    OFF: normaliseMatrix(source["OFF"], DEFAULT_DEBUG_PRESETS.OFF),
    BASIC: normaliseMatrix(source["BASIC"], DEFAULT_DEBUG_PRESETS.BASIC),
    DEBUG: normaliseMatrix(source["DEBUG"], DEFAULT_DEBUG_PRESETS.DEBUG),
    TRACE: normaliseMatrix(source["TRACE"], DEFAULT_DEBUG_PRESETS.TRACE),
  };
}

export function normaliseDebugSettingsResponse(raw: unknown): DebugSettingsResponse {
  const source = isRecord(raw) ? raw : {};
  const mode = normaliseDebugMode(source["debugMode"] ?? source["debug_mode"]);
  const presets = normalisePresets(source["presets"]);

  return {
    debugMode: mode,
    debugMatrix: normaliseMatrix(
      source["debugMatrix"] ?? source["debug_matrix"] ?? source,
      mode === "CUSTOM" ? presets.BASIC : presets[mode as DebugPresetMode],
    ),
    presets,
    updatedAt:
      typeof source["updatedAt"] === "string"
        ? source["updatedAt"]
        : typeof source["updated_at"] === "string"
          ? source["updated_at"]
          : null,
  };
}
