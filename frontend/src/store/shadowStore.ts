"use client";
import { create } from "zustand";

interface ShadowStore {
  originalText: string;
  setOriginalText: (text: string) => void;
  resetShadow: () => void;
}

export const useShadowStore = create<ShadowStore>((set) => ({
  originalText: "",
  setOriginalText: (originalText) => set({ originalText }),
  resetShadow: () => set({ originalText: "" }),
}));
