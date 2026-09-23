# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Test suite (`tests/`, pytest) covering slug/markdown formatting, profile
  loading, strategy dispatch, `is_initial_archive`, the new empty-extraction
  check, and the new Chrome-render fallback.
- CI (`.github/workflows/ci.yml`): lint + test on push/PR to `main`.
- CodeQL security scanning (`.github/workflows/codeql.yml`), weekly plus
  push/PR.
- Dependabot (`.github/dependabot.yml`) for `pip` and `github-actions`.
- Ruff lint configuration and a `dev` extras group (`pytest`, `ruff`).
- `Makefile` (`install`, `test`, `lint`, `clean`).
- `SECURITY.md`, documenting the Canvas token, GitHub token delegation via
  `gh auth token`, and the Terraform state this tool actually depends on.
- `.repo-archetype.yml`, declaring `python-service` explicitly rather than
  leaving it to auto-detection.
- `js_render_fallback` on `external_site` profiles: when the wget mirror
  finds no course root, the extractor now falls back to fetching each
  matched candidate URL through headless Chrome, converting the rendered DOM
  the same way every other content path in this codebase does. Replaces the
  standalone, single-course `scripts/render_chrome_pages.sh`.
- `verify_not_empty`: the post-extract verification step now fails loudly if
  a run wrote zero assignment files, instead of reporting success on an
  empty extraction.

### Changed

- `cmpt-328-comp-arch` profile: sets `js_render_fallback: true` instead of
  pointing at the retired manual script in a comment.
- Commit attribution in `git_ops.commit_if_changes` updated to the current
  model name.

### Removed

- `scripts/render_chrome_pages.sh`, superseded by the integrated
  `js_render_fallback` path in `extractors/external_site.py`.
