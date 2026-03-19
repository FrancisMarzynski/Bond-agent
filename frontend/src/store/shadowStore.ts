"use client";
import { create } from "zustand";

export interface Annotation {
  id: string;
  original_span: string;
  replacement: string;
  reason: string;
  start_index: number;
  end_index: number;
}

interface ShadowStore {
  originalText: string;
  annotations: Annotation[];
  shadowCorrectedText: string;
  setOriginalText: (text: string) => void;
  setAnnotations: (annotations: Annotation[]) => void;
  setShadowCorrectedText: (text: string) => void;
  resetShadow: () => void;
}

export const useShadowStore = create<ShadowStore>((set) => ({
  originalText: "",
  annotations: [],
  shadowCorrectedText: "",
  setOriginalText: (originalText) => set({ originalText }),
  setAnnotations: (annotations) => set({ annotations }),
  setShadowCorrectedText: (shadowCorrectedText) => set({ shadowCorrectedText }),
  resetShadow: () => set({ originalText: "", annotations: [], shadowCorrectedText: "" }),
}));
