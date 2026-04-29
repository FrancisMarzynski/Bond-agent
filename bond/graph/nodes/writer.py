import logging
import re
from typing import Any, Literal, Optional

import markdown as _md
from bs4 import BeautifulSoup
from pydantic import ValidationError

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END
from langgraph.types import Command, interrupt

from bond.config import settings
from bond.graph.state import (
    AuthorState,
    DraftValidationAttempt,
    DraftValidationChecks,
    DraftValidationDetails,
    DraftValidationFailure,
)
from bond.llm import estimate_cost_usd, get_draft_llm
from bond.prompts.context import build_context_block
from bond.prompts.research_context import select_research_context
from bond.prompts.writer import FORBIDDEN_WORD_STEMS, WRITER_SYSTEM_PROMPT
from bond.schemas import CheckpointResponse
from bond.store.article_log import get_article_count
from bond.store.chroma import get_corpus_collection

log = logging.getLogger(__name__)

_RERANK_FETCH_N = 15  # Candidates fetched before reranking
_WRITER_MAX_OUTPUT_TOKENS = 4096
_META_DESCRIPTION_MIN_LENGTH = 150
_META_DESCRIPTION_MAX_LENGTH = 160
_WORD_COUNT_BUFFER = 120

# Module-level singleton — model loaded once per process
_ranker = None


def _get_ranker():
    global _ranker
    if _ranker is None:
        from flashrank import Ranker

        # ms-marco-MultiBERT-L-12 supports multilingual text (incl. Polish)
        _ranker = Ranker(
            model_name="ms-marco-MultiBERT-L-12", cache_dir="/tmp/flashrank"
        )
    return _ranker


def _rerank(query: str, candidates: list[dict], top_n: int) -> list[dict]:
    """Rerank candidate dicts by FlashRank score on their 'text' field.

    Each candidate dict must contain a 'text' key. The original dict is
    returned (with all metadata preserved), sorted by cross-encoder score.
    """
    from flashrank import RerankRequest

    passages = [{"id": i, "text": c["text"]} for i, c in enumerate(candidates)]
    request = RerankRequest(query=query, passages=passages)
    ranked = _get_ranker().rerank(request)
    return [candidates[r["id"]] for r in ranked[:top_n]]


# ---------------------------------------------------------------------------
# RAG exemplar retrieval
# ---------------------------------------------------------------------------


def _fetch_rag_exemplars(topic: str, n: int = 5) -> list[dict]:
    """
    Fetch style exemplar fragments from Phase 1 corpus.

    1. Retrieves up to _RERANK_FETCH_N (15) candidates via cosine similarity,
       including section_type and article_type metadata.
       Prefers own_text source; falls back to all types if < 3 own-text results.
    2. Reranks candidates with FlashRank cross-encoder (ms-marco-MultiBERT-L-12).
    3. Returns top n (default 5) dicts: {text, article_type, section_type}.

    Falls back to cosine-similarity order if reranking fails.
    """
    collection = get_corpus_collection()
    if collection is None or collection.count() == 0:
        return []

    fetch_n = min(_RERANK_FETCH_N, collection.count())

    def _to_dicts(docs: list, metas: list) -> list[dict]:
        return [
            {
                "text": doc,
                "article_type": meta.get("article_type", meta.get("source_type", "")),
                "section_type": meta.get("section_type", ""),
            }
            for doc, meta in zip(docs, metas)
        ]

    # Try own_text first
    try:
        own_results = collection.query(
            query_texts=[topic],
            n_results=fetch_n,
            where={"source_type": "own"},
            include=["documents", "metadatas"],
        )
        own_docs = own_results["documents"][0] if own_results["documents"] else []
        own_metas = own_results["metadatas"][0] if own_results["metadatas"] else []
    except Exception:
        own_docs, own_metas = [], []

    candidates: list[dict]
    if len(own_docs) >= 3:
        candidates = _to_dicts(own_docs, own_metas)
    else:
        # Fall back to all source types
        try:
            all_results = collection.query(
                query_texts=[topic],
                n_results=fetch_n,
                include=["documents", "metadatas"],
            )
            all_docs = all_results["documents"][0] if all_results["documents"] else []
            all_metas = all_results["metadatas"][0] if all_results["metadatas"] else []
            candidates = _to_dicts(all_docs, all_metas)
        except Exception:
            candidates = []

    if not candidates:
        return []

    if len(candidates) <= n:
        # Nothing to rerank — fewer candidates than requested
        return candidates[:n]

    try:
        return _rerank(topic, candidates, top_n=n)
    except Exception as exc:
        log.warning("FlashRank reranking failed, using cosine order: %s", exc)
        return candidates[:n]


# ---------------------------------------------------------------------------
# Output cleanup
# ---------------------------------------------------------------------------


def _strip_thinking_tags(text: str) -> str:
    """Remove <thinking>...</thinking> blocks emitted by the LLM's reasoning step."""
    return re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL).strip()


def _strip_markdown_wrapper(text: str) -> str:
    """Strip ```markdown ... ``` or ``` ... ``` wrappers the LLM may add despite instructions."""
    text = text.strip()
    if text.startswith("```markdown"):
        text = text[len("```markdown") :].lstrip("\n")
    elif text.startswith("```"):
        text = text[3:].lstrip("\n")
    if text.endswith("```"):
        text = text[:-3].rstrip("\n")
    return text.strip()


def _clean_output(text: str) -> str:
    """Full output cleanup pipeline: strip thinking tags, then markdown wrappers."""
    return _strip_markdown_wrapper(_strip_thinking_tags(text))


# ---------------------------------------------------------------------------
# SEO + tone constraint validation
# ---------------------------------------------------------------------------


def _parse_draft_to_soup(draft: str) -> BeautifulSoup:
    """Parse Markdown draft to BeautifulSoup tree (understands fenced code blocks)."""
    html = _md.markdown(draft, extensions=["fenced_code"])
    return BeautifulSoup(html, "html.parser")


def _count_body_words(soup: BeautifulSoup) -> int:
    """Count body words, excluding heading and Meta-description nodes."""
    soup_copy = BeautifulSoup(str(soup), "html.parser")
    for tag in soup_copy.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        tag.decompose()
    for p in soup_copy.find_all("p"):
        if re.match(r"^Meta[- ]?[Dd]escription", p.get_text().strip(), re.IGNORECASE):
            p.decompose()
    return len(soup_copy.get_text().split())


def _check_forbidden_words(draft: str) -> list[str]:
    """Return list of forbidden word stems found in draft (stem = catches all inflected forms)."""
    draft_lower = draft.lower()
    return [stem for stem in FORBIDDEN_WORD_STEMS if stem in draft_lower]


def _normalize_match_text(text: str) -> str:
    """Normalize text for robust keyword matching across punctuation/casing differences."""
    normalized = re.sub(r"[^\w\s]", " ", text.lower(), flags=re.UNICODE)
    return re.sub(r"\s+", " ", normalized).strip()


def _extract_meta_description(soup: BeautifulSoup) -> str:
    """Extract the visible Meta-description line from rendered Markdown."""
    for p in soup.find_all("p"):
        paragraph = p.get_text().strip()
        match = re.match(
            r"^Meta[- ]?[Dd]escription[:\s]+(.+)", paragraph, re.IGNORECASE
        )
        if match:
            return match.group(1).strip()
    return ""


def _extract_first_body_paragraph(soup: BeautifulSoup) -> str:
    """Return the first real body paragraph, skipping the Meta-description line."""
    for p in soup.find_all("p"):
        paragraph = p.get_text().strip()
        if not paragraph:
            continue
        if re.match(r"^Meta[- ]?[Dd]escription[:\s]+", paragraph, re.IGNORECASE):
            continue
        return paragraph
    return ""


def _recommended_body_word_target(min_words: int) -> int:
    """Return a buffered target so the validator still passes after model undercount drift."""
    return min_words + _WORD_COUNT_BUFFER


def _split_markdown_blocks(text: str) -> list[str]:
    return [block.strip() for block in re.split(r"\n\s*\n", text.strip()) if block.strip()]


def _join_markdown_blocks(blocks: list[str]) -> str:
    return "\n\n".join(blocks).strip()


def _find_meta_block_index(blocks: list[str]) -> int | None:
    for index, block in enumerate(blocks):
        if re.match(r"^Meta[- ]?[Dd]escription[:\s]+", block, re.IGNORECASE):
            return index
    return None


def _find_h1_block_index(blocks: list[str]) -> int | None:
    for index, block in enumerate(blocks):
        if block.startswith("# "):
            return index
    return None


def _find_first_paragraph_block_index(blocks: list[str]) -> int | None:
    for index, block in enumerate(blocks):
        stripped = block.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        if re.match(r"^Meta[- ]?[Dd]escription[:\s]+", stripped, re.IGNORECASE):
            continue
        return index
    return None


def _normalize_inline_spacing(text: str) -> str:
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\(\s+", "(", text)
    text = re.sub(r"\s+\)", ")", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text.strip()


def _strip_redundant_heading_prefix(existing_heading: str, primary_keyword: str) -> str:
    heading_body = re.sub(r"^#\s+", "", existing_heading).strip()
    if not heading_body:
        return primary_keyword

    normalized_heading = _normalize_match_text(heading_body)
    normalized_keyword = _normalize_match_text(primary_keyword)
    if normalized_heading == normalized_keyword:
        return primary_keyword
    if normalized_heading.startswith(normalized_keyword):
        return heading_body
    return f"{primary_keyword}: {heading_body}"


def _ensure_h1_contains_keyword(markdown_text: str, primary_keyword: str) -> str:
    blocks = _split_markdown_blocks(markdown_text)
    if not blocks:
        return markdown_text

    h1_index = _find_h1_block_index(blocks)
    if h1_index is None:
        insert_at = 1 if _find_meta_block_index(blocks) == 0 else 0
        blocks.insert(insert_at, f"# {primary_keyword}")
        return _join_markdown_blocks(blocks)

    heading = blocks[h1_index]
    if primary_keyword and _normalize_match_text(primary_keyword) not in _normalize_match_text(heading):
        blocks[h1_index] = f"# {_strip_redundant_heading_prefix(heading, primary_keyword)}"
    return _join_markdown_blocks(blocks)


def _build_keyword_prefix(primary_keyword: str) -> str:
    if primary_keyword.strip().endswith("?"):
        return (
            f"{primary_keyword} Na to pytanie odpowiadają dane operacyjne, koszt wdrożenia "
            "i wyniki firm, które już pracują z tym podejściem."
        )
    return (
        f"{primary_keyword} to obszar, który warto oceniać przez liczby, proces wdrożenia "
        "i wpływ na wynik biznesowy."
    )


def _ensure_first_paragraph_contains_keyword(markdown_text: str, primary_keyword: str) -> str:
    blocks = _split_markdown_blocks(markdown_text)
    if not blocks or not primary_keyword:
        return markdown_text

    paragraph_index = _find_first_paragraph_block_index(blocks)
    if paragraph_index is None:
        return markdown_text

    paragraph = blocks[paragraph_index]
    if _normalize_match_text(primary_keyword) in _normalize_match_text(paragraph):
        return markdown_text

    blocks[paragraph_index] = _normalize_inline_spacing(
        f"{_build_keyword_prefix(primary_keyword)} {paragraph}"
    )
    return _join_markdown_blocks(blocks)


def _truncate_to_word_boundary(text: str, max_length: int) -> str:
    candidate = text.strip()
    if len(candidate) <= max_length:
        return candidate

    truncated = candidate[: max_length + 1]
    if " " in truncated:
        truncated = truncated[: truncated.rfind(" ")]
    return truncated.rstrip(" ,;:-")


def _extend_text_to_min_length(text: str, filler: str, min_length: int, max_length: int) -> str:
    candidate = text.strip()
    filler_words = filler.split()
    index = 0
    while len(candidate) < min_length and index < len(filler_words):
        next_candidate = f"{candidate} {filler_words[index]}".strip()
        if len(next_candidate) > max_length:
            break
        candidate = next_candidate
        index += 1
    return candidate


def _ensure_meta_description_length(markdown_text: str) -> str:
    blocks = _split_markdown_blocks(markdown_text)
    if not blocks:
        return markdown_text

    meta_index = _find_meta_block_index(blocks)
    paragraph_index = _find_first_paragraph_block_index(blocks)
    first_paragraph = blocks[paragraph_index] if paragraph_index is not None else ""

    if meta_index is None:
        meta_index = 0
        blocks.insert(0, "Meta-description: ")

    existing_meta = re.sub(
        r"^Meta[- ]?[Dd]escription[:\s]+", "", blocks[meta_index], flags=re.IGNORECASE
    ).strip()
    supplemental = _normalize_inline_spacing(first_paragraph)
    candidate = existing_meta or supplemental
    if not candidate:
        return markdown_text

    if len(candidate) < _META_DESCRIPTION_MIN_LENGTH and supplemental:
        extra_source = supplemental
        if extra_source.startswith(candidate):
            extra_source = extra_source[len(candidate) :].strip()
        candidate = _extend_text_to_min_length(
            candidate,
            extra_source,
            _META_DESCRIPTION_MIN_LENGTH,
            _META_DESCRIPTION_MAX_LENGTH,
        )

    if len(candidate) < _META_DESCRIPTION_MIN_LENGTH:
        candidate = _extend_text_to_min_length(
            candidate,
            "dla zespołów, które liczą koszt, wynik i tempo wdrożenia.",
            _META_DESCRIPTION_MIN_LENGTH,
            _META_DESCRIPTION_MAX_LENGTH,
        )

    candidate = _truncate_to_word_boundary(candidate, _META_DESCRIPTION_MAX_LENGTH)
    if len(candidate) < _META_DESCRIPTION_MIN_LENGTH and supplemental:
        candidate = _truncate_to_word_boundary(
            _extend_text_to_min_length(
                candidate,
                supplemental,
                _META_DESCRIPTION_MIN_LENGTH,
                _META_DESCRIPTION_MAX_LENGTH,
            ),
            _META_DESCRIPTION_MAX_LENGTH,
        )

    blocks[meta_index] = f"Meta-description: {candidate}"
    return _join_markdown_blocks(blocks)


def _remove_forbidden_words(markdown_text: str) -> str:
    repaired = markdown_text
    for stem in FORBIDDEN_WORD_STEMS:
        repaired = re.sub(
            rf"(?iu)\b\w*{re.escape(stem)}\w*\b",
            "",
            repaired,
        )

    lines = [_normalize_inline_spacing(line) if line.strip() else "" for line in repaired.splitlines()]
    return "\n".join(lines).strip()


def _lookup_research_items(
    research_data: dict[str, Any] | Any | None,
    key: str,
) -> list[str]:
    if research_data is None:
        return []
    if isinstance(research_data, dict):
        value = research_data.get(key, [])
    else:
        value = getattr(research_data, key, [])
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _extract_research_sentences(
    research_data: dict[str, Any] | Any | None,
    draft: str,
) -> list[str]:
    normalized_draft = _normalize_match_text(draft)
    unique_sentences: list[str] = []
    seen: set[str] = set()

    for item in _lookup_research_items(research_data, "fakty") + _lookup_research_items(
        research_data, "statystyki"
    ):
        sentence = _normalize_inline_spacing(item.strip(" -*"))
        if not sentence:
            continue
        if sentence[-1] not in ".!?":
            sentence += "."
        normalized_sentence = _normalize_match_text(sentence)
        if normalized_sentence in seen or normalized_sentence in normalized_draft:
            continue
        seen.add(normalized_sentence)
        unique_sentences.append(sentence)
    return unique_sentences


def _build_fallback_extension_paragraph(index: int) -> str:
    fallback_paragraphs = [
        (
            "W praktyce o skuteczności wdrożenia decydują jakość danych wejściowych, "
            "jasny podział odpowiedzialności i regularny przegląd wyników na poziomie procesu. "
            "Dopiero takie połączenie pozwala powiązać decyzje operacyjne z kosztem, czasem realizacji "
            "i jakością efektu końcowego."
        ),
        (
            "Równie ważne jest ustalenie mierników, które pokazują nie tylko wynik pilotażu, "
            "ale też trwałość efektu po wdrożeniu. Bez tego zespół nie odróżni pojedynczej poprawy "
            "od realnej zmiany, którą da się utrzymać przy większej skali działania."
        ),
        (
            "Dlatego końcowa decyzja powinna łączyć analizę liczb z oceną ograniczeń organizacyjnych, "
            "ryzyk wdrożenia i wpływu na codzienny rytm pracy. Taka perspektywa ogranicza koszt błędów "
            "i ułatwia obronę inwestycji przed interesariuszami."
        ),
    ]
    return fallback_paragraphs[index % len(fallback_paragraphs)]


def _build_word_count_extension_paragraphs(
    draft: str,
    research_data: dict[str, Any] | Any | None,
    min_words: int,
) -> list[str]:
    current_word_count = _count_body_words(_parse_draft_to_soup(draft))
    target_word_count = min_words + 30
    word_shortfall = max(target_word_count - current_word_count, 0)
    if word_shortfall <= 0:
        return []

    sentences = _extract_research_sentences(research_data, draft)
    paragraphs: list[str] = []
    cursor = 0
    added_words = 0

    intros = [
        (
            "W praktyce o jakości wdrożenia decydują trzy elementy: jakość danych wejściowych, "
            "tempo podejmowania decyzji i sposób mierzenia efektu biznesowego."
        ),
        (
            "Na etapie skalowania rozwiązania warto zestawić twarde dane z wpływem na harmonogram, "
            "budżet i odpowiedzialność zespołu za wynik."
        ),
        (
            "Dla zespołu operacyjnego kluczowe jest to, czy dane potwierdzają poprawę procesu, "
            "a nie tylko pojedynczy sukces pilotażu."
        ),
    ]
    closers = [
        (
            "Takie ujęcie porządkuje decyzję wdrożeniową i pozwala ocenić, czy efekt utrzyma się "
            "poza pierwszą fazą projektu."
        ),
        (
            "Dopiero na tej podstawie da się realnie porównać koszt wdrożenia z wpływem na jakość, "
            "czas i przewidywalność procesu."
        ),
    ]

    while added_words < word_shortfall:
        paragraph_parts = [intros[len(paragraphs) % len(intros)]]
        while cursor < len(sentences) and len(" ".join(paragraph_parts).split()) < 85:
            paragraph_parts.append(sentences[cursor])
            cursor += 1

        if len(paragraph_parts) == 1:
            paragraph_parts.append(_build_fallback_extension_paragraph(len(paragraphs)))
        else:
            paragraph_parts.append(closers[len(paragraphs) % len(closers)])

        paragraph = _normalize_inline_spacing(" ".join(paragraph_parts))
        paragraphs.append(paragraph)
        added_words += len(paragraph.split())

        if cursor >= len(sentences) and added_words < word_shortfall:
            paragraphs.append(_build_fallback_extension_paragraph(len(paragraphs)))
            added_words = sum(len(item.split()) for item in paragraphs)

    return paragraphs


def _expand_draft_to_min_words(
    markdown_text: str,
    research_data: dict[str, Any] | Any | None,
    min_words: int,
) -> str:
    extra_paragraphs = _build_word_count_extension_paragraphs(
        markdown_text, research_data, min_words
    )
    if not extra_paragraphs:
        return markdown_text

    blocks = _split_markdown_blocks(markdown_text)
    blocks.extend(extra_paragraphs)
    return _join_markdown_blocks(blocks)


def _apply_validation_repairs(
    draft: str,
    validation: DraftValidationDetails,
    *,
    primary_keyword: str,
    min_words: int,
    research_data: dict[str, Any] | Any | None,
    allow_word_count_expansion: bool,
) -> str:
    repaired = draft
    failure_codes = set(validation.get("failure_codes", []))

    if "keyword_in_h1" in failure_codes:
        repaired = _ensure_h1_contains_keyword(repaired, primary_keyword)
    if "keyword_in_first_para" in failure_codes:
        repaired = _ensure_first_paragraph_contains_keyword(repaired, primary_keyword)
    if "no_forbidden_words" in failure_codes:
        repaired = _remove_forbidden_words(repaired)
    if "meta_desc_length_ok" in failure_codes:
        repaired = _ensure_meta_description_length(repaired)
    if allow_word_count_expansion and "word_count_ok" in failure_codes:
        repaired = _expand_draft_to_min_words(repaired, research_data, min_words)
        repaired = _remove_forbidden_words(repaired)
        repaired = _ensure_meta_description_length(repaired)

    return repaired


def _validate_draft(
    draft: str, primary_keyword: str, min_words: int
) -> DraftValidationDetails:
    """Check hard constraints and return a structured validation report."""
    soup = _parse_draft_to_soup(draft)

    h1 = soup.find("h1")
    h1_text = h1.get_text().strip() if h1 else ""
    first_para = _extract_first_body_paragraph(soup)
    meta_desc = _extract_meta_description(soup)

    normalized_primary_keyword = _normalize_match_text(primary_keyword)
    body_word_count = _count_body_words(soup)
    forbidden_stems = _check_forbidden_words(draft)
    meta_description_length = len(meta_desc)

    checks: DraftValidationChecks = {
        "keyword_in_h1": bool(
            h1_text
            and normalized_primary_keyword
            and normalized_primary_keyword in _normalize_match_text(h1_text)
        ),
        "keyword_in_first_para": bool(
            first_para
            and normalized_primary_keyword
            and normalized_primary_keyword in _normalize_match_text(first_para)
        ),
        "meta_desc_length_ok": (
            _META_DESCRIPTION_MIN_LENGTH
            <= meta_description_length
            <= _META_DESCRIPTION_MAX_LENGTH
        ),
        "word_count_ok": body_word_count >= min_words,
        "no_forbidden_words": len(forbidden_stems) == 0,
    }
    failure_codes = [code for code, passed in checks.items() if not passed]
    failures: list[DraftValidationFailure] = []

    if not checks["keyword_in_h1"]:
        failures.append(
            {
                "code": "keyword_in_h1",
                "message": (
                    f'H1 musi zawierać główne słowo kluczowe "{primary_keyword}".'
                ),
            }
        )
    if not checks["keyword_in_first_para"]:
        failures.append(
            {
                "code": "keyword_in_first_para",
                "message": (
                    f'Pierwszy akapit musi zawierać główne słowo kluczowe "{primary_keyword}".'
                ),
            }
        )
    if not checks["meta_desc_length_ok"]:
        failures.append(
            {
                "code": "meta_desc_length_ok",
                "message": (
                    "Meta-description musi mieć 150-160 znaków; "
                    f"obecnie ma {meta_description_length}."
                ),
            }
        )
    if not checks["word_count_ok"]:
        failures.append(
            {
                "code": "word_count_ok",
                "message": (
                    f"Treść artykułu ma {body_word_count} słów; wymagane minimum to {min_words}."
                ),
            }
        )
    if not checks["no_forbidden_words"]:
        failures.append(
            {
                "code": "no_forbidden_words",
                "message": (
                    "Usuń niedozwolone rdzenie słów: "
                    + ", ".join(forbidden_stems)
                    + "."
                ),
            }
        )

    return {
        "passed": len(failure_codes) == 0,
        "checks": checks,
        "failure_codes": failure_codes,
        "failures": failures,
        "primary_keyword": primary_keyword,
        "body_word_count": body_word_count,
        "min_words": min_words,
        "meta_description_length": meta_description_length,
        "meta_description_min_length": _META_DESCRIPTION_MIN_LENGTH,
        "meta_description_max_length": _META_DESCRIPTION_MAX_LENGTH,
        "forbidden_stems": forbidden_stems,
        "attempt_count": 0,
        "attempts": [],
    }


def _build_validation_repair_guidance(validation: DraftValidationDetails) -> str:
    """Translate failed validator checks into concrete repair actions for the writer model."""
    guidance: list[str] = []
    failure_codes = set(validation.get("failure_codes", []))
    primary_keyword = validation["primary_keyword"]

    if "keyword_in_h1" in failure_codes:
        guidance.append(
            f'- W nagłówku H1 umieść dokładny ciąg "{primary_keyword}" i nie parafrazuj tej frazy.'
        )
    if "keyword_in_first_para" in failure_codes:
        guidance.append(
            f'- W pierwszym akapicie użyj dokładnego ciągu "{primary_keyword}" naturalnie, bez cudzysłowów i bez frazy "główne słowo kluczowe".'
        )
    if "meta_desc_length_ok" in failure_codes:
        guidance.append(
            "- Przepisz linię `Meta-description:` tak, aby miała 150-160 znaków ze spacjami; celuj w 155 znaków i zachowaj tylko jedną taką linię."
        )
    if "word_count_ok" in failure_codes:
        min_words = validation["min_words"]
        body_word_count = validation["body_word_count"]
        shortfall = max(min_words - body_word_count, 0)
        target_words = max(
            _recommended_body_word_target(min_words),
            body_word_count + max(shortfall, _WORD_COUNT_BUFFER),
        )
        guidance.append(
            "- Rozbuduj istniejące sekcje merytorycznie, bez zmiany sensu i bez lania wody: "
            f"obecnie treść ma {body_word_count} słów, minimum to {min_words}, więc po poprawce celuj w co najmniej {target_words} słów treści głównej."
        )
        guidance.append(
            "- Dodaj konkretne dane, przykłady, skutki wdrożenia, ryzyka albo kryteria decyzyjne w już istniejących sekcjach zamiast dopisywać meta-komentarze o artykule."
        )
    if "no_forbidden_words" in failure_codes:
        forbidden_stems = ", ".join(validation.get("forbidden_stems", []))
        guidance.append(
            f"- Usuń wszystkie niedozwolone rdzenie słów ({forbidden_stems}) i zastąp je faktami, liczbami albo precyzyjnym opisem zjawiska."
        )

    return "\n".join(guidance)


def _build_revision_instructions(
    validation: DraftValidationDetails,
    cp2_feedback: str | None,
) -> tuple[str, Literal["validation", "user_and_validation"]]:
    failure_list = "\n".join(
        f"- {failure['message']}" for failure in validation.get("failures", [])
    )
    repair_guidance = _build_validation_repair_guidance(validation)

    if cp2_feedback:
        return (
            f"""Priorytet 1 — uwzględnij feedback użytkownika:
{cp2_feedback}

Priorytet 2 — finalny artykuł musi też spełnić wszystkie poniższe wymagania SEO:
{failure_list}

Instrukcje naprawcze:
{repair_guidance}""",
            "user_and_validation",
        )

    return (
        f"""Napraw obecny draft tak, aby spełnił wszystkie poniższe wymagania SEO:
{failure_list}

Instrukcje naprawcze:
{repair_guidance}""",
        "validation",
    )


# ---------------------------------------------------------------------------
# Prompt builder (user message only — system prompt is in bond/prompts/writer.py)
# ---------------------------------------------------------------------------


def _format_exemplar(ex: dict) -> str:
    """Render a single exemplar dict as a labelled few-shot block."""
    article_type = ex.get("article_type") or "?"
    section_type = ex.get("section_type") or "?"
    label = f"[Typ: {article_type} | Sekcja: {section_type}]"
    return f"{label}\n{ex['text']}"


def _build_writer_user_prompt(
    topic: str,
    keywords: list[str],
    heading_structure: str,
    research_context: str,
    exemplars: list[dict],
    min_words: int,
    context_block: str = "",
    revision_instructions: Optional[str] = None,
    current_draft: Optional[str] = None,
    revision_source: Literal["user", "validation", "user_and_validation"] | None = None,
) -> str:
    """Build the user message for the writer LLM. System directives live in WRITER_SYSTEM_PROMPT."""
    primary_keyword = keywords[0] if keywords else topic
    other_keywords = ", ".join(keywords[1:]) if len(keywords) > 1 else "brak"
    target_words = _recommended_body_word_target(min_words)
    max_target_words = target_words + 180

    exemplar_section = ""
    if exemplars:
        formatted = "\n\n---\n\n".join(_format_exemplar(e) for e in exemplars[:5])
        exemplar_section = f"""
## WZORCE STYLISTYCZNE (Few-Shot)
Poniższe fragmenty pochodzą z korpusu stylistycznego. Każdy opatrzony jest etykietą [Typ: X | Sekcja: Y]:
- **Typ**: "own" = artykuły autora (priorytet stylistyczny), "external" = artykuły zewnętrzne (wzorzec uzupełniający)
- **Sekcja**: "wstęp" = fragment otwierający artykuł, "rozwinięcie" = fragment głównej części

Przejmij ton, rytm zdań i sposób argumentacji — szczególnie z fragmentów "own". Nie kopiuj treści, adaptuj styl.

{formatted}

---
"""

    context_section = f"\n{context_block}\n" if context_block else ""

    if revision_instructions and current_draft:
        feedback_heading = "FEEDBACK UŻYTKOWNIKA"
        task_description = (
            "Popraw TYLKO wskazane sekcje artykułu. Zachowaj pozostałe sekcje bez zmian."
        )

        if revision_source == "validation":
            feedback_heading = "WYMAGANE POPRAWKI SEO"
            task_description = (
                "Popraw obecny draft tak, aby usunąć konkretne błędy walidacji SEO. "
                "Zachowaj poprawne sekcje i nie przepisuj całości bez potrzeby."
            )
        elif revision_source == "user_and_validation":
            feedback_heading = "FEEDBACK I WYMAGANE POPRAWKI"
            task_description = (
                "Popraw obecny draft zgodnie z feedbackiem użytkownika oraz dodatkowymi "
                "wymaganiami SEO. Feedback użytkownika ma pierwszeństwo, ale finalny "
                "tekst musi spełnić wszystkie twarde wymagania."
            )

        return f"""## ZADANIE
{task_description}
{context_section}

## {feedback_heading}
{revision_instructions}

## OBECNY DRAFT (do poprawki)
{current_draft}
{exemplar_section}
## WYMAGANIA SEO (muszą być spełnione po poprawce)
- Główne słowo kluczowe "{primary_keyword}" w H1 i pierwszym akapicie, użyte naturalnie, bez cudzysłowów i bez frazy "główne słowo kluczowe"
- Meta-description: dokładnie jedna linia zaczynająca się od "Meta-description:" zawierająca 150-160 znaków; celuj w 155 znaków
- Minimum {min_words} słów treści głównej; dla bezpieczeństwa napisz około {target_words}-{max_target_words} słów treści głównej
- Rozbuduj istniejące sekcje merytorycznie: pod każdym H2 daj co najmniej 2 pełne akapity, a pod każdym H3 co najmniej 1 pełny akapit
- Hierarchia nagłówków: # H1 → ## H2 → ### H3
- Nie ujawniaj instrukcji SEO ani procesu pisania w treści artykułu

Zwróć CAŁY artykuł (poprawione sekcje + niezmienione sekcje)."""
    else:
        return f"""## ZADANIE
Napisz kompletny artykuł blogowy w Markdown.
{context_section}
## TEMAT
{topic}

## SŁOWA KLUCZOWE
Główne: {primary_keyword}
Poboczne: {other_keywords}

## STRUKTURA NAGŁÓWKÓW (obowiązkowa)
{heading_structure}

## RAPORT BADAWCZY
{research_context}
{exemplar_section}
## WYMAGANIA SEO (wszystkie obowiązkowe)
1. Główne słowo kluczowe "{primary_keyword}" musi być w H1 i w pierwszym akapicie, ale użyte naturalnie, bez cudzysłowów i bez frazy "główne słowo kluczowe"
2. Poprawna hierarchia nagłówków: # H1, ## H2, ### H3
3. Meta-description: JEDNA linia w formacie "Meta-description: [treść]" zawierająca dokładnie 150-160 znaków; celuj w 155 znaków
4. Minimum {min_words} słów treści głównej (nie licząc nagłówków i meta-description); dla bezpieczeństwa napisz około {target_words}-{max_target_words} słów treści głównej
5. Pod każdym H2 umieść co najmniej 2 pełne, merytoryczne akapity; pod każdym H3 co najmniej 1 pełny akapit
6. Naturalne wplecenie słów kluczowych (bez keyword stuffing i bez komentarzy o SEO wewnątrz artykułu)"""


# ---------------------------------------------------------------------------
# Writer node
# ---------------------------------------------------------------------------


async def writer_node(state: AuthorState) -> dict:
    """
    Generate SEO-compliant draft with RAG style injection and Tone of Voice enforcement.

    Before generation:
    - Checks RAG corpus count. If < settings.low_corpus_threshold, interrupts with
      a standard approve/reject warning payload and waits for user confirmation.

    After corpus check:
    - Auto-retries up to 2 times if hard constraints fail (SEO or forbidden words).
    - On cp2_feedback: targeted section revision (preserves unchanged sections).
    """
    topic = state["topic"]
    keywords = state.get("keywords", [])
    primary_keyword = keywords[0] if keywords else topic
    heading_structure = state.get("heading_structure", "")
    research_report = state.get("research_report", "")
    research_data = state.get("research_data")
    cp2_feedback = state.get("cp2_feedback")
    current_draft = state.get("draft")  # for targeted revision
    min_words = settings.min_word_count

    # --- Low corpus gate ---
    corpus_count = get_article_count()
    if corpus_count < settings.low_corpus_threshold:
        warning_message = (
            f"Korpus zawiera tylko {corpus_count} artykułów "
            f"(minimum: {settings.low_corpus_threshold}). Styl draftu może być niespójny."
        )
        user_response = interrupt(
            {
                "checkpoint": "low_corpus",
                "type": "approve_reject",
                "warning": warning_message,
                "corpus_count": corpus_count,
                "threshold": settings.low_corpus_threshold,
                "instructions": (
                    'Wyślij {"action": "approve"}, {"action": "reject"} '
                    'lub {"action": "abort"} aby zdecydować o kontynuacji.'
                ),
            }
        )
        try:
            response = CheckpointResponse(**user_response)
        except ValidationError as exc:
            raise ValueError(f"Nieprawidłowa odpowiedź low_corpus: {exc}") from exc

        if response.action != "approve":
            return Command(
                goto=END,
                update={
                    "draft": "",
                    "draft_validated": False,
                    "draft_validation_details": None,
                },
            )

    # Select DRAFT_MODEL LLM (temperature 0.5–0.7 per COMMUNICATION_STYLE.md §3)
    llm = get_draft_llm(max_tokens=_WRITER_MAX_OUTPUT_TOKENS, temperature=0.7)

    # Fetch RAG exemplars from Phase 1 corpus
    exemplars = _fetch_rag_exemplars(topic, n=5)
    context_block = build_context_block(state.get("context_dynamic"))
    research_context_selection = select_research_context(
        llm=llm,
        research_report=research_report,
        research_data=state.get("research_data"),
        build_prompt_payload=lambda research_context: [
            SystemMessage(content=WRITER_SYSTEM_PROMPT),
            HumanMessage(
                content=_build_writer_user_prompt(
                    topic=topic,
                    keywords=keywords,
                    heading_structure=heading_structure,
                    research_context=research_context,
                    exemplars=exemplars,
                    min_words=min_words,
                    context_block=context_block,
                )
            ),
        ],
        reserved_output_tokens=_WRITER_MAX_OUTPUT_TOKENS,
    )
    research_context = research_context_selection.variant.content
    if not research_context_selection.fit_found:
        log.warning(
            "Writer prompt exceeded available input budget even after compaction: %s > %s (variant=%s)",
            research_context_selection.estimated_prompt_tokens,
            research_context_selection.available_input_tokens,
            research_context_selection.variant.kind,
        )

    # Generate draft with silent auto-retry (max 2 additional attempts = 3 total)
    draft = ""
    validation: DraftValidationDetails = {
        "passed": False,
        "checks": {
            "keyword_in_h1": False,
            "keyword_in_first_para": False,
            "meta_desc_length_ok": False,
            "word_count_ok": False,
            "no_forbidden_words": False,
        },
        "failure_codes": [],
        "failures": [],
        "primary_keyword": primary_keyword,
        "body_word_count": 0,
        "min_words": min_words,
        "meta_description_length": 0,
        "meta_description_min_length": _META_DESCRIPTION_MIN_LENGTH,
        "meta_description_max_length": _META_DESCRIPTION_MAX_LENGTH,
        "forbidden_stems": [],
        "attempt_count": 0,
        "attempts": [],
    }
    max_attempts = 3
    total_draft_input_tokens = 0
    total_draft_output_tokens = 0
    attempt_summaries: list[DraftValidationAttempt] = []
    for attempt in range(max_attempts):
        revision_instructions = None
        revision_source: Literal["user", "validation", "user_and_validation"] | None = None
        revision_draft = None

        if attempt == 0 and cp2_feedback and current_draft:
            revision_instructions = cp2_feedback
            revision_source = "user"
            revision_draft = current_draft
        elif attempt > 0 and draft:
            revision_instructions, revision_source = _build_revision_instructions(
                validation,
                cp2_feedback,
            )
            revision_draft = draft

        user_prompt = _build_writer_user_prompt(
            topic=topic,
            keywords=keywords,
            heading_structure=heading_structure,
            research_context=research_context,
            exemplars=exemplars,
            min_words=min_words,
            context_block=context_block,
            revision_instructions=revision_instructions,
            current_draft=revision_draft,
            revision_source=revision_source,
        )
        messages = [
            SystemMessage(content=WRITER_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]
        response = await llm.ainvoke(messages)
        draft = _clean_output(response.content)

        usage = response.usage_metadata or {}
        total_draft_input_tokens += usage.get("input_tokens", 0)
        total_draft_output_tokens += usage.get("output_tokens", 0)

        validation = _validate_draft(draft, primary_keyword, min_words)
        repaired_draft = _apply_validation_repairs(
            draft,
            validation,
            primary_keyword=primary_keyword,
            min_words=min_words,
            research_data=research_data,
            allow_word_count_expansion=attempt == max_attempts - 1,
        )
        if repaired_draft != draft:
            draft = repaired_draft
            validation = _validate_draft(draft, primary_keyword, min_words)

        attempt_summaries.append(
            {
                "attempt_number": attempt + 1,
                "passed": validation["passed"],
                "failed_codes": list(validation["failure_codes"]),
            }
        )
        validation["attempt_count"] = len(attempt_summaries)
        validation["attempts"] = list(attempt_summaries)

        if validation["passed"]:
            break

        if attempt < max_attempts - 1:
            log.warning(
                "Writer auto-retry %d/%d: failed constraints: %s",
                attempt + 1,
                max_attempts - 1,
                validation["failure_codes"],
            )

    # All retries exhausted (or succeeded above)
    if not validation["passed"]:
        log.warning(
            "Draft failed validation after %d attempts. Failed: %s",
            max_attempts,
            validation["failure_codes"],
        )

    call_cost = estimate_cost_usd(
        settings.draft_model, total_draft_input_tokens, total_draft_output_tokens
    )
    existing_draft_tokens = state.get("tokens_used_draft", 0)
    existing_cost = state.get("estimated_cost_usd", 0.0)

    return {
        "draft": draft,
        "draft_validated": validation["passed"],
        "draft_validation_details": validation,
        "tokens_used_draft": existing_draft_tokens
        + total_draft_input_tokens
        + total_draft_output_tokens,
        "estimated_cost_usd": existing_cost + call_cost,
    }
