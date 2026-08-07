import { describe, it, expect, beforeEach } from "vitest";
import { setActivePinia, createPinia } from "pinia";
import { useDatasetStore } from "../../src/stores/datasetStore";
import { useSystemStore } from "../../src/stores/systemStore";

describe("Pinia Stores", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("should manage active dataset state", () => {
    const store = useDatasetStore();
    expect(store.activeDataset).toBeNull();

    const mockItem = {
      id: "ds_test",
      name: "Test Dataset",
      version_id: "V0_Original",
      file_size_bytes: 1000,
      row_count: 100,
      col_count: 3,
      created_at: "2026-07-28T00:00:00Z",
      time_column: "timestamp",
      input_columns: ["u1"],
      output_column: "y",
    };

    store.setActiveDataset(mockItem);
    expect(store.activeDataset?.id).toBe("ds_test");
  });

  it("should manage system health state", () => {
    const store = useSystemStore();
    expect(store.isHealthy).toBe(true);

    store.setHealth(
      { status: "ok", uptime_seconds: 120 },
      { status: "healthy", components: { postgres: { status: "ok" }, redis: { status: "ok" } } }
    );

    expect(store.isHealthy).toBe(true);
  });
});
