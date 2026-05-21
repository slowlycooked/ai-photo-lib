/**
 * Compatibility re-export shim.
 *
 * All API implementations, types, and helpers live in src/api/*.
 * Existing `import { api, Photo, Project, ApiError, ... } from "@/lib/api"`
 * continues to work unchanged.
 */
export * from "../api/index";
