import { qs, request } from "./client";
import type { SearchResponse } from "./types";

export const searchApi = {
  search: (projectId: number, q: string, page = 1, pageSize = 50) =>
    request<SearchResponse>(
      `/projects/${projectId}/search${qs({
        q,
        page,
        page_size: pageSize,
        mode: "auto",
      })}`,
    ),
};
