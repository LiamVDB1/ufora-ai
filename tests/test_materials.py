from __future__ import annotations

import pytest

from ufora_cli import materials
from ufora_cli.materials import MaterialNotFound, _extract_text, _find_content_item, _find_topic


def sample_toc():
    return {
        "Modules": [
            {
                "ModuleId": 20,
                "Title": "Project",
                "Description": {
                    "Text": "Optimize the Python implementation and benchmark the result. Handle soft-clipped reads efficiently."
                },
                "Topics": [
                    {
                        "TopicId": 10,
                        "Title": "Hoofdstuk 1",
                        "TypeIdentifier": "File",
                        "Description": {"Text": "Introduction and exam material"},
                    },
                    {"TopicId": 11, "Title": "Hoofdstuk 2", "Description": {"Text": ""}},
                ],
                "Modules": [
                    {
                        "ModuleId": 21,
                        "Title": "Extra",
                        "Description": {"Text": ""},
                        "Topics": [{"TopicId": 12, "Title": "Tactics", "Description": {"Text": ""}}],
                        "Modules": [],
                    }
                ],
            }
        ]
    }


class FakeResolver:
    def resolve(self, _course):
        return {
            "OrgUnit": {"Id": 123, "Code": "TEST_2026", "Name": "Test Course"},
            "Access": {"IsActive": True},
        }


class FakeResponse:
    headers = {"Content-Disposition": 'attachment; filename="chapter.pdf"', "Content-Type": "application/pdf"}
    content = b"pdf-bytes"


class FakeClient:
    def content_toc(self, _org_id):
        return sample_toc()

    def content_topic_file(self, _org_id, _topic_id):
        return FakeResponse()


OVERVIEW = {
    "Description": {
        "Text": "Used software: Example Tool. Exercises use another platform. Closed-book exam.",
        "Html": "<p>Used software: Example Tool.</p>",
    },
    "HasAttachment": False,
}


def test_find_topic_exact_title_and_path():
    path, topic = _find_topic(sample_toc(), "Hoofdstuk 1")
    assert path == ("Project",)
    assert topic["TopicId"] == 10


def test_find_topic_by_numeric_id():
    path, topic = _find_topic(sample_toc(), "12")
    assert path == ("Project", "Extra")
    assert topic["Title"] == "Tactics"


def test_find_topic_rejects_missing():
    with pytest.raises(MaterialNotFound):
        _find_topic(sample_toc(), "does not exist")


def test_extract_text_decodes_text_file():
    text, kind = _extract_text(b"hello\nworld", "notes.txt", "text/plain")
    assert kind == "text"
    assert text == "hello\nworld"


def test_search_includes_overview_and_module_descriptions(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(materials, "_client_and_resolver", lambda: (FakeClient(), FakeResolver()))
    monkeypatch.setattr(materials, "_overview_for", lambda client, org_id: OVERVIEW)

    overview_matches = materials.search_course_content("TEST", "software")["matches"]
    assert overview_matches[0]["kind"] == "overview"
    assert "Used software" in overview_matches[0]["description_text"]

    module_matches = materials.search_course_content("TEST", "soft-clipped")["matches"]
    assert module_matches[0]["kind"] == "module"
    assert module_matches[0]["title"] == "Project"


def test_find_content_item_accepts_full_module_path():
    kind, path, item = _find_content_item(sample_toc(), "Project / Extra / Tactics")

    assert kind == "topic"
    assert path == ("Project", "Extra")
    assert item["TopicId"] == 12


def test_find_content_item_accepts_compact_path_syntax():
    kind, path, item = _find_content_item(sample_toc(), "Project/Extra/Tactics")

    assert kind == "topic"
    assert path == ("Project", "Extra")
    assert item["TopicId"] == 12


def test_download_single_content_file_accepts_topic_id(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setattr(materials, "_client_and_resolver", lambda: (FakeClient(), FakeResolver()))
    monkeypatch.setattr(materials, "_overview_for", lambda client, org_id: OVERVIEW)

    result = materials.download_single_content_file("TEST", "10", tmp_path)

    assert result is not None
    assert result["filename"] == "chapter.pdf"
    assert (tmp_path / "chapter.pdf").read_bytes() == b"pdf-bytes"


def test_download_single_content_file_returns_none_for_module(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setattr(materials, "_client_and_resolver", lambda: (FakeClient(), FakeResolver()))
    monkeypatch.setattr(materials, "_overview_for", lambda client, org_id: OVERVIEW)

    assert materials.download_single_content_file("TEST", "Project", tmp_path) is None


def test_read_material_module_without_body_lists_children(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(materials, "_client_and_resolver", lambda: (FakeClient(), FakeResolver()))
    monkeypatch.setattr(materials, "_overview_for", lambda client, org_id: OVERVIEW)

    extra = materials.read_material("TEST", "Project / Extra")

    assert extra["item"]["kind"] == "module"
    assert extra["content"]["text"] == ""
    assert extra["children"] == [
        {"kind": "topic", "id": 12, "title": "Tactics", "type": None}
    ]


def test_read_material_can_read_overview_and_module_body(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(materials, "_client_and_resolver", lambda: (FakeClient(), FakeResolver()))
    monkeypatch.setattr(materials, "_overview_for", lambda client, org_id: OVERVIEW)

    overview = materials.read_material("TEST", "Overzicht")
    assert overview["item"]["kind"] == "overview"
    assert "Closed-book exam" in overview["content"]["text"]

    project = materials.read_material("TEST", "Project")
    assert project["item"]["kind"] == "module"
    assert project["item"]["id"] == 20
    assert "soft-clipped" in project["content"]["text"]
