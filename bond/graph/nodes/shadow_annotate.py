"""Shadow annotate node — structured annotation generation with index validation.

Responsibility:
1. Call the DRAFT_MODEL LLM with `with_structured_output` to produce a deterministic
   list of style annotations (Pydantic → JSON schema enforced).
2. Validate that each annotation's start_index and end_index fall within the text bounds
   and align with the declared original_span (cross-check + auto-correct).
3. Apply valid annotations to assemble shadow_corrected_text.
4. Return: annotations (list[Annotation]) and shadow_corrected_text (str).
"""
from __future__ import annotations

import logging
from typing import Optional

from pydantic import BaseModel, Field

from bond.graph.state import Annotation, BondState
from bond.llm import get_draft_llm

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic models for with_structured_output (deterministic JSON schema)
# ---------------------------------------------------------------------------

class AnnotationItem(BaseModel):
    """Single style correction with character-level span indices."""

    id: str = Field(
        description=(
            "Stabilny identyfikator adnotacji, np. 'ann_001', 'ann_002'. "
            "Nadawaj go zgodnie z kolejnością występowania w tekście."
        )
    )
    original_span: str = Field(
        description=(
            "Dokładny, dosłowny fragment z nadesłanego tekstu, który ma zostać zastąpiony. "
            "Powinien mieć co najmniej 10 znaków i być jednoznaczny w obrębie tekstu. "
            "Jeżeli fraza powtarza się wielokrotnie, dołącz wystarczająco szeroki kontekst."
        )
    )
    replacement: str = Field(
        description=(
            "Poprawiona wersja fragmentu zgodna ze stylem autora z korpusu. "
            "Zachowaj poprawną interpunkcję i kontekst wielkich liter."
        )
    )
    reason: str = Field(
        description=(
            "Krótkie uzasadnienie po polsku (1-2 zdania), odnoszące się do stylu autora. "
            "Nie używaj angielskich zdań ani angielskich zwrotów o stylu autora."
        )
    )
    start_index: int = Field(
        description=(
            "Indeks początkowy znaku (włącznie, 0-based) dla original_span "
            "w nadesłanym tekście. Musi zachodzić warunek: "
            "text[start_index:end_index] == original_span."
        )
    )
    end_index: int = Field(
        description=(
            "Indeks końcowy znaku (wyłącznie, 0-based) dla original_span "
            "w nadesłanym tekście. Musi zachodzić warunek: "
            "text[start_index:end_index] == original_span."
        )
    )


class AnnotationResult(BaseModel):
    """Complete structured output from the style annotator LLM."""

    annotations: list[AnnotationItem] = Field(
        description=(
            "Wszystkie poprawki stylistyczne uporządkowane rosnąco po start_index. "
            "Uwzględnij wszystkie istotne odchylenia od stylu autora — "
            "ton, słownictwo, rytm i interpunkcję."
        )
    )
    alignment_summary: str = Field(
        default="",
        description=(
            "Opcjonalne, krótkie podsumowanie po polsku (1-2 zdania) o zgodności tekstu ze stylem autora. "
            "Uzupełnij je tylko wtedy, gdy liczba adnotacji przekracza 5; w przeciwnym razie pozostaw puste."
        ),
    )


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
Jesteś redaktorem stylistycznym. Twoje zadanie to precyzyjna korekta nadesłanego tekstu \
tak, by jak najdokładniej pasował do stylu wzorcowego autora (fragmenty korpusu podano poniżej).

Analizujesz trzy obszary:
1. TON — emocjonalny ładunek, dystans do czytelnika, pewność siebie, poziom formalności
2. RYTM ZDAŃ — długość, interpunkcja, użycie myślników/średników, struktura akapitów
3. SŁOWNICTWO — aktywne vs pasywne konstrukcje, specjalistyczne terminy, powtarzające się wzorce

Dla każdej adnotacji MUSISZ podać precyzyjne indeksy znakowe (start_index, end_index) \
wskazujące pozycję cytatu original_span w nadesłanym tekście.
Obowiązuje warunek: tekst[start_index:end_index] == original_span (dokładne dopasowanie).\

Wszystkie pola tekstowe odpowiedzi muszą być po polsku.
W szczególności pole `reason` ma być zawsze po polsku i ma opisywać decyzję redakcyjną, \
a nie instruować użytkownika po angielsku. Nie używaj angielskich formułek o stylu autora.\
"""


def _build_user_prompt(
    original_text: str,
    fragments: list[dict],
    feedback: str | None = None,
) -> str:
    corpus_block = "\n\n---\n\n".join(
        f"[Fragment {i + 1}]\n{frag['text']}" for i, frag in enumerate(fragments)
    )
    base = (
        f"## TEKST DO KOREKTY\n\n{original_text}\n\n"
        f"## WZORCOWE FRAGMENTY KORPUSU AUTORA\n\n{corpus_block}\n\n"
    )
    if feedback:
        base += (
            f"## FEEDBACK Z POPRZEDNIEJ ITERACJI\n\n{feedback}\n\n"
            "Uwzględnij powyższy feedback — popraw adnotacje zgodnie z uwagami użytkownika. "
        )
    base += (
        "Wygeneruj listę adnotacji stylistycznych. Dla każdej: podaj dokładny original_span, "
        "replacement, reason oraz start_index i end_index w tekście. "
        "Pole `reason` napisz wyłącznie po polsku."
    )
    return base


# ---------------------------------------------------------------------------
# Index validation & auto-correction
# ---------------------------------------------------------------------------

def _validate_and_fix_annotation(
    item: AnnotationItem,
    text: str,
) -> Optional[Annotation]:
    """Validate a single annotation's indices against the text.

    Three-pass validation:
    1. Accept as-is if indices are in bounds AND text[start:end] == original_span.
    2. Auto-correct indices by searching for original_span in text (first occurrence).
    3. Reject the annotation if original_span is not found anywhere in the text.

    Returns an Annotation TypedDict on success, None on failure.
    """
    text_len = len(text)
    start = item.start_index
    end = item.end_index

    # Pass 1: indices in bounds and match declared span
    if (
        0 <= start < text_len
        and start < end <= text_len
        and text[start:end] == item.original_span
    ):
        return Annotation(
            id=item.id,
            original_span=item.original_span,
            replacement=item.replacement,
            reason=item.reason,
            start_index=start,
            end_index=end,
        )

    # Pass 2: auto-correct by searching for the span
    idx = text.find(item.original_span)
    if idx != -1:
        corrected_end = idx + len(item.original_span)
        if idx != start or corrected_end != end:
            logger.warning(
                "shadow_annotate: corrected indices for '%s': [%d:%d] → [%d:%d]",
                item.id,
                start,
                end,
                idx,
                corrected_end,
            )
        return Annotation(
            id=item.id,
            original_span=item.original_span,
            replacement=item.replacement,
            reason=item.reason,
            start_index=idx,
            end_index=corrected_end,
        )

    # Pass 3: reject — span not found in text
    logger.warning(
        "shadow_annotate: discarding annotation '%s' — original_span not found in text. "
        "Indices were [%d:%d], text length %d.",
        item.id,
        start,
        end,
        text_len,
    )
    return None


# ---------------------------------------------------------------------------
# Text assembly
# ---------------------------------------------------------------------------

def _apply_annotations(original: str, annotations: list[Annotation]) -> str:
    """Apply annotations to produce corrected text.

    Annotations are applied in reverse index order so earlier replacements
    do not shift the character positions of later ones.
    Replacements that change text length are handled correctly because each
    annotation's start_index/end_index refers to the *original* text.
    """
    sorted_anns = sorted(annotations, key=lambda a: a["start_index"], reverse=True)
    result = original
    for ann in sorted_anns:
        s = ann["start_index"]
        e = ann["end_index"]
        result = result[:s] + ann["replacement"] + result[e:]
    return result


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

async def shadow_annotate_node(state: BondState) -> dict:
    """Generate structured style annotations and assemble corrected text.

    AC compliance:
    - Uses with_structured_output(AnnotationResult) for deterministic JSON output.
    - Validates start_index and end_index against len(original_text) with auto-correction.
    - Returns annotations: list[Annotation] and shadow_corrected_text: str.
    """
    original_text = (state.get("original_text") or "").strip()
    if not original_text:
        logger.warning("shadow_annotate: original_text is empty — skipping annotation.")
        return {
            "annotations": [],
            "shadow_corrected_text": "",
        }

    fragments: list[dict] = state.get("shadow_corpus_fragments") or []
    if not fragments:
        logger.warning(
            "shadow_annotate: no corpus fragments available — "
            "annotations will lack style reference."
        )

    feedback: str | None = state.get("shadow_feedback") or None
    if feedback:
        logger.info("shadow_annotate: re-run with user feedback — incorporating into prompt.")

    # Select LLM — temperature=0 for deterministic structured output
    llm = get_draft_llm(max_tokens=4096, temperature=0)

    structured_llm = llm.with_structured_output(AnnotationResult)

    user_prompt = _build_user_prompt(original_text, fragments, feedback=feedback)
    result: AnnotationResult = await structured_llm.ainvoke([
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ])

    logger.info(
        "shadow_annotate: LLM returned %d annotation(s).", len(result.annotations)
    )

    # Validate indices and discard any annotation that fails all three passes
    text_len = len(original_text)
    valid_annotations: list[Annotation] = []
    for item in result.annotations:
        # Boundary pre-check (logged separately by _validate_and_fix_annotation)
        if item.start_index < 0 or item.end_index > text_len:
            logger.warning(
                "shadow_annotate: annotation '%s' has out-of-bounds indices "
                "[%d:%d] for text of length %d — attempting auto-correction.",
                item.id,
                item.start_index,
                item.end_index,
                text_len,
            )
        ann = _validate_and_fix_annotation(item, original_text)
        if ann is not None:
            valid_annotations.append(ann)

    logger.info(
        "shadow_annotate: %d/%d annotation(s) passed validation.",
        len(valid_annotations),
        len(result.annotations),
    )

    corrected_text = _apply_annotations(original_text, valid_annotations)

    return {
        "annotations": valid_annotations,
        "shadow_corrected_text": corrected_text,
    }
