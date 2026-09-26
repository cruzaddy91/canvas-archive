# Resume here (session paused 2026-09-26, single-project focus elsewhere)

Nothing changed in this project since the 2026-09-23 checkpoint, verified
clean again today: tool repo and all 21 course-extract repos under
`~/Workspace/school/canvas-extracts/` are at 0 uncommitted changes, 0
commits ahead of origin, no background processes running. This file
replaces the old dated resume note (same idea, refreshed).

## The clock this project runs on

The Canvas access token is valid for 90 days from issuance. As of today
(2026-09-26) that clock is running but not urgent, there is real slack
right now. Do not let that slack turn into procrastination, an expired
token mid-extraction is exactly the scare that started this whole
project. Re-check the actual expiration date early in the next session
rather than assuming "still fine."

## What's done

1. Repo restructured to the workspace's python-service convention
   (exemplar: `portfolio/career-pipeline-api`). Bronze -> Silver, 63
   tests, ruff, CI, CodeQL, Dependabot, Makefile, `.repo-archetype.yml`.
   One item (`releases`) short of Gold.
2. 12 of the priority courses extracted and pushed (CMPT 307/311/322/
   351/352/355, DATA 220/350/360/370, MATH 210, WCSAM 203). CMPT 215
   tried and dropped, genuinely 0 assignments on Canvas.
3. Built `course_home_row_text_context` in `course_home_table.py`, a
   reusable capability that merges a matched schedule row's own text
   into an assignment's `.md` when the Assignments cell has no
   downloadable file. Ships with three opt-in fallbacks: a stale-link
   safety check, `course_home_row_numeric_match`, and
   `course_home_assignments_column_header`. This fixed three distinct
   failure modes across Jingsai Liang's courses (CMPT 311, DATA 220,
   DATA 360, DATA 370) with one general mechanism instead of
   course-by-course patches.
4. Fixed a real integrity bug in `extractors/external_site.py`:
   `js_render_fallback`'s headless-Chrome fetch was trusting any
   non-empty rendered HTML as success, including a rendered 403
   "Forbidden" page. Now checks the real HTTP status before Chrome ever
   launches.
5. Kathy Lenth's remaining 3 courses (322, 352, 355) audited read-only,
   confirmed already complete or genuinely empty on Canvas itself. No
   new profile needed.

## Two things left open, in recommended order

1. **The 8 unattempted courses**, not yet touched at all: CMPT 385,
   CMPT 390, DATA 110, DATA 470, GEOL 205, OEL 151, OEL 155, SOC 105.
   These were deliberately deprioritized during the original triage,
   not checked and found unimportant. Recommended first step: a quick
   pass confirming which of these actually matter before spending
   extraction effort, since some may be electives not worth archiving.
   This is the one item with real time pressure (the 90-day token),
   everything else on this list is not time-boxed.
2. **Comprehensive testing-library decision**, deliberately lower
   priority, no deadline. Open question: `responses` vs `vcrpy` for
   HTTP-level mocking of the Canvas API and instructor sites, layered
   on top of the pure-logic tests already in `tests/`. Never confirmed,
   never started.

## Exact next step

Ask which of the 8 remaining courses actually matter, then extract
the ones that do. Only move to the testing-library decision after
that, or whenever there's a natural lull, it has no deadline pressure
of its own.

## Verify state yourself

```bash
cd ~/Workspace/portfolio/canvas-archive && make test && make lint
cd ~/Workspace/portfolio/canvas-archive && uv run canvas-archive list
```

Every repo (tool + all 21 course archives) should show 0 uncommitted
changes and 0 commits ahead of origin.
