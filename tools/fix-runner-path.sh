#!/bin/bash
# ProFluency: points the posting runner at the Mac's own up-to-date tools.
#
# Some Macs have old copies of git (2.18 from 2018) and Python in /usr/local/bin, left by old installers. When those
# come first on the runner's path, every job fails at "Fetching the repository" with "RPC failed; HTTP 400 ...
# expected flush after ref listing". This sets the runner's path to Apple's own git first (and python.org's
# Python 3.12, if it's installed), keeps gh, and restarts the runner. It deletes nothing.
#
# Run it from Terminal with:
#   bash <(curl -fsSL https://raw.githubusercontent.com/cjgraham-hue/profluency-autopost/main/tools/fix-runner-path.sh)

set -uo pipefail
cd "$HOME/profluency-runner" 2>/dev/null || { echo "There's no runner folder at ~/profluency-runner."; exit 1; }
P="/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin"
PYDIR="/Library/Frameworks/Python.framework/Versions/3.12/bin"
[ -x "$PYDIR/python3" ] && P="$PYDIR:$P"
./svc.sh stop >/dev/null 2>&1
printf '%s' "$P" > .path
./svc.sh start >/dev/null 2>&1
echo "The runner now uses: $(PATH="$P" git --version), $(PATH="$P" python3 --version 2>&1), gh at $(PATH="$P" command -v gh || echo 'not found')."
sleep 4
if ./svc.sh status 2>/dev/null | grep -qi started; then
  echo "Runner restarted. The next posting run (every 15 minutes) should go green."
else
  echo "The runner didn't restart. Copy what's above and send it to Claude."
fi
