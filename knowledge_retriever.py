import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


STOPWORDS = {
    "a",
    "about",
    "an",
    "and",
    "for",
    "how",
    "i",
    "is",
    "me",
    "my",
    "notes",
    "of",
    "on",
    "please",
    "revise",
    "show",
    "summarize",
    "summary",
    "technique",
    "the",
    "to",
}


@dataclass(slots=True)
class IndexEntry:
    title: str
    path: Path
    metadata: dict[str, str]
    excerpt: str


@dataclass(slots=True)
class RetrievedNote:
    title: str
    path: Path
    metadata: dict[str, Any]
    body: str
    excerpt: str
    score: float


@dataclass(slots=True)
class RetrievalResult:
    request: str
    topic: str
    matches: list[RetrievedNote]

    def as_prompt_context(self) -> str:
        sections: list[str] = []
        for note in self.matches:
            sections.extend(
                [
                    f"Title: {note.title}",
                    f"Path: {note.path.name}",
                    f"Metadata: {json.dumps(note.metadata, ensure_ascii=False)}",
                    "Body:",
                    note.body or note.excerpt or "",
                    "",
                ]
            )
        return "\n".join(sections).strip()


class KnowledgeRetriever:
    def __init__(self, knowledge_dir: Path):
        self.knowledge_dir = knowledge_dir
        self.index_path = knowledge_dir / "index.md"
        if not self.index_path.exists():
            raise FileNotFoundError(
                f"Knowledge index not found at {self.index_path}. Run notion_connection.py first."
            )

        self.index_entries = self._load_index_entries()

    def retrieve(self, request: str, limit: int = 3) -> RetrievalResult:
        topic = self.extract_topic(request)
        query_tokens = self._tokenize(topic)

        scored_entries = []
        for entry in self.index_entries:
            score = self._score_index_entry(topic, query_tokens, entry)
            if score > 0:
                scored_entries.append((score, entry))

        scored_entries.sort(key=lambda item: item[0], reverse=True)
        shortlisted = scored_entries[: max(limit * 2, 5)]

        retrieved_notes = []
        for base_score, entry in shortlisted:
            note = self._load_note(entry)
            note.score = base_score + self._score_note_body(topic, query_tokens, note)
            retrieved_notes.append(note)

        retrieved_notes.sort(key=lambda note: note.score, reverse=True)

        return RetrievalResult(
            request=request,
            topic=topic,
            matches=retrieved_notes[:limit],
        )

    @staticmethod
    def extract_topic(request: str) -> str:
        patterns = [
            r"^\s*(?:create|make|generate)\s+(?:a\s+)?(?:linkedin\s+|instagram\s+)?carousel\s+(?:on|about|for)\s+(?P<topic>.+?)\.?\s*$",
            r"^\s*/carousel\s+(?P<topic>.+?)\s*$",
            r"^\s*summarize\s+my\s+notes\s+(?:on|about|for)\s+(?P<topic>.+?)\.?\s*$",
            r"^\s*revise\s+my\s+notes\s+(?:on|about|for)\s+(?P<topic>.+?)\.?\s*$",
            r"^\s*/(?:summarize|revise|find)\s+(?P<topic>.+?)\s*$",
            r"^\s*summarize\s+(?P<topic>.+?)\.?\s*$",
        ]

        for pattern in patterns:
            match = re.match(pattern, request, flags=re.IGNORECASE)
            if match:
                return match.group("topic").strip(" .\"'")

        return request.strip()

    def _load_index_entries(self) -> list[IndexEntry]:
        content = self.index_path.read_text(encoding="utf-8")
        body = self._strip_frontmatter(content)
        entries: list[IndexEntry] = []
        current_title = ""
        current_path: Path | None = None
        current_metadata: dict[str, str] = {}
        current_excerpt = ""

        for raw_line in body.splitlines():
            line = raw_line.strip()
            if line.startswith("## ["):
                if current_title and current_path is not None:
                    entries.append(
                        IndexEntry(
                            title=current_title,
                            path=current_path,
                            metadata=current_metadata,
                            excerpt=current_excerpt,
                        )
                    )

                match = re.match(r"^## \[(?P<title>.+)\]\((?P<path>.+)\)$", line)
                if not match:
                    continue

                current_title = match.group("title")
                current_path = self.knowledge_dir / match.group("path")
                current_metadata = {}
                current_excerpt = ""
                continue

            if not line.startswith("- "):
                continue

            key, _, value = line[2:].partition(":")
            if not value:
                continue

            cleaned_value = value.strip()
            if key.strip() == "excerpt":
                current_excerpt = cleaned_value
            else:
                current_metadata[key.strip()] = cleaned_value

        if current_title and current_path is not None:
            entries.append(
                IndexEntry(
                    title=current_title,
                    path=current_path,
                    metadata=current_metadata,
                    excerpt=current_excerpt,
                )
            )

        return entries

    def _load_note(self, entry: IndexEntry) -> RetrievedNote:
        metadata, body = self._parse_note_file(entry.path)
        return RetrievedNote(
            title=str(metadata.get("title") or entry.title),
            path=entry.path,
            metadata=metadata,
            body=body,
            excerpt=entry.excerpt,
            score=0.0,
        )

    def _score_index_entry(
        self, topic: str, query_tokens: set[str], entry: IndexEntry
    ) -> float:
        topic_norm = self._normalize_text(topic)
        title_norm = self._normalize_text(entry.title)
        excerpt_norm = self._normalize_text(entry.excerpt)
        metadata_text = self._normalize_text(" ".join(entry.metadata.values()))
        score = 0.0

        if topic_norm and topic_norm in title_norm:
            score += 80
        if topic_norm and topic_norm in excerpt_norm:
            score += 30
        if topic_norm and topic_norm in metadata_text:
            score += 15

        title_tokens = self._tokenize(entry.title)
        for token in query_tokens:
            if token in title_tokens:
                score += 12
            elif token in title_norm:
                score += 8

            if token in excerpt_norm:
                score += 4
            if token in metadata_text:
                score += 3

        return score

    def _score_note_body(
        self, topic: str, query_tokens: set[str], note: RetrievedNote
    ) -> float:
        topic_norm = self._normalize_text(topic)
        body_norm = self._normalize_text(note.body)
        score = 0.0

        if topic_norm and topic_norm in body_norm:
            score += 25

        for token in query_tokens:
            if token in body_norm:
                score += 2

        return score

    @staticmethod
    def _parse_note_file(path: Path) -> tuple[dict[str, Any], str]:
        content = path.read_text(encoding="utf-8")
        if not content.startswith("---\n"):
            return {}, content.strip()

        end_marker = content.find("\n---\n", 4)
        if end_marker == -1:
            return {}, content.strip()

        frontmatter_text = content[4:end_marker]
        body = content[end_marker + 5 :].strip()
        metadata: dict[str, Any] = {}

        for line in frontmatter_text.splitlines():
            key, _, raw_value = line.partition(":")
            if not raw_value:
                continue

            parsed_value = raw_value.strip()
            try:
                metadata[key.strip()] = json.loads(parsed_value)
            except json.JSONDecodeError:
                metadata[key.strip()] = parsed_value

        return metadata, body

    @staticmethod
    def _strip_frontmatter(content: str) -> str:
        if not content.startswith("---\n"):
            return content

        end_marker = content.find("\n---\n", 4)
        if end_marker == -1:
            return content

        return content[end_marker + 5 :]

    @staticmethod
    def _normalize_text(value: str) -> str:
        return re.sub(r"\s+", " ", value.lower()).strip()

    @staticmethod
    def _tokenize(value: str) -> set[str]:
        tokens = re.findall(r"[a-z0-9]+", value.lower())
        return {token for token in tokens if token not in STOPWORDS and len(token) > 1}


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Retrieve notes from the knowledge layer.")
    parser.add_argument("query", help="The user request to resolve against the note library.")
    args = parser.parse_args()

    retriever = KnowledgeRetriever(Path(__file__).resolve().parent / "knowledge_layer")
    result = retriever.retrieve(args.query)

    print(f"Topic: {result.topic}")
    if not result.matches:
        print("No matching notes found.")
        return

    for note in result.matches:
        print(f"- {note.title} ({note.path.name}) score={note.score:.1f}")


if __name__ == "__main__":
    main()
