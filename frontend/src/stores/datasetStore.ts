import { defineStore } from "pinia";
import { ref } from "vue";
import type { DatasetItem, DatasetProfile } from "../types/api";

export const useDatasetStore = defineStore("dataset", () => {
  const activeDataset = ref<DatasetItem | null>(null);
  const activeProfile = ref<DatasetProfile | null>(null);
  const datasetsList = ref<DatasetItem[]>([]);

  function setActiveDataset(ds: DatasetItem | null) {
    activeDataset.value = ds;
  }

  function setDatasetsList(list: DatasetItem[]) {
    datasetsList.value = list;
  }

  function setProfile(profile: DatasetProfile | null) {
    activeProfile.value = profile;
  }

  return {
    activeDataset,
    activeProfile,
    datasetsList,
    setActiveDataset,
    setDatasetsList,
    setProfile,
  };
});
