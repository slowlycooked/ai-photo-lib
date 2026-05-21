import type { DebugMatrix, LogLevel } from "@/lib/api";

type LoggerPayload = Record<string, unknown> | undefined;

const LEVEL_WEIGHT: Record<LogLevel, number> = {
  OFF: 99,
  ERROR: 40,
  WARNING: 30,
  INFO: 20,
  DEBUG: 10,
  TRACE: 0,
};

let frontendLogLevel: LogLevel = "INFO";

function shouldLog(level: LogLevel): boolean {
  return LEVEL_WEIGHT[level] >= LEVEL_WEIGHT[frontendLogLevel];
}

export function configureFrontendLogger(settings: Pick<DebugMatrix, "frontendLogLevel">): void {
  frontendLogLevel = settings.frontendLogLevel;
}

function renderArgs(message: string, payload?: LoggerPayload): unknown[] {
  if (!payload) return [message];
  return [message, payload];
}

export const logger = {
  error(message: string, payload?: LoggerPayload): void {
    if (!shouldLog("ERROR")) return;
    console.error(...renderArgs(message, payload));
  },
  warn(message: string, payload?: LoggerPayload): void {
    if (!shouldLog("WARNING")) return;
    console.warn(...renderArgs(message, payload));
  },
  info(message: string, payload?: LoggerPayload): void {
    if (!shouldLog("INFO")) return;
    console.info(...renderArgs(message, payload));
  },
  debug(message: string, payload?: LoggerPayload): void {
    if (!shouldLog("DEBUG")) return;
    console.debug(...renderArgs(message, payload));
  },
};
