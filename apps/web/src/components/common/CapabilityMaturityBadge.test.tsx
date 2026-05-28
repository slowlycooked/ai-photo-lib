import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CapabilityMaturityBadge } from "@/components/common/CapabilityMaturityBadge";
import { CAPABILITY_MATURITY_LIST } from "@/lib/capabilityMaturity";

describe("CapabilityMaturityBadge", () => {
  it("renders all maturity levels with consistent label and hint", () => {
    render(
      <div>
        {CAPABILITY_MATURITY_LIST.map((item) => (
          <div key={item.key}>
            <CapabilityMaturityBadge item={item} />
            <p>{item.hint}</p>
          </div>
        ))}
      </div>
    );

    expect(screen.getByText("Face clustering · 稳定")).toBeInTheDocument();
    expect(screen.getByText("Task controls · 稳定")).toBeInTheDocument();
    expect(screen.getByText("Prompt 测试 · 稳定")).toBeInTheDocument();
    expect(screen.getByText("Embedding rebuild · 稳定")).toBeInTheDocument();

    expect(screen.getByText(/状态跟踪与 Review Pending 主链路/)).toBeInTheDocument();
    expect(screen.getByText(/暂停、取消与失败明细查看/)).toBeInTheDocument();
    expect(screen.getByText(/支持项目级重建与状态跟踪/)).toBeInTheDocument();
  });
});
