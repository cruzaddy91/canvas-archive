# Course profiles

Per-course config for the canvas-archive pipeline. One YAML file per course where the prof's content layout differs from the default (Canvas description fields). Courses without a profile file default to the `canvas_only` strategy.

## Schema

```yaml
canvas_id: <int>            # Canvas course id (required, identifies the profile)
slug_kebab: <str>           # repo name suffix: canvas-archive-<slug_kebab>
slug_camel: <str>           # local dir name under ~/Workspace/school/canvas-extracts/
strategy: canvas_only | external_site

# Required when strategy == external_site:
external_site:
  base_url: https://...     # prof's site root (passed to wget --recursive --no-parent)
  assignment_patterns:
    - regex: "^lab(\\d+)$"  # matched against lowercased assignment name
      candidates:           # tried in order; {n} = first regex group
        - "labs/lab{n}/index.html"
        - "labs/lab{n}/lab{n}.pdf"
      starters:             # optional; binary files copied alongside the .md
        - "labs/lab{n}/lab{n}.tar"
  handouts_dir: handouts    # optional; subdir of base_url with explainer pages
```

Filename = `<canvas_id>-<slug_kebab>.yaml` is conventional but only `canvas_id` matters for matching.
