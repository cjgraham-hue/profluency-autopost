#!/bin/bash
# ProFluency: repairs the posting runner on this Mac when its jobs fail with
# "externals/node24/bin/node ... No such file or directory" (part of the runner's own files has gone missing,
# usually after an interrupted self-update). It downloads GitHub's runner again over the same folder and restarts
# it. The runner's connection to GitHub (.runner and .credentials) is kept, so nothing needs pasting.
#
# Run it from Terminal with:
#   bash <(curl -fsSL https://raw.githubusercontent.com/cjgraham-hue/profluency-autopost/main/tools/repair-mac-runner.sh)

set -uo pipefail
DIR="$HOME/profluency-runner"
cd "$DIR" 2>/dev/null || { echo "There's no runner folder at $DIR on this Mac."; exit 1; }
[ -f ./.runner ] || { echo "The runner here isn't connected to GitHub. Run tools/setup-mac-runner.sh instead."; exit 1; }
case "$(uname -m)" in arm64) ARCH=arm64 ;; x86_64) ARCH=x64 ;; *) echo "Unsupported processor."; exit 1 ;; esac

VER=$(curl -fsSL https://api.github.com/repos/actions/runner/releases/latest \
      | python3 -c 'import json, sys; print(json.load(sys.stdin)["tag_name"].lstrip("v"))') \
  || { echo "Couldn't reach GitHub. Check the internet connection and run this again."; exit 1; }

echo "Stopping the runner..."
./svc.sh stop >/dev/null 2>&1 || true
echo "Downloading GitHub's runner $VER for $ARCH..."
rm -rf ./_update
if ! curl -fsSL -o runner.tar.gz "https://github.com/actions/runner/releases/download/v${VER}/actions-runner-osx-${ARCH}-${VER}.tar.gz"; then
  echo "The download didn't work. Run this again."; ./svc.sh start >/dev/null 2>&1; exit 1
fi
tar xzf runner.tar.gz && rm -f runner.tar.gz
echo "Starting the runner..."
./svc.sh start >/dev/null 2>&1 || { ./svc.sh install >/dev/null 2>&1; ./svc.sh start >/dev/null 2>&1; }

if ls ./externals/node*/bin/node >/dev/null 2>&1 && ./svc.sh status 2>/dev/null | grep -qi started; then
  echo
  echo "Repaired. The runner is back with all its files. The next posting run (every 15 minutes) should go green,"
  echo "and anything due in the last 12 hours still goes out."
else
  echo
  echo "Something still isn't right. Copy what's above and send it to Claude."
fi
