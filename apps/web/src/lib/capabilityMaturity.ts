export type CapabilityMaturityLevel = "stable" | "experimental" | "converging";

export interface CapabilityMaturityItem {
  key: "face_clustering" | "prompt_testing" | "embedding_rebuild";
  capability: string;
  level: CapabilityMaturityLevel;
  levelLabel: "稳定" | "实验" | "待收敛";
  hint: string;
}

export const CAPABILITY_MATURITY: Record<CapabilityMaturityItem["key"], CapabilityMaturityItem> = {
  face_clustering: {
    key: "face_clustering",
    capability: "Face clustering",
    level: "experimental",
    levelLabel: "实验",
    hint: "算法和参数仍在持续打磨，建议在 review 流程中复核结果。",
  },
  prompt_testing: {
    key: "prompt_testing",
    capability: "Prompt 测试",
    level: "converging",
    levelLabel: "待收敛",
    hint: "关键链路可用，交互与历史管理规则仍在持续收敛。",
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
  CAPABILITY_MATURITY.prompt_testing,
  CAPABILITY_MATURITY.embedding_rebuild,
];
