"""
bond/harness.py — CLI test harness for Author mode pipeline

Usage:
    # Approve-all smoke test (new session)
    python -m bond.harness

    # Interactive mode (prompts at each checkpoint)
    python -m bond.harness --interactive

    # Resume interrupted session
    python -m bond.harness --resume --thread-id <uuid>

    # Custom topic
    python -m bond.harness --topic "Marketing treści dla SaaS" --keywords "content marketing,SEO,blog"
"""

import argparse
import asyncio
import uuid
from typing import Optional

from dotenv import load_dotenv

load_dotenv()  # Must be before bond.graph imports so env vars are available

from langgraph.types import Command

from bond.graph.graph import compile_graph


def _handle_interrupt(result: dict, interactive: bool) -> dict:
    """
    Extract interrupt payload from graph result and determine resume value.

    Returns the value to pass to Command(resume=...).
    """
    interrupts = result.get("__interrupt__", [])
    if not interrupts:
        return {}

    interrupt_data = interrupts[0].value if hasattr(interrupts[0], "value") else interrupts[0]
    checkpoint = interrupt_data.get("checkpoint", "unknown")

    print(f"\n{'='*60}")
    print(f"CHECKPOINT: {checkpoint.upper()}")
    print(f"{'='*60}")

    if checkpoint == "checkpoint_1":
        print("\n[RAPORT Z BADAŃ]")
        print(interrupt_data.get("research_report", "")[:500] + "...")
        print("\n[PROPONOWANA STRUKTURA NAGŁÓWKÓW]")
        print(interrupt_data.get("heading_structure", ""))
        print(f"\nIteracja: {interrupt_data.get('cp1_iterations', 0)}")

        if not interactive:
            print("\n[AUTO] Zatwierdzam strukturę nagłówków.")
            return {"approved": True}

        user_input = input("\nZatwierdź? [t/n]: ").strip().lower()
        if user_input == "t":
            return {"approved": True}
        edited = input("Wklej edytowaną strukturę nagłówków (lub Enter aby zachować obecną):\n")
        note = input("Opcjonalna notatka dla agenta:\n")
        return {
            "approved": False,
            "edited_structure": edited or interrupt_data.get("heading_structure", ""),
            "note": note,
        }

    elif checkpoint == "checkpoint_2":
        print("\n[DRAFT ARTYKUŁU]")
        print(interrupt_data.get("draft", "")[:800] + "\n[... draft skrócony do 800 znaków ...]")
        print(f"\nWalidacja SEO: {interrupt_data.get('draft_validated', 'n/a')}")
        print(f"Iteracja: {interrupt_data.get('cp2_iterations', 0)}")
        if interrupt_data.get("warning"):
            print(f"OSTRZEŻENIE: {interrupt_data['warning']}")

        if not interactive:
            print("\n[AUTO] Zatwierdzam draft.")
            return {"approved": True}

        user_input = input("\nZatwierdź? [t/n]: ").strip().lower()
        if user_input == "t":
            return {"approved": True}
        feedback = input("Opisz które sekcje poprawić i jak:\n")
        return {"approved": False, "feedback": feedback}

    elif "warning" in interrupt_data:
        # Duplicate detection or low-corpus checkpoint
        print(f"\n[OSTRZEŻENIE] {interrupt_data.get('warning')}")
        if interrupt_data.get("existing_title"):
            print(f"Istniejący artykuł: {interrupt_data.get('existing_title')}")
            print(f"Data publikacji: {interrupt_data.get('existing_date')}")
            print(f"Podobieństwo: {interrupt_data.get('similarity_score')}")
        if interrupt_data.get("corpus_count") is not None:
            print(f"Artykułów w korpusie: {interrupt_data.get('corpus_count')} (próg: {interrupt_data.get('threshold')})")

        if not interactive:
            print("\n[AUTO] Kontynuuję.")
            return True

        user_input = input("\nKontynuować? [t/n]: ").strip().lower()
        return user_input == "t"

    return {"approved": True}  # fallback


async def run_author_pipeline(
    topic: str = "Jak zwiększyć ruch na blogu firmowym",
    keywords: Optional[list[str]] = None,
    thread_id: Optional[str] = None,
    interactive: bool = False,
    resume: bool = False,
) -> dict:
    """
    Run the Author mode pipeline end-to-end.

    Args:
        topic: Article topic
        keywords: List of SEO keywords (first is primary)
        thread_id: Existing thread ID for resume; generates new UUID if None
        interactive: If True, prompts user at each checkpoint; if False, auto-approves
        resume: If True, resumes from existing thread_id state

    Returns:
        Final graph state dict
    """
    if keywords is None:
        keywords = ["content marketing", "blog"]

    if thread_id is None:
        thread_id = str(uuid.uuid4())

    config = {"configurable": {"thread_id": thread_id}}
    graph = compile_graph()

    print(f"\nAuthor Mode Pipeline")
    print(f"Topic: {topic}")
    print(f"Keywords: {keywords}")
    print(f"Thread ID: {thread_id}")
    print(f"Mode: {'Interactive' if interactive else 'Auto-approve'}")
    print(f"{'Resume' if resume else 'Fresh run'}")

    if resume:
        print("\nResuming from last checkpoint...")
        result = await graph.ainvoke(Command(resume={"approved": True}), config=config)
    else:
        initial_state = {
            "topic": topic,
            "keywords": keywords,
            "thread_id": thread_id,
            "search_cache": {},
            "cp1_iterations": 0,
            "cp2_iterations": 0,
            "metadata_saved": False,
            "duplicate_match": None,
            "duplicate_override": None,
            "research_report": None,
            "heading_structure": None,
            "cp1_approved": None,
            "cp1_feedback": None,
            "draft": None,
            "draft_validated": None,
            "cp2_approved": None,
            "cp2_feedback": None,
        }
        result = await graph.ainvoke(initial_state, config=config)

    # Handle interrupt chain — loop until graph finishes or exits
    max_interrupts = 20  # safety limit
    interrupt_count = 0
    while result.get("__interrupt__") and interrupt_count < max_interrupts:
        resume_value = _handle_interrupt(result, interactive)
        result = await graph.ainvoke(Command(resume=resume_value), config=config)
        interrupt_count += 1

    # Final state
    print(f"\n{'='*60}")
    print("PIPELINE COMPLETE")
    print(f"{'='*60}")
    print(f"Metadata saved: {result.get('metadata_saved', False)}")
    if result.get("draft"):
        word_count = len(result["draft"].split())
        print(f"Draft word count: {word_count}")
        print(f"Draft validated: {result.get('draft_validated')}")
        print(f"\nDraft preview (first 300 chars):\n{result['draft'][:300]}...")

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bond Author Mode test harness")
    parser.add_argument("--topic", default="Jak zwiększyć ruch na blogu firmowym")
    parser.add_argument("--keywords", default="SEO blog,content marketing,ruch organiczny")
    parser.add_argument("--thread-id", default=None)
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    keywords = [k.strip() for k in args.keywords.split(",")]
    asyncio.run(run_author_pipeline(
        topic=args.topic,
        keywords=keywords,
        thread_id=args.thread_id,
        interactive=args.interactive,
        resume=args.resume,
    ))
