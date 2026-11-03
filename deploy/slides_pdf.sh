#!/bin/sh
# docs/slides.html → docs/slides.pdf (16:9) with headless Chrome/Chromium.
CHROME="${CLEANROOM_CHROME:-chromium}"
cd "$(dirname "$0")/../docs" && "$CHROME" --headless=new --disable-gpu --no-pdf-header-footer \
  --user-data-dir=/tmp/cr-slides --print-to-pdf="$PWD/slides.pdf" "file://$PWD/slides.html"
