#!/bin/sh
# Each wall checked with the exact flags the app uses; output saved as evidence (docs/containment_check.txt).
IMG=cleanroom-runner:1
F="--runtime=runsc --network=none --read-only --tmpfs /tmp:size=64m --cpus=1 --memory=512m --memory-swap=512m --pids-limit=128 --cap-drop=ALL --security-opt=no-new-privileges --user 65534:65534"
run() {
  name="$1"; shift
  echo "## $name"
  out=$(perl -e "alarm 60; exec @ARGV" docker run --rm $F $IMG "$@" 2>&1); code=$?
  echo "$out" | tail -4
  echo "exit=$code"; echo
}
{
  echo "# containment check · $(date -u +%Y-%m-%dT%H:%MZ) · $(uname -sm) · runsc $(runsc --version 2>/dev/null | head -1 | awk '{print $3}')"
  echo
  run "kernel (gVisor)" sh -c 'dmesg | head -1'
  run "network" python3 -c "
import socket
try:
    socket.create_connection(('example.com', 443), timeout=5); print('CONNECTED')
except OSError as e: print('blocked:', type(e).__name__, e)"
  run "environment of the container (names only)" sh -c 'env | cut -d= -f1 | sort | tr "\n" " "'
  run "write to the root filesystem" sh -c 'echo x > /x && echo WROTE || echo "read-only: refused"'
  run "memory cap (try to allocate 1 GB)" python3 -c "
a = bytearray(1024**3); print('ALLOCATED 1 GB')"
  run "process cap (start 500 sleeping processes)" python3 -c "
import subprocess
ok = 0
for i in range(500):
    try:
        subprocess.Popen(['sleep', '30']); ok += 1
    except OSError as e:
        print('stopped after', ok, 'processes:', e); break
else:
    print('started all 500')"
  run "privileges" sh -c 'id; cat /proc/self/status | grep -E "^Cap(Eff|Prm)"'
  echo "## leftovers after all runs"
  echo "containers: $(docker ps -aq | wc -l | tr -d ' ')"
} | tee docs/containment_check.txt
