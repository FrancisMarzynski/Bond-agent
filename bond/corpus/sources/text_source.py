from bond.corpus.ingestor import CorpusIngestor


def ingest_text(text: str, source_type: str, title: str = "Wklejony tekst") -> dict:
    ingestor = CorpusIngestor()
    return ingestor.ingest(text=text, title=title, source_type=source_type)
