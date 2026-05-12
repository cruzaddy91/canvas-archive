#!/usr/bin/env bash
# Headless-Chrome enrichment for instructor sites that build tables and
# problems via JavaScript at runtime (canvas-archive's default wget mirror
# captures only the empty JS stubs from such pages).
#
# For every Homework {N}.{M}.md file in TARGET_DIR, fetches the matching
# `${BASE_URL}homework{N}.{M}` page via headless Chrome, runs the rendered
# DOM through pandoc, and replaces the md file with a clean
# `# Homework {N}.{M}` + Source link + body. Em dashes are scrubbed.
#
# Usage:
#   scripts/render_chrome_pages.sh <base_url> <target_homework_dir>
# Example:
#   scripts/render_chrome_pages.sh \
#     https://cs.westminsteru.edu/~kathy/2026spring/cmpt328/ \
#     ~/Workspace/school/CMPT-328_CompArchitec/assignments/Homework
set -euo pipefail

BASE_URL="${1:-}"
TARGET_DIR="${2:-}"

if [[ -z "${BASE_URL}" || -z "${TARGET_DIR}" ]]; then
  echo "usage: $0 <base_url> <target_homework_dir>" >&2
  exit 2
fi

CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
if [[ ! -x "${CHROME}" ]]; then
  echo "Chrome not found at ${CHROME}. Set CHROME env var to override." >&2
  exit 1
fi
if ! command -v pandoc >/dev/null 2>&1; then
  echo "pandoc not found on PATH" >&2
  exit 1
fi

BASE_URL="${BASE_URL%/}/"
shopt -s nullglob
count=0

for md_file in "${TARGET_DIR}"/Homework\ *.md; do
  basename=$(basename "${md_file}" .md)
  version="${basename#Homework }"
  if [[ ! "${version}" =~ ^[0-9]+\.[0-9]+$ ]]; then
    continue
  fi
  url="${BASE_URL}homework${version}"
  tmp_dom="$(mktemp -t hw_${version}_dom.XXXX.html)"
  "${CHROME}" --headless=new --disable-gpu --virtual-time-budget=6000 \
    --dump-dom "${url}" 2>/dev/null > "${tmp_dom}"
  body_md=$(pandoc -f html -t gfm-raw_html "${tmp_dom}")
  {
    printf "# Homework %s\n\n" "${version}"
    printf "*Source: [%s](%s)*\n\n" "${url}" "${url}"
    printf "%s\n" "${body_md}"
  } > "${md_file}"
  # Em dashes are forbidden in workspace markdown; substitute colon for the
  # common " — " label form and a hyphen otherwise.
  sed -i '' 's/ — /: /g; s/—/-/g' "${md_file}"
  rm -f "${tmp_dom}"
  lines=$(wc -l < "${md_file}" | tr -d ' ')
  echo "  enriched: ${md_file} (${lines} lines)"
  count=$((count + 1))
done

if [[ ${count} -eq 0 ]]; then
  echo "no Homework N.M.md files found under ${TARGET_DIR}" >&2
  exit 1
fi
echo "done: ${count} file(s)"
