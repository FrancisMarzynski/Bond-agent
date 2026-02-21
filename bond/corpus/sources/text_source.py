from bond.corpus.ingestor import CorpusIngestor

def ingest_text(text: str, source_type: str, title: str = "Pasted text") -> dict:
    ingestor = CorpusIngestor()
    return ingestor.ingest(text=text, title=title, source_type=source_type)
