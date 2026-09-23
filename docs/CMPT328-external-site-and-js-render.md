# CMPT 328: external_site mirror and JavaScript-rendered pages

## Problem

The [cmpt-328-comp-arch profile](../profiles/cmpt-328-comp-arch.yaml) uses
`strategy: external_site`. The extractor mirrors the instructor `base_url`
with `wget`, then matches Canvas assignment titles to paths under that mirror.

Some homework HTML (notably Kathy's pages referenced in the profile) **builds
tables and prompts in the browser with JavaScript**. `wget` only saves the
initial HTML shell, so the mirror comes back empty and `course root` cannot
be located (2026-05-14 UAT: `wget` exited 8, mirrored 0 files).

## Troubleshooting: wget exit 8 and zero files

If the log shows **mirrored 0 files** and **could not locate course root**, run
this first (same host the profile uses):

```bash
curl -sS -o /dev/null -w '%{http_code}\n' \
  'https://cs.westminsteru.edu/~kathy/2026spring/cmpt328/'
```

**HTTP 403 Forbidden** means Apache is denying the request **before** any
mirror layout or JavaScript question. Typical causes: directory permissions,
the course tree not published yet, or access restricted to campus or VPN. A
browser on an allowed network may still open the site while `wget` and
`curl` fail the same way until the server allows anonymous reads (or you add an
approved export path).

**HTTP 404** usually means the path or semester folder changed: update
`external_site.base_url` in the profile after you confirm the live URL in a
browser.

The extractor prints a **`[diag] GET ... -> HTTP ...`** line when the mirror
is empty and the course root cannot be resolved, so you can see the status
without a separate `curl` run.

## Fix: `js_render_fallback`

Set `external_site.js_render_fallback: true` on the profile (already set for
this course). When the wget mirror comes back empty, the extractor falls
back to fetching each matched candidate URL directly through headless
Chrome (`--dump-dom`), which executes the page's JavaScript first, then runs
the rendered DOM through the same `to_md()` conversion every other content
path in this codebase uses. See
`extractors/external_site.py:_render_via_chrome` and
`_match_and_embed_via_chrome`.

This requires Chrome at the path in `$CHROME`, or the default macOS install
location. No other setup, and no separate script to remember to run: a plain
`uv run canvas-archive run 3596470` now falls back to the render automatically
whenever the mirror is empty. Assignment content still fetched via wget on
other profiles is untouched, since the fallback only engages when the mirror
already failed to find a course root.

Other options worth knowing, not needed for this course today:

- **Tighten `assignment_patterns`.** When Canvas titles change spacing or
  punctuation, extend the regex or `candidates` ladder in the profile so the
  mirror path resolves. Run `uv run canvas-archive run 3596470` and inspect
  `enriched N assignments` in the log.
- **Prefer `canvas_only` extras when Canvas also exposes starters.** If the
  instructor later puts PDFs or files in Canvas, merge additional profile
  flags (for example `download_linked_canvas_files`) without replacing the
  external_site mirror.

## UAT checklist (328)

- [ ] `uv run canvas-archive run 3596470` completes; note `enriched` count in
  the `[fallback]` line.
- [ ] Spot-check two homework `.md` files under the extract tree for readable
  problem text, not a near-empty stub.
- [ ] If a candidate still comes back empty, confirm the URL pattern in
  `assignment_patterns` actually matches the live page (open it in a
  browser), then re-run.
