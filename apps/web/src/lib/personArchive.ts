import type { PersonSummary } from "@/api";

const MANUAL_ARCHIVE_KEY_PREFIX = "people-manual-archive-v1";
const MANUAL_MANAGE_KEY_PREFIX = "people-manual-manage-v1";

function manualArchiveStorageKey(projectId: number): string {
  return `${MANUAL_ARCHIVE_KEY_PREFIX}:${projectId}`;
}

function manualManageStorageKey(projectId: number): string {
  return `${MANUAL_MANAGE_KEY_PREFIX}:${projectId}`;
}

function readManualArchivedIds(projectId: number): number[] {
  if (typeof localStorage === "undefined" || typeof localStorage.getItem !== "function") return [];
  try {
    const raw = localStorage.getItem(manualArchiveStorageKey(projectId));
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((value) => Number.isInteger(value) && value > 0);
  } catch {
    return [];
  }
}

function readManualManagedIds(projectId: number): number[] {
  if (typeof localStorage === "undefined" || typeof localStorage.getItem !== "function") return [];
  try {
    const raw = localStorage.getItem(manualManageStorageKey(projectId));
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((value) => Number.isInteger(value) && value > 0);
  } catch {
    return [];
  }
}

function writeManualArchivedIds(projectId: number, ids: number[]): void {
  if (typeof localStorage === "undefined" || typeof localStorage.setItem !== "function") return;
  localStorage.setItem(manualArchiveStorageKey(projectId), JSON.stringify(ids));
}

function writeManualManagedIds(projectId: number, ids: number[]): void {
  if (typeof localStorage === "undefined" || typeof localStorage.setItem !== "function") return;
  localStorage.setItem(manualManageStorageKey(projectId), JSON.stringify(ids));
}

export function getManualArchivedPersonIds(projectId: number): Set<number> {
  return new Set(readManualArchivedIds(projectId));
}

export function getManualManagedPersonIds(projectId: number): Set<number> {
  return new Set(readManualManagedIds(projectId));
}

export function archivePersonManually(projectId: number, personId: number): Set<number> {
  const current = getManualArchivedPersonIds(projectId);
  current.add(personId);
  writeManualArchivedIds(projectId, Array.from(current));
  return current;
}

export function forceManagePersonManually(projectId: number, personId: number): Set<number> {
  const current = getManualManagedPersonIds(projectId);
  current.add(personId);
  writeManualManagedIds(projectId, Array.from(current));
  return current;
}

export function unarchivePersonManually(projectId: number, personId: number): Set<number> {
  const current = getManualArchivedPersonIds(projectId);
  current.delete(personId);
  writeManualArchivedIds(projectId, Array.from(current));
  return current;
}

export function unforceManagePersonManually(projectId: number, personId: number): Set<number> {
  const current = getManualManagedPersonIds(projectId);
  current.delete(personId);
  writeManualManagedIds(projectId, Array.from(current));
  return current;
}

export function isArchivedPerson(
  person: Pick<
    PersonSummary,
    "created_by" | "is_named" | "review_pending_count"
  >,
): boolean {
  return person.created_by.startsWith("system") && !person.is_named && person.review_pending_count <= 0;
}