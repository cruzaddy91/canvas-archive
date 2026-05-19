# Scratch: canvas extract UAT wave (202 / 306 / 328) and CMPT 328 status

**Ephemeral.** Delete this file after the UAT story is closed or its facts are
merged into [profiles/README.md](../profiles/README.md),
[UAT-wave-202-306-328.md](UAT-wave-202-306-328.md), and
[CMPT328-external-site-and-js-render.md](CMPT328-external-site-and-js-render.md).

## What we did so far (this repo version)

- **Adaptive starter resolution wave (202 / 306 / 328):** Documented staged
  `canvas_only` flow, memoization boundaries, production vs `developer_mode`,
  and UAT checklists under `profiles/` and `docs/`.
- **Lockdown:** `validate_profile_security_flags` rejects
  `course_home_external_starters_allow_any_https_host` when `developer_mode` is
  not true; pipeline calls it after profile load.
- **`canvas_only`:** Named stage helpers, optional
  `dedupe_external_download_urls`, and extract logs include stage counters for
  dashboards.
- **`external_site`:** When the mirror is empty and the course root cannot be
  found, logs a **`[diag] GET <base_url> -> HTTP …`** line (same User-Agent as
  `wget`) so failures are easier to read than “exit 8” alone.
- **CMPT 328:** Confirmed **`base_url` can return HTTP 403** for anonymous
  `curl` / `wget`. Treating that as acceptable means **no external mirror** for
  that run: Canvas-only `.md` still land; enrich is skipped by design.

## UAT snapshot (carry into the next doc update if needed)

| Course | External enrich | Notes |
| :-- | :-- | :-- |
| CMPT 202 | N/A (`canvas_only`) | Ran with production-style flags; verify OK. |
| CMPT 306 | Yes (`external_site`) | Mirror and patterns worked; verify OK. |
| CMPT 328 | No | 403 on `base_url`; empty mirror; enrich skipped. |

## Possible next moves (this UAT version)

1. **328 access:** If you need mirrored homework bodies, try **campus VPN** or
   confirm with the instructor whether **`base_url` should be public**. If 403
   stays, keep relying on Canvas-only output or manual exports.
2. **Profile:** Update `external_site.base_url` only when you have a **live,
   anonymously readable** directory (or accept no enrich).
3. **Thin prompts after a successful mirror:** Use the JS-render / headless path
   described in [CMPT328-external-site-and-js-render.md](CMPT328-external-site-and-js-render.md).
4. **Optional automation:** Local verify script (host allowlist grep), CI
   `canvas-archive run` when secrets exist, or wiring
   `starter_resolution_order` if a course truly needs reordering (still
   documented as future-facing today).
5. **Housekeeping:** After merging the above into permanent docs, **delete this
   file** so scratch notes do not accumulate.
