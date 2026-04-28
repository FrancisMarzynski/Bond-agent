import pytest

from bond.db import metadata_log
from bond.graph.nodes.save_metadata import save_metadata_node


@pytest.fixture
def temp_metadata_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test_metadata.db")
    monkeypatch.setattr(
        "bond.db.metadata_log.settings",
        type("S", (), {"metadata_db_path": db_path})(),
    )
    return db_path


@pytest.mark.asyncio
async def test_save_metadata_node_persists_sqlite_and_chroma(temp_metadata_db, monkeypatch):
    captured: dict[str, str] = {}

    def fake_add_topic_to_metadata_collection(thread_id: str, topic: str, published_date: str) -> None:
        captured["thread_id"] = thread_id
        captured["topic"] = topic
        captured["published_date"] = published_date

    monkeypatch.setattr(
        "bond.graph.nodes.save_metadata.add_topic_to_metadata_collection",
        fake_add_topic_to_metadata_collection,
    )

    result = await save_metadata_node(
        {
            "topic": "Jak budowac korpus redakcyjny",
            "thread_id": "thread-happy",
            "tokens_used_research": 120,
            "tokens_used_draft": 240,
            "estimated_cost_usd": 1.25,
        }
    )

    assert result == {"metadata_saved": True}
    articles = await metadata_log.get_recent_articles(limit=10)
    assert len(articles) == 1
    assert articles[0]["thread_id"] == "thread-happy"
    assert articles[0]["topic"] == "Jak budowac korpus redakcyjny"
    assert articles[0]["tokens_used_research"] == 120
    assert articles[0]["tokens_used_draft"] == 240
    assert articles[0]["estimated_cost_usd"] == 1.25
    assert captured["thread_id"] == "thread-happy"
    assert captured["topic"] == "Jak budowac korpus redakcyjny"
    assert captured["published_date"]


@pytest.mark.asyncio
async def test_save_metadata_node_rolls_back_sqlite_when_chroma_write_fails(temp_metadata_db, monkeypatch):
    def failing_add_topic_to_metadata_collection(thread_id: str, topic: str, published_date: str) -> None:
        raise RuntimeError("Chroma add failed")

    monkeypatch.setattr(
        "bond.graph.nodes.save_metadata.add_topic_to_metadata_collection",
        failing_add_topic_to_metadata_collection,
    )

    with pytest.raises(RuntimeError, match="Chroma add failed"):
        await save_metadata_node(
            {
                "topic": "Temat rollbacku",
                "thread_id": "thread-rollback",
            }
        )

    articles = await metadata_log.get_recent_articles(limit=10)
    assert articles == []
