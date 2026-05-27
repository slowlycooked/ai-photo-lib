export type CapabilityMaturityLevel = "stable" | "experimental" | "converging";

export interface CapabilityMaturityItem {
  key:
    | "face_clustering"
    | "face_rematch_unknown"
    | "search_face_filters"
    | "system_health_check"
    | "prompt_testing"
    | "embedding_rebuild";
  capability: string;
  level: CapabilityMaturityLevel;
  levelLabel: "稳定" | "实验" | "待收敛";
  hint: string;
}

export const CAPABILITY_MATURITY: Record<CapabilityMaturityItem["key"], CapabilityMaturityItem> = {
  face_clustering: {
    key: "face_clustering",
    capability: "Face clustering",
    level: "stable",
    levelLabel: "稳定",
    hint: "聚类任务已纳入项目级队列、状态跟踪与 Review Pending 主链路。",
  },
  face_rematch_unknown: {
    key: "face_rematch_unknown",
    capability: "Face rematch unknown",
    level: "stable",
    levelLabel: "稳定",
    hint: "未知人脸重匹配已纳入项目级队列，并保留人工确认结果。",
  },
  search_face_filters: {
    key: "search_face_filters",
    capability: "Search face filters",
    level: "stable",
    levelLabel: "稳定",
    hint: "合照、单人照、待确认和未命名人物筛选已接入搜索主链路。",
  },
  system_health_check: {
    key: "system_health_check",
    capability: "System health check",
    level: "stable",
    levelLabel: "稳定",
    hint: "运行状态检查覆盖 DB、migration、路径、模型配置和 auth 配置。",
  },
  prompt_testing: {
    key: "prompt_testing",
    capability: "Prompt 测试",
    level: "stable",
    levelLabel: "稳定",
    hint: "Prompt 测试支持项目模板、测试图片、解析结果与本地历史回看。",
  },
  embedding_rebuild: {
    key: "embedding_rebuild",
    capability: "Embedding rebuild",
    level: "stable",
    levelLabel: "稳定",
    hint: "支持项目级重建与状态跟踪，可作为发布能力默认入口。",
  },
};

export const CAPABILITY_MATURITY_LIST: CapabilityMaturityItem[] = [
  CAPABILITY_MATURITY.face_clustering,
  CAPABILITY_MATURITY.face_rematch_unknown,
  CAPABILITY_MATURITY.search_face_filters,
  CAPABILITY_MATURITY.system_health_check,
  CAPABILITY_MATURITY.prompt_testing,
  CAPABILITY_MATURITY.embedding_rebuild,
];
