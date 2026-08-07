import { describe, it, expect } from "vitest";
import { ApiError } from "../../src/api/client";

describe("ApiClient & ApiError", () => {
  it("should create ApiError with code and requestId", () => {
    const err = new ApiError("DATASET_NOT_FOUND", "数据集不存在", "req-12345", { id: "ds_1" });
    expect(err.code).toBe("DATASET_NOT_FOUND");
    expect(err.message).toBe("数据集不存在");
    expect(err.requestId).toBe("req-12345");
    expect(err.details?.id).toBe("ds_1");
  });
});
