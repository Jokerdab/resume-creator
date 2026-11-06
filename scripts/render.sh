#!/usr/bin/env bash
# Usage: bash scripts/render.sh path/to/resume.html [more.html ...]
# Renders each HTML to a PDF next to it and prints the page count (must be 2).
set -euo pipefail

find_chrome() {
  for c in \
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
    "/Applications/Chromium.app/Contents/MacOS/Chromium" \
    "$(command -v google-chrome 2>/dev/null || true)" \
    "$(command -v chromium 2>/dev/null || true)" \
    "$(command -v chromium-browser 2>/dev/null || true)" \
    "/c/Program Files/Google/Chrome/Application/chrome.exe"; do
    [ -n "$c" ] && [ -x "$c" ] && { echo "$c"; return; }
  done
  echo "Chrome or Chromium not found" >&2; exit 1
}

CHROME="$(find_chrome)"

for html in "$@"; do
  abs="$(cd "$(dirname "$html")" && pwd)/$(basename "$html")"
  pdf="${abs%.html}.pdf"
  # Chrome sometimes keeps an old PDF instead of overwriting it
  rm -f "$pdf"
  "$CHROME" --headless --disable-gpu --no-pdf-header-footer --print-to-pdf="$pdf" "file://$abs" 2>/dev/null
  pages="$(python3 -c "import re,sys;print(len(re.findall(rb'/Type\s*/Page[^s]',open(sys.argv[1],'rb').read())))" "$pdf")"
  status="OK"; [ "$pages" -gt 2 ] && status="TOO LONG: cut weak bullets"
  echo "$(basename "$pdf"): $pages pages — $status"
done
