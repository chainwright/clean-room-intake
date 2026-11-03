#!/bin/sh
# Control for the process cap: the break-in flood in a normal room (pids 128) and in one with the cap raised to 1000.
# Same image, same walls otherwise. Output saved as evidence: docs/flood_cap_control.txt
set -u
W=$(mktemp -d /tmp/cr-ctl-XXXX); cp sandbox/runner.py sandbox/netlog.py "$W"/; cp sandbox/breakin.py "$W"/step.py
printf flood > "$W"/file; chmod 755 "$W"; chmod 444 "$W"/*
for cap in 128 1000; do
  out=$(docker run --rm --runtime=runsc --network=none --read-only --tmpfs=/tmp:size=64m --memory=512m --memory-swap=512m \
        --cpus=1 --pids-limit=$cap --cap-drop=ALL --security-opt=no-new-privileges --user=65534:65534 -v "$W":/in:ro \
        cleanroom-runner:1 python3 -I /in/runner.py 2>&1); code=$?
  forks=$(printf '%s\n' "$out" | grep -c '"os.fork"')
  last=$(printf '%s\n' "$out" | grep '"probe"' | tail -1 | sed 's/.*"outcome": "\([^"]*\)".*/\1/')
  echo "pids-limit=$cap  exit=$code  forks_recorded=$forks  last_word_from_inside=\"$last\""
done
rm -rf "$W"
