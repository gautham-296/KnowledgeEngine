import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from notion_client import Client
from notion_client.errors import APIResponseError


project_root = Path(__file__).resolve().parent
output_dir = project_root / "knowledge_layer"
index_path = output_dir / "index.md"

load_dotenv(project_root / ".env")

notion_token = os.getenv("NOTION_TOKEN")
database_id = os.getenv("NOTION_DATABASE_ID")

if not notion_token or not database_id:
    raise RuntimeError(
        "Missing NOTION_TOKEN or NOTION_DATABASE_ID in .env at the workspace root."
    )

notion = Client(auth=notion_token)


def rich_text_to_plain_text(items: list[dict[str, Any]]) -> str:
    return "".join(item.get("plain_text", "") for item in items)


def serialize_user(user: dict[str, Any] | None) -> dict[str, Any] | None:
    if not user:
        return None

    return {
        "id": user.get("id"),
        "name": user.get("name"),
        "type": user.get("type"),
    }


def serialize_file(file_item: dict[str, Any]) -> dict[str, Any]:
    file_type = file_item.get("type")
    file_payload = file_item.get(file_type, {})

    return {
        "name": file_item.get("name"),
        "type": file_type,
        "url": file_payload.get("url"),
        "expiry_time": file_payload.get("expiry_time"),
    }


def serialize_formula(formula: dict[str, Any]) -> Any:
    formula_type = formula.get("type")
    if formula_type == "string":
        return formula.get("string")
    if formula_type == "number":
        return formula.get("number")
    if formula_type == "boolean":
        return formula.get("boolean")
    if formula_type == "date":
        return formula.get("date")

    return None


def serialize_rollup(rollup: dict[str, Any]) -> Any:
    rollup_type = rollup.get("type")
    if rollup_type == "number":
        return rollup.get("number")
    if rollup_type == "date":
        return rollup.get("date")
    if rollup_type == "array":
        values = []
        for item in rollup.get("array", []):
            values.append(serialize_property_value({"type": item.get("type"), **item}))
        return values

    return None


def serialize_property_value(prop: dict[str, Any]) -> Any:
    prop_type = prop.get("type")

    if prop_type == "title":
        return rich_text_to_plain_text(prop.get("title", []))
    if prop_type == "rich_text":
        return rich_text_to_plain_text(prop.get("rich_text", []))
    if prop_type == "number":
        return prop.get("number")
    if prop_type == "select":
        selected = prop.get("select")
        return selected.get("name") if selected else None
    if prop_type == "multi_select":
        return [item.get("name") for item in prop.get("multi_select", [])]
    if prop_type == "status":
        status = prop.get("status")
        return status.get("name") if status else None
    if prop_type == "date":
        return prop.get("date")
    if prop_type == "people":
        return [serialize_user(user) for user in prop.get("people", [])]
    if prop_type == "files":
        return [serialize_file(file_item) for file_item in prop.get("files", [])]
    if prop_type == "checkbox":
        return prop.get("checkbox")
    if prop_type == "url":
        return prop.get("url")
    if prop_type == "email":
        return prop.get("email")
    if prop_type == "phone_number":
        return prop.get("phone_number")
    if prop_type == "relation":
        return [item.get("id") for item in prop.get("relation", [])]
    if prop_type == "formula":
        return serialize_formula(prop.get("formula", {}))
    if prop_type == "rollup":
        return serialize_rollup(prop.get("rollup", {}))
    if prop_type == "created_time":
        return prop.get("created_time")
    if prop_type == "created_by":
        return serialize_user(prop.get("created_by"))
    if prop_type == "last_edited_time":
        return prop.get("last_edited_time")
    if prop_type == "last_edited_by":
        return serialize_user(prop.get("last_edited_by"))
    if prop_type == "unique_id":
        unique_id = prop.get("unique_id") or {}
        return {
            "prefix": unique_id.get("prefix"),
            "number": unique_id.get("number"),
        }

    return prop.get(prop_type)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "untitled"


def normalize_key(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return normalized or "field"


def make_yaml_frontmatter(metadata: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in metadata.items():
        lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines)


def compact_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def build_excerpt(body: str, limit: int = 220) -> str:
    cleaned = compact_whitespace(body)
    if len(cleaned) <= limit:
        return cleaned

    return cleaned[: limit - 3].rstrip() + "..."


def extract_title(properties: dict[str, Any]) -> str:
    for prop in properties.values():
        if prop.get("type") == "title":
            title = serialize_property_value(prop)
            if title:
                return title
    return "Untitled"


def extract_page_body(properties: dict[str, Any]) -> str:
    preferred_content_fields = ["Content", "Atomic Content", "Summary", "Body"]

    for field_name in preferred_content_fields:
        prop = properties.get(field_name)
        if not prop:
            continue

        content = serialize_property_value(prop)
        if isinstance(content, str) and content.strip():
            return content.strip()

    return ""


def fetch_all_pages() -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    next_cursor: str | None = None

    while True:
        query_args: dict[str, Any] = {"data_source_id": database_id}
        if next_cursor:
            query_args["start_cursor"] = next_cursor

        try:
            response: Any = notion.data_sources.query(**query_args)
        except APIResponseError as error:
            raise RuntimeError(
                "Notion could not access the configured database/data source. "
                "Verify NOTION_DATABASE_ID in .env and ensure the database is shared with your integration."
            ) from error

        pages.extend(response.get("results", []))

        if not response.get("has_more"):
            break

        next_cursor = response.get("next_cursor")

    return pages


def build_note_metadata(page: dict[str, Any]) -> dict[str, Any]:
    properties = page.get("properties", {})
    metadata = {
        "title": extract_title(properties),
        "notion_page_id": page.get("id"),
        "source_database_id": database_id,
        "created_time": page.get("created_time"),
        "last_edited_time": page.get("last_edited_time"),
        "exported_at": datetime.now(UTC).isoformat(),
    }

    for property_name, prop in properties.items():
        metadata[normalize_key(property_name)] = serialize_property_value(prop)

    return metadata


def build_output_path(metadata: dict[str, Any]) -> Path:
    title_slug = slugify(str(metadata.get("title") or "untitled"))
    page_id = str(metadata.get("notion_page_id") or "")
    return output_dir / f"{title_slug}-{page_id[:8]}.md"


def write_index(note_records: list[dict[str, Any]]) -> Path:
    domains = sorted(
        {
            record["metadata"].get("domain")
            for record in note_records
            if record["metadata"].get("domain")
        }
    )
    index_metadata = {
        "title": "Knowledge Layer Index",
        "source_database_id": database_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "note_count": len(note_records),
        "domains": domains,
    }

    index_lines = [
        make_yaml_frontmatter(index_metadata),
        "",
        "# Knowledge Layer Index",
        "",
        "This file is rebuilt whenever `python notion_connection.py` runs.",
        "",
        f"Total notes: {len(note_records)}",
    ]

    for record in sorted(note_records, key=lambda item: item["metadata"]["title"].lower()):
        metadata = record["metadata"]
        index_lines.extend(
            [
                "",
                f"## [{metadata['title']}]({record['path'].name})",
                "",
                f"- domain: {metadata.get('domain') or 'Unknown'}",
                f"- note_type: {metadata.get('note_type') or 'Unknown'}",
                f"- book_title: {metadata.get('book_title') or 'Unknown'}",
                f"- author: {metadata.get('author') or 'Unknown'}",
                f"- status: {metadata.get('status') or 'Unknown'}",
                f"- notion_page_id: {metadata.get('notion_page_id')}",
            ]
        )

        excerpt = record["excerpt"]
        if excerpt:
            index_lines.extend([f"- excerpt: {excerpt}"])

    index_path.write_text("\n".join(index_lines).rstrip() + "\n", encoding="utf-8")
    return index_path


def export_pages_to_markdown() -> tuple[list[Path], Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    exported_files: list[Path] = []
    note_records: list[dict[str, Any]] = []

    for page in fetch_all_pages():
        properties = page.get("properties", {})
        metadata = build_note_metadata(page)
        body = extract_page_body(properties)
        frontmatter = make_yaml_frontmatter(metadata)

        note_parts = [frontmatter, "", f"# {metadata['title']}"]
        if body:
            note_parts.extend(["", body])

        note_path = build_output_path(metadata)
        note_path.write_text("\n".join(note_parts).rstrip() + "\n", encoding="utf-8")
        exported_files.append(note_path)
        note_records.append(
            {
                "metadata": metadata,
                "path": note_path,
                "excerpt": build_excerpt(body),
            }
        )

    return exported_files, write_index(note_records)


def main() -> None:
    exported_files, generated_index = export_pages_to_markdown()
    print(f"Exported {len(exported_files)} notes to {output_dir}")
    print(generated_index.name)
    for note_path in exported_files:
        print(note_path.name)


if __name__ == "__main__":
    main()
