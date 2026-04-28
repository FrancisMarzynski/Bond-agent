"use client";
import { AnnotationList } from "@/components/AnnotationList";
import type { Annotation } from "@/store/shadowStore";

interface ShadowAnnotationsSectionProps {
  annotations: Annotation[];
  activeId: string | null;
  onAnnotationClick: (annotation: Annotation) => void;
  onApplyAll: () => void;
  isStreaming: boolean;
}

export function ShadowAnnotationsSection(props: ShadowAnnotationsSectionProps) {
  return (
    <section className="border-b bg-background">
      <AnnotationList {...props} layout="section" />
    </section>
  );
}
