from __future__ import annotations

from ufora_cli import d2l_entry


class FakeResolver:
    def __init__(self, enrollments):
        self._items = enrollments

    def _load(self):
        return self._items


def enrollment(*, oid: int, code: str, name: str, type_code: str, type_name: str):
    return {
        "OrgUnit": {
            "Id": oid,
            "Code": code,
            "Name": name,
            "Type": {"Code": type_code, "Name": type_name},
        }
    }


def test_ugent_localized_course_offering_is_recognized():
    item = enrollment(
        oid=1,
        code="E017950A_2026",
        name="E017950A - Secure Software and Systems",
        type_code="Course Offering",
        type_name="Cursuseditie",
    )
    assert d2l_entry._is_course_offering(item)


def test_groups_are_excluded_from_courses():
    course = enrollment(
        oid=1,
        code="C003783A_2025",
        name="C003783A - Logisch programmeren",
        type_code="Course Offering",
        type_name="Cursuseditie",
    )
    group = enrollment(
        oid=2,
        code="uuid",
        name="C003783A GR01",
        type_code="Group",
        type_name="Groep",
    )
    assert d2l_entry._all_courses(FakeResolver([course, group])) == [course]


def test_current_courses_use_academic_year_suffix(monkeypatch):
    monkeypatch.setattr(d2l_entry, "_academic_year_start", lambda: 2026)
    old = enrollment(
        oid=1,
        code="C003783A_2025",
        name="Old",
        type_code="Course Offering",
        type_name="Cursuseditie",
    )
    current = enrollment(
        oid=2,
        code="E017950A_2026",
        name="Current",
        type_code="Course Offering",
        type_name="Cursuseditie",
    )
    assert d2l_entry._list_courses(FakeResolver([old, current])) == [current]


def test_file_topics_are_labeled_as_files_even_without_topictype():
    topic = {"TypeIdentifier": "File", "Title": "Hoofdstuk 1"}
    assert d2l_entry._topic_label(topic) == "file"


def test_external_topics_are_labeled_as_links():
    topic = {"TypeIdentifier": "Link", "Title": "Dodona"}
    assert d2l_entry._topic_label(topic) == "link"


def test_disambiguation_prefers_course_over_gr01():
    course = enrollment(
        oid=1,
        code="C003783A_2025",
        name="C003783A - Logisch programmeren",
        type_code="Course Offering",
        type_name="Cursuseditie",
    )
    group = enrollment(
        oid=2,
        code="uuid",
        name="C003783A GR01",
        type_code="Group",
        type_name="Groep",
    )
    assert d2l_entry._disambiguate(FakeResolver([]), "C003783A", [course, group]) == course
