"use client";
import { create } from "zustand";

interface ShadowStore {
  // Stan trybu Shadow — zostanie rozbudowany w kolejnych fazach
}

export const useShadowStore = create<ShadowStore>(() => ({}));
