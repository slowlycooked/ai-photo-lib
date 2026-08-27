import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Photo } from "@/api";
import { PhotoCard } from "./PhotoCard";

const photo = {
  id: 42,
  project_id: 7,
  file_name: "example.jpg",
  updated_at: "2026-08-24T12:00:00Z",
} as Photo;

describe("PhotoCard", () => {
  it("lets the user retry a failed thumbnail with a cache-busting URL", () => {
    render(<PhotoCard photo={photo} />);
    const firstImage = screen.getByRole("img", { name: "example.jpg" });
    const firstSrc = firstImage.getAttribute("src");

    fireEvent.error(firstImage);
    fireEvent.click(screen.getByRole("button", { name: "无法加载，点击重试" }));

    const retriedImage = screen.getByRole("img", { name: "example.jpg" });
    expect(retriedImage.getAttribute("src")).not.toBe(firstSrc);
    expect(retriedImage.getAttribute("src")).toContain("retry=");
  });

  it("uses a valid query separator when the thumbnail has no version", () => {
    render(<PhotoCard photo={{ ...photo, updated_at: "" }} />);
    fireEvent.error(screen.getByRole("img", { name: "example.jpg" }));
    fireEvent.click(screen.getByRole("button", { name: "无法加载，点击重试" }));

    expect(screen.getByRole("img", { name: "example.jpg" }).getAttribute("src")).toContain(
      "/thumbnail?retry=",
    );
  });

  it("marks a located photo and exposes a focus target", () => {
    render(<PhotoCard photo={photo} highlighted />);

    expect(screen.getByText("定位目标")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "查看照片 example.jpg" })).toHaveAttribute(
      "id",
      "photo-42",
    );
  });
});
