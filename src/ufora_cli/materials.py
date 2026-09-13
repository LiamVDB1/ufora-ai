from __future__ import annotations

from io import BytesIO
import logging
import os
from pathlib import Path
import re
from typing import Any
from urllib.parse import unquote

from d2l.errors import ForbiddenError, NotFoundError
from pypdf import PdfReader

from .core import UFORA_HOST, UforaError, _translate_upstream_text
from .d2l_entry import _patch_resolver


MAX_MATERIAL_BYTES = 50 * 1024 * 1024


class MaterialNotFound(UforaError):
    pass


def _client_and_resolver():
    os.environ["D2L_HOST"] = UFORA_HOST
    _patch_resolver()

    from d2l.cli import _resolve_token
    from d2l.auth import make_session
    from d2l.client import D2LClient
    from d2l.resolver import CourseResolver

    try:
        token = _resolve_token()
    except Exception as exc:
        raise UforaError(_translate_upstream_text(str(exc))) from exc
    client = D2LClient(make_session(token))
    return client, CourseResolver(client)


def _course_identity(org: dict[str, Any]) -> dict[str, Any]:
    return {"id": org["Id"], "code": org.get("Code"), "name": org.get("Name")}


def _overview_for(client: Any, org_id: int) -> dict[str, Any] | None:
    try:
        overview = client.lms_get(client.le(f"/{org_id}/overview"))
    except (NotFoundError, ForbiddenError):
        return None
    return overview if isinstance(overview, dict) else None


def get_course_overview(course: str) -> dict[str, Any]:
    """Return the dedicated Brightspace Course Overview for a Ufora course."""
    client, resolver = _client_and_resolver()
    enrollment = resolver.resolve(course)
    org = enrollment["OrgUnit"]
    overview = _overview_for(client, org["Id"])
    if overview is None:
        return {"course": _course_identity(org), "overview": None}

    description = overview.get("Description") or {}
    return {
        "course": _course_identity(org),
        "overview": {
            "description_text": description.get("Text", "") if isinstance(description, dict) else "",
            "description_html": description.get("Html", "") if isinstance(description, dict) else "",
            "has_attachment": bool(overview.get("HasAttachment")),
        },
    }


def _walk_content_items(node: Any, path: tuple[str, ...] = ()):
    """Yield modules and topics with their containing module path."""
    if not isinstance(node, dict):
        return

    for module in node.get("Modules", []) or []:
        if not isinstance(module, dict):
            continue
        title = str(module.get("Title") or module.get("Name") or "?")
        yield "module", path, module
        module_path = (*path, title)
        for topic in module.get("Topics", []) or []:
            if isinstance(topic, dict):
                yield "topic", module_path, topic
        yield from _walk_content_items(module, module_path)


def _walk_topics(node: Any, path: tuple[str, ...] = ()):
    for kind, item_path, item in _walk_content_items(node, path):
        if kind == "topic":
            yield item_path, item


def _find_topic(toc: dict[str, Any], query: str) -> tuple[tuple[str, ...], dict[str, Any]]:
    query = query.strip()
    if not query:
        raise MaterialNotFound("material query must not be empty")

    topics = list(_walk_topics(toc))
    if query.isdigit():
        for path, topic in topics:
            tid = topic.get("TopicId") or topic.get("Id")
            if str(tid) == query:
                return path, topic

    q = query.casefold()
    exact = [item for item in topics if str(item[1].get("Title", "")).casefold() == q]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise MaterialNotFound(_ambiguous_message(query, exact))

    partial = [item for item in topics if q in str(item[1].get("Title", "")).casefold()]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        raise MaterialNotFound(_ambiguous_message(query, partial))

    raise MaterialNotFound(f"No course material matching '{query}'. Use `ufora content COURSE --toc` first.")


def _description(item: dict[str, Any]) -> dict[str, Any]:
    value = item.get("Description") or {}
    return value if isinstance(value, dict) else {}


def _content_id(kind: str, item: dict[str, Any]) -> int | None:
    if kind == "module":
        return item.get("ModuleId") or item.get("Id")
    if kind == "topic":
        return item.get("TopicId") or item.get("Id")
    return None


def _overview_item(overview: dict[str, Any] | None) -> dict[str, Any] | None:
    if overview is None:
        return None
    return {
        "Title": "Overview",
        "Description": overview.get("Description") or {},
        "HasAttachment": bool(overview.get("HasAttachment")),
    }


def _normalize_content_path(value: str) -> str:
    """Normalize human path syntax such as `Slides / Tactics` or `Slides/Tactics`."""
    parts = [part.strip() for part in re.split(r"\s*(?:/|>|::)\s*", value.strip()) if part.strip()]
    return " / ".join(parts).casefold()


def _candidate_path(kind: str, path: tuple[str, ...], item: dict[str, Any]) -> str:
    if kind == "overview":
        return "overview"
    title = str(item.get("Title") or item.get("Name") or "?")
    return " / ".join([*path, title])


def _find_content_item(
    toc: dict[str, Any],
    query: str,
    *,
    overview: dict[str, Any] | None = None,
) -> tuple[str, tuple[str, ...], dict[str, Any]]:
    query = query.strip()
    if not query:
        raise MaterialNotFound("material query must not be empty")

    candidates: list[tuple[str, tuple[str, ...], dict[str, Any]]] = []
    overview_item = _overview_item(overview)
    if overview_item is not None:
        candidates.append(("overview", (), overview_item))
    candidates.extend(_walk_content_items(toc))

    q = query.casefold()
    if q in {"overview", "overzicht", "course overview", "cursusoverzicht"} and overview_item is not None:
        return "overview", (), overview_item

    if query.isdigit():
        for kind, path, item in candidates:
            if str(_content_id(kind, item)) == query:
                return kind, path, item

    normalized_path = _normalize_content_path(query)
    path_matches = [
        candidate
        for candidate in candidates
        if _normalize_content_path(_candidate_path(candidate[0], candidate[1], candidate[2])) == normalized_path
    ]
    if len(path_matches) == 1:
        return path_matches[0]
    if len(path_matches) > 1:
        raise MaterialNotFound(_ambiguous_content_message(query, path_matches))

    exact = [candidate for candidate in candidates if str(candidate[2].get("Title", "")).casefold() == q]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise MaterialNotFound(_ambiguous_content_message(query, exact))

    partial = [candidate for candidate in candidates if q in str(candidate[2].get("Title", "")).casefold()]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        raise MaterialNotFound(_ambiguous_content_message(query, partial))

    description_matches = []
    for candidate in candidates:
        text = _description(candidate[2]).get("Text", "") or ""
        if q in str(text).casefold():
            description_matches.append(candidate)
    if len(description_matches) == 1:
        return description_matches[0]
    if len(description_matches) > 1:
        raise MaterialNotFound(_ambiguous_content_message(query, description_matches))

    raise MaterialNotFound(
        f"No Ufora overview, module, or topic matching '{query}'. "
        "Use `ufora search COURSE QUERY` first."
    )


def search_course_content(course: str, query: str, *, limit: int = 20) -> dict[str, Any]:
    """Search the course overview, module bodies, topics, and topic descriptions."""
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    query = query.strip()
    if not query:
        raise ValueError("query must not be empty")

    client, resolver = _client_and_resolver()
    enrollment = resolver.resolve(course)
    org = enrollment["OrgUnit"]
    toc = client.content_toc(org["Id"])
    if not isinstance(toc, dict):
        toc = {"Modules": []}
    overview = _overview_for(client, org["Id"])

    q = query.casefold()
    words = [part for part in re.split(r"\s+", q) if part]
    candidates: list[tuple[str, tuple[str, ...], dict[str, Any]]] = []
    overview_item = _overview_item(overview)
    if overview_item is not None:
        candidates.append(("overview", (), overview_item))
    candidates.extend(_walk_content_items(toc))

    scored: list[tuple[int, str, tuple[str, ...], dict[str, Any]]] = []
    for kind, path, item in candidates:
        title = str(item.get("Title") or "")
        description_text = str(_description(item).get("Text", "") or "")
        aliases = "overview overzicht cursusoverzicht course overview" if kind == "overview" else ""
        haystack = " ".join([title, *path, description_text, aliases]).casefold()
        title_cf = title.casefold()

        score = 0
        if q == title_cf or (kind == "overview" and q in {"overview", "overzicht", "cursusoverzicht", "course overview"}):
            score += 100
        elif q in title_cf:
            score += 60
        elif q in description_text.casefold():
            score += 40
        elif q in haystack:
            score += 30
        if words:
            score += sum(5 for word in words if word in haystack)
        if score:
            scored.append((score, kind, path, item))

    scored.sort(key=lambda candidate: (-candidate[0], str(candidate[3].get("Title") or "").casefold()))
    matches = []
    for score, kind, path, item in scored[:limit]:
        description = _description(item)
        item_id = _content_id(kind, item)
        matches.append(
            {
                "score": score,
                "kind": kind,
                "module_path": list(path),
                "item_id": item_id,
                "topic_id": item_id if kind == "topic" else None,
                "module_id": item_id if kind == "module" else None,
                "title": item.get("Title"),
                "type": (
                    "Overview"
                    if kind == "overview"
                    else "Module"
                    if kind == "module"
                    else item.get("TypeIdentifier") or item.get("TopicType")
                ),
                "url": item.get("Url"),
                "last_modified": item.get("LastModifiedDate"),
                "description_text": description.get("Text", "") or "",
                "has_attachment": bool(item.get("HasAttachment")) if kind == "overview" else False,
            }
        )

    return {
        "course": _course_identity(org),
        "query": query,
        "matches": matches,
    }


def _ambiguous_content_message(
    query: str,
    matches: list[tuple[str, tuple[str, ...], dict[str, Any]]],
) -> str:
    lines = [f"Multiple Ufora content items match '{query}':"]
    for kind, path, item in matches[:20]:
        item_id = _content_id(kind, item)
        where_parts = [*path, str(item.get("Title") or "?")]
        where = " / ".join(where_parts)
        ident = "overview" if kind == "overview" else str(item_id)
        lines.append(f"  [{ident}] {kind}: {where}")
    lines.append("Use `ufora search COURSE QUERY`, then use a numeric item ID or more specific title.")
    return "\n".join(lines)


def _ambiguous_message(query: str, matches: list[tuple[tuple[str, ...], dict[str, Any]]]) -> str:
    lines = [f"Multiple materials match '{query}':"]
    for path, topic in matches[:20]:
        tid = topic.get("TopicId") or topic.get("Id")
        where = " / ".join(path)
        lines.append(f"  [{tid}] {where} / {topic.get('Title', '?')}")
    lines.append("Use the numeric topic ID or a more specific title.")
    return "\n".join(lines)


def _safe_filename(value: str, fallback: str) -> str:
    name = Path(str(value).replace("\\", "/")).name.strip()
    return name if name not in {"", ".", ".."} else fallback


def _filename(response, topic: dict[str, Any]) -> str:
    disposition = response.headers.get("Content-Disposition", "")
    match = re.search(r"filename\*?=[\"']?(?:UTF-8''|utf-8'')?([^\"';]+)", disposition)
    if match:
        return unquote(match.group(1).strip())
    url = str(topic.get("Url") or "")
    if url:
        return unquote(url.rsplit("/", 1)[-1])
    return str(topic.get("Title") or f"topic-{topic.get('TopicId', 'unknown')}")


def download_single_content_file(
    course: str,
    target: str,
    out_dir: str | Path,
) -> dict[str, Any] | None:
    """Download one file-backed topic by title/path/ID.

    Returns ``None`` when TARGET resolves to a module, allowing the CLI to fall
    back to recursive module download behavior.
    """
    client, resolver = _client_and_resolver()
    enrollment = resolver.resolve(course)
    org = enrollment["OrgUnit"]
    org_id = org["Id"]
    toc = client.content_toc(org_id)
    if not isinstance(toc, dict):
        toc = {"Modules": []}
    overview = _overview_for(client, org_id)
    kind, path, item = _find_content_item(toc, target, overview=overview)

    if kind == "module":
        return None

    if kind == "overview":
        if not item.get("HasAttachment"):
            raise UforaError("The course overview has no downloadable attachment.")
        response = client.lms_get_raw(client.le(f"/{org_id}/overview/attachment"))
        fallback = "course-overview-attachment"
    else:
        is_file = item.get("TypeIdentifier") == "File" or item.get("TopicType") == 1
        if not is_file:
            raise UforaError(
                f"'{item.get('Title', target)}' is not a downloadable Ufora file. "
                "Use `ufora material COURSE TARGET` to read its inline text or URL."
            )
        item_id = _content_id(kind, item)
        response = client.content_topic_file(org_id, int(item_id))
        fallback = f"topic-{item_id}"

    filename = _safe_filename(_filename(response, item), fallback)
    destination = Path(out_dir).expanduser()
    destination.mkdir(parents=True, exist_ok=True)
    file_path = destination / filename
    file_path.write_bytes(response.content)
    return {
        "course": _course_identity(org),
        "kind": kind,
        "module_path": list(path),
        "item_id": _content_id(kind, item),
        "title": item.get("Title"),
        "filename": filename,
        "path": str(file_path.resolve()),
        "size_bytes": len(response.content),
    }


def _extract_text(content: bytes, filename: str, content_type: str) -> tuple[str | None, str]:
    lower_name = filename.lower()
    lower_type = content_type.lower()

    if lower_name.endswith(".pdf") or "application/pdf" in lower_type:
        # pypdf can emit optional-font diagnostics directly through its logger.
        # They are useful to library developers but make the student CLI unusably noisy.
        logger = logging.getLogger("pypdf")
        previous_level = logger.level
        logger.setLevel(logging.ERROR)
        try:
            reader = PdfReader(BytesIO(content))
            pages = [(page.extract_text() or "").strip() for page in reader.pages]
        finally:
            logger.setLevel(previous_level)
        return "\n\n".join(text for text in pages if text), "pdf"

    if (
        lower_name.endswith((".txt", ".md", ".csv", ".html", ".htm", ".xml", ".json"))
        or lower_type.startswith("text/")
        or "json" in lower_type
        or "xml" in lower_type
    ):
        return content.decode("utf-8", errors="replace"), "text"

    return None, "binary"


def _extract_response_content(
    response: Any,
    item: dict[str, Any],
    *,
    max_chars: int,
) -> dict[str, Any]:
    filename = _filename(response, item)
    content_type = response.headers.get("Content-Type", "")
    content = response.content
    if len(content) > MAX_MATERIAL_BYTES:
        raise UforaError(
            f"Material '{filename}' is {len(content)} bytes; direct MCP/CLI extraction is limited "
            f"to {MAX_MATERIAL_BYTES} bytes. Download the module/file locally instead."
        )
    try:
        text, kind = _extract_text(content, filename, content_type)
    except Exception as exc:
        raise UforaError(f"Could not extract text from '{filename}': {exc}") from exc
    truncated = text is not None and len(text) > max_chars
    if text is not None:
        text = text[:max_chars]
    return {
        "kind": kind,
        "filename": filename,
        "content_type": content_type,
        "size_bytes": len(content),
        "text": text,
        "truncated": truncated,
        "note": None
        if text is not None
        else "Binary file is downloadable with `ufora download-content`, but direct text extraction is not supported for this format yet.",
    }


def read_material(course: str, material: str, *, max_chars: int = 60_000) -> dict[str, Any]:
    """Read a Ufora Overview, module body, topic description, or file-backed topic."""
    if not 1_000 <= max_chars <= 500_000:
        raise ValueError("max_chars must be between 1000 and 500000")

    client, resolver = _client_and_resolver()
    enrollment = resolver.resolve(course)
    org = enrollment["OrgUnit"]
    org_id = org["Id"]
    toc = client.content_toc(org_id)
    if not isinstance(toc, dict):
        toc = {"Modules": []}
    overview = _overview_for(client, org_id)

    kind, path, item = _find_content_item(toc, material, overview=overview)
    item_id = _content_id(kind, item)
    description = _description(item)
    item_record: dict[str, Any] = {
        "kind": kind,
        "id": item_id,
        "title": item.get("Title"),
        "type": (
            "Overview"
            if kind == "overview"
            else "Module"
            if kind == "module"
            else item.get("TypeIdentifier") or item.get("TopicType")
        ),
        "url": item.get("Url"),
        "last_modified": item.get("LastModifiedDate"),
        "description_text": description.get("Text", "") or "",
        "description_html": description.get("Html", "") or "",
    }
    result: dict[str, Any] = {
        "course": _course_identity(org),
        "module_path": list(path),
        "item": item_record,
    }

    if kind == "overview":
        result["content"] = {
            "kind": "overview",
            "text": item_record["description_text"][:max_chars],
            "truncated": len(item_record["description_text"]) > max_chars,
        }
        if item.get("HasAttachment"):
            response = client.lms_get_raw(client.le(f"/{org_id}/overview/attachment"))
            result["attachment"] = _extract_response_content(
                response,
                {"Title": "course-overview-attachment"},
                max_chars=max_chars,
            )
        return result

    if kind == "module":
        text = item_record["description_text"]
        result["content"] = {
            "kind": "module_description",
            "text": text[:max_chars],
            "truncated": len(text) > max_chars,
        }
        children: list[dict[str, Any]] = []
        for child_module in item.get("Modules", []) or []:
            if not isinstance(child_module, dict):
                continue
            children.append(
                {
                    "kind": "module",
                    "id": child_module.get("ModuleId") or child_module.get("Id"),
                    "title": child_module.get("Title") or child_module.get("Name"),
                    "type": "Module",
                }
            )
        for child_topic in item.get("Topics", []) or []:
            if not isinstance(child_topic, dict):
                continue
            children.append(
                {
                    "kind": "topic",
                    "id": child_topic.get("TopicId") or child_topic.get("Id"),
                    "title": child_topic.get("Title") or child_topic.get("Name"),
                    "type": child_topic.get("TypeIdentifier") or child_topic.get("TopicType"),
                }
            )
        result["children"] = children
        return result

    # Backwards-compatible alias for clients written against the 0.x topic-only shape.
    result["topic"] = item_record
    is_file = item.get("TypeIdentifier") == "File" or item.get("TopicType") == 1
    if not is_file:
        text = item_record["description_text"]
        result["content"] = {
            "kind": "external_or_inline",
            "text": text[:max_chars],
            "source_url": item.get("Url"),
            "truncated": len(text) > max_chars,
        }
        return result

    response = client.content_topic_file(org_id, int(item_id))
    result["content"] = _extract_response_content(response, item, max_chars=max_chars)
    return result
