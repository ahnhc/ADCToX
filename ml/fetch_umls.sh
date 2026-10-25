#!/usr/bin/env bash
# Download and unpack the UMLS Metathesaurus with your own UTS licence (needed by ml/umls_build.py).
#
#   bash ml/fetch_umls.sh [release] [folder]      # defaults: 2026AA, /data/hyeongchanahn/adctox/raw/umls
#
# NLM's server cannot resume, so a cut-off download (.partial) starts again from zero; network errors are retried that way.
# Asks for the UTS API key (UTS -> My Profile) without showing it, and passes it to curl on stdin, so it is not on the screen,
# in the shell history, or in the process list. Nothing here is committed: UMLS content is licensed.
set -euo pipefail
REL="${1:-2026AA}"; DIR="${2:-/data/hyeongchanahn/adctox/raw/umls}"
ZIP="umls-${REL}-metathesaurus-full.zip"
mkdir -p "$DIR"; cd "$DIR"
if [ ! -s "$ZIP" ]; then
  rm -f "$ZIP.partial"
  read -rsp "UTS API key: " KEY; echo
  printf 'url = "https://uts-ws.nlm.nih.gov/download?url=https://download.nlm.nih.gov/umls/kss/%s/%s&apiKey=%s"\noutput = "%s.partial"\nlocation\nfail\nretry = 5\nretry-all-errors\nretry-delay = 10\n' \
    "$REL" "$ZIP" "$KEY" "$ZIP" | curl -K - --progress-bar
  unset KEY
  mv "$ZIP.partial" "$ZIP"
fi
unzip -tq "$ZIP" >/dev/null && echo "zip ok"
unzip -oq "$ZIP" -d "$DIR"
ls -d "$DIR"/*/META && ls -la "$DIR"/*/META/MRCONSO.RRF "$DIR"/*/META/MRSTY.RRF
touch "$DIR/.fetched"; echo "done: $DIR"
