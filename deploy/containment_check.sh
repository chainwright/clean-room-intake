#!/bin/sh
# Day-1 evidence for the README: each wall checked on the VM, output saved to docs/containment_check.txt.
IMG=cleanroom-runner:1
F="--runtime=runsc --network=none --read-only --tmpfs /tmp:size=64m --cpus=1 --memory=512m --memory-swap=512m --pids-limit=128 --cap-drop=ALL --security-opt=no-new-privileges --user 65534:65534"
run() { echo "## $1"; shift; timeout 40 docker run --rm $F $IMG "$@" 2>&1 | tail -3; echo "exit=$?"; echo; }
{
  date -u
  run "gVisor kernel" sh -c 'dmesg | head -2'
  run "network" python3 -c "import urllib.request;urllib.request.urlopen('https://example.com',timeout=5)"
  run "environment (no secrets)" sh -c 'env | grep -ci key || true'
  run "read-only root" sh -c 'echo x > /x'
  run "memory cap" python3 -c "a='x'*10**10"
  run "pids cap" python3 -c "import os
for i in range(500): os.fork()"
  echo "## leftovers"; docker ps -a --filter name=cr- --format '{{.Names}}' | wc -l
} | tee docs/containment_check.txt
