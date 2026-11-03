#!/bin/bash
# ProFluency: stops the OLD Mac doing the hub Mac's jobs, once the new hub Mac is set up and working.
#
# Run it from Terminal on the old Mac with:
#   bash <(curl -fsSL https://raw.githubusercontent.com/cjgraham-hue/profluency-autopost/main/tools/retire-old-mac.sh)
#
# It switches off this Mac's posting timer and stops its posting runner, so only the hub Mac starts and runs
# the jobs. It deletes no files: ~/profluency-runner and ~/profluency-timer stay where they are, and running
# setup-mac-runner.sh and setup-mac-timer.sh again would bring this Mac back.

set -uo pipefail
LABEL="uk.co.profluency.post-timer"

echo "Switching off this Mac's ProFluency jobs."

if launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then
  launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || launchctl unload "$HOME/Library/LaunchAgents/$LABEL.plist" >/dev/null 2>&1
fi
if [ -f "$HOME/Library/LaunchAgents/$LABEL.plist" ]; then
  mv "$HOME/Library/LaunchAgents/$LABEL.plist" "$HOME/profluency-timer/$LABEL.plist.off" 2>/dev/null || true
fi
echo "Posting timer: off."

if [ -x "$HOME/profluency-runner/svc.sh" ]; then
  (cd "$HOME/profluency-runner" && ./svc.sh stop >/dev/null 2>&1; ./svc.sh uninstall >/dev/null 2>&1)
  echo "Posting runner: stopped. (The hub Mac has taken over its place on GitHub.)"
else
  echo "Posting runner: not on this Mac."
fi

echo
echo "Done. This Mac no longer posts or runs the hub's jobs. In the Claude app on this Mac, turn off"
echo "Require this computer on any scheduled task that still has it, so it runs on the hub Mac instead."
