# CMPT 328: external_site mirror and JavaScript-rendered pages

## Problem

The [cmpt-328-comp-arch profile](../profiles/cmpt-328-comp-arch.yaml) uses
`strategy: external_site`. The extractor mirrors the instructor `base_url`
with `wget`, then matches Canvas assignment titles to paths under that mirror.

Some homework HTML (notably Kathy’s pages referenced in the profile) **builds
tables and prompts in the browser with JavaScript**. `wget` only saves the
initial HTML shell, so Markdown conversion can look **empty or thin** compared
to what you see in Chrome.

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

The extractor now prints a **`[diag] GET ... -> HTTP ...`** line when the
mirror is empty and the course root cannot be resolved, so you can see the
status without a separate `curl` run.

## Workarounds

1. **Manual or scripted headless render**  
   After a normal `canvas-archive run`, open the worst pages in a browser,
   confirm they need JS, then replace the mirrored stubs with fully rendered
   HTML (or exported PDF) using a **trusted local script** you control. The
   profile comment historically pointed at `scripts/render_chrome_pages.sh`;
   that script is **not shipped in this repo** today. If you add one, keep it
   next to the profile and document the exact command line here.

2. **Tighten `assignment_patterns`**  
   When Canvas titles change spacing or punctuation, extend the regex or
   `candidates` ladder in the profile so the mirror path resolves. Run
   `uv run canvas-archive run 3596470` and inspect
   `enriched N assignments from external site` in the log.

3. **Prefer `canvas_only` extras when Canvas also exposes starters**  
   If the instructor later puts PDFs or files in Canvas, you can merge
   additional profile flags (for example `download_linked_canvas_files`)
   without replacing the external_site mirror.

## UAT checklist (328)

- [ ] `uv run canvas-archive run 3596470` completes; note `enriched` and
  `copied starter` counts. If `wget` exits non-zero and `mirrored 0 files`,
  fix TLS, robots, or `base_url` before expecting content (2026-05-14 UAT saw
  exit 8 and empty mirror).
- [ ] Spot-check two homework `.md` files under the extract tree for readable
  problem text.
- [ ] If stubs are empty, run your headless render pass and re-run verify, or
  attach PDFs manually and document in the archive README for that course
  repo.
