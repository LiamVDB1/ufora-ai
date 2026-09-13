# UGent / Ufora compatibility notes

Ufora AI exists partly because generic Brightspace assumptions do not perfectly match UGent's Ufora configuration.

## Localized course type

Brightspace enrollment objects contain both a human-readable type name and a stable machine-readable type code.

UGent returns real courses approximately as:

```json
{
  "Type": {
    "Code": "Course Offering",
    "Name": "Cursuseditie"
  }
}
```

Generic tooling that checks only `Type.Name == "Course Offering"` therefore finds zero courses. Ufora AI recognizes the stable `Type.Code` and treats localized names as presentation only.

## Groups are not courses

The same enrollment feed can contain group objects such as:

```text
C003783A - Logisch programmeren   Course Offering
C003783A GR01                     Group
```

A short query such as `C003783A` can match both. Ufora AI excludes group objects from course lists and prefers the real Course Offering during disambiguation.

## Historical courses remain active

UGent can leave old course offerings marked `IsActive=true` and `CanAccess=true` long after the academic year ended. Treating every active offering as a current course causes two problems:

1. students see a noisy list of old courses;
2. cross-course endpoints such as calendar/due can fail when given a huge collection containing historical/administrative offerings.

Ufora AI therefore treats offering codes ending in `_YYYY` as the academic-year start year and uses the current year by default. `ufora courses --all` remains available for history.

If UGent changes this code convention, the compatibility test suite should be updated based on observed API behavior rather than silently guessing.

## Administrative/evaluation offerings

A student can also be enrolled in evaluation or information objects that use Course Offering semantics but are not normal courses. Current-year filtering greatly reduces these in ordinary planning queries. Historical listing intentionally remains closer to the raw set of real Course Offerings.

## Empty feature endpoints

Not every UGent course uses every Brightspace feature. Real examples include courses with substantial course content and announcements but no Brightspace Assignments or Quizzes. Ufora AI reports the endpoint faithfully and does not transform `[]` into a claim that no coursework exists.

## Course Overview is separate from the table of contents

Brightspace exposes the classic **Course Overview** through a dedicated read endpoint (`/{orgUnitId}/overview`). It is not part of `content/toc` on every course/configuration. At UGent this surface can contain high-value course-wide information such as required software, books/chapters, exam format, grading rules, projects, and external platforms.

Ufora AI therefore exposes Course Overview explicitly and includes it in targeted course-context workflows. A missing item in the TOC does not imply the course lacks an Overview.

## Module descriptions are first-class content

Brightspace modules can carry substantial `Description.Text`/`Description.Html` bodies. At UGent, an instructor can put an entire project specification directly on a module such as `Project` rather than inside a topic/file. Ufora AI search/read workflows include module bodies rather than indexing topics only.

## Course content

The Brightspace table-of-contents endpoint can expose more than a human-readable module list. Module/topic objects can include:

- nested module structure;
- topic IDs;
- file/link type;
- module and topic descriptions (`Text` and `Html`);
- URLs;
- modification timestamps.

Ufora AI's MCP `get_course_content(..., detailed=true)` uses this richer form. `read_course_material` can then retrieve file-backed topics and extract PDF/text content.

## Calendar/due endpoint behavior

UGent supports the Brightspace `myEvents` and `myItems/due` endpoints. Earlier 400/403 failures during development were caused by incorrect/overbroad org-unit selection, not by UGent disabling these APIs.

## Regression fixtures

The test suite keeps synthetic examples of these compatibility rules. Live-account validation should never be required for ordinary CI, and private course/grade content must not be committed as fixtures.
