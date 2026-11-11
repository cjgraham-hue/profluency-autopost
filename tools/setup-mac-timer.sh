#!/bin/bash
# ProFluency autopost: a timer on this Mac that starts the posting job every 15 minutes.
#
# GitHub's own timer for the Instagram autopost workflow is best effort: since 29 Oct 2026 it has often started
# the job only 3 or 4 times a day, so posts went out hours late or were skipped. This adds a small background
# timer (a macOS LaunchAgent) that asks GitHub to run the workflow at 02, 17, 32 and 47 minutes past each hour
# from 07:02 to 21:47, Mac time. The job itself still runs on the runner, exactly as before; the runner isn't
# touched, and GitHub's own timer stays as a backup. If the Mac is asleep at one of those times, the timer
# fires once when it wakes.
#
# Run it from Terminal with:
#   bash <(curl -fsSL https://raw.githubusercontent.com/cjgraham-hue/profluency-autopost/main/tools/setup-mac-timer.sh)
#
# It needs the GitHub command-line tool (gh), signed in to the account that owns the repository. You do that
# sign-in yourself in the browser; this script never asks for or saves a password or token. Safe to run again.
#
# What it writes:
#   ~/profluency-timer/start-posting.sh                       asks GitHub to start the posting job
#   ~/Library/LaunchAgents/uk.co.profluency.post-timer.plist  the timer
#   ~/Library/Logs/profluency-post-timer.log                  one line each time it runs
# To remove it:
#   launchctl bootout gui/$(id -u)/uk.co.profluency.post-timer; rm ~/Library/LaunchAgents/uk.co.profluency.post-timer.plist

set -euo pipefail

REPO="cjgraham-hue/profluency-autopost"
LABEL="uk.co.profluency.post-timer"
DIR="$HOME/profluency-timer"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/profluency-post-timer.log"

say() { printf '\n%s\n' "$*"; }

say "Setting up the ProFluency posting timer on this Mac."

# 1. The GitHub command-line tool.
GH=$(command -v gh || true)
for p in /opt/homebrew/bin/gh /usr/local/bin/gh; do [ -z "$GH" ] && [ -x "$p" ] && GH="$p"; done
if [ -z "$GH" ]; then
  say "The GitHub command-line tool (gh) isn't on this Mac yet. Install it, then run this script again:"
  echo "  with Homebrew:  brew install gh"
  echo "  or download the macOS installer from https://cli.github.com"
  exit 1
fi
echo "Found gh at $GH."

# 2. Signed in to GitHub (you do this yourself, in the browser).
if ! "$GH" auth status --hostname github.com >/dev/null 2>&1; then
  say "gh isn't signed in to GitHub yet. Run this, choose to log in with a web browser, and finish in the browser:"
  echo "  $GH auth login --hostname github.com --git-protocol https --web"
  echo "Then run this script again."
  exit 1
fi
if ! "$GH" workflow view autopost.yml -R "$REPO" >/dev/null 2>&1; then
  say "gh is signed in, but it can't see the Instagram autopost workflow in $REPO."
  echo "Sign in with the GitHub account that owns the repository (run: $GH auth login --web), then run this script again."
  exit 1
fi
echo "gh is signed in and can see the Instagram autopost workflow."

# 3. The script the timer runs.
mkdir -p "$DIR" "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
cat > "$DIR/start-posting.sh" <<SH
#!/bin/bash
# Started by the ProFluency posting timer. Asks GitHub to run the Instagram autopost workflow (mode "post"),
# unless a run is already waiting or running. The workflow only posts what is due, so an extra start is harmless.
# At 02 past every other hour (07:02, 09:02 … 21:02) it also starts the hub sync in the website repository,
# because GitHub's own two-hourly timer for it often skips runs.
REPO="$REPO"
SITE="cjgraham-hue/profluency"
GH="$GH"
stamp() { date '+%Y-%m-%d %H:%M'; }
# A run counts as busy only if it was created in the last 30 minutes: GitHub sometimes leaves a run stuck as
# "queued" for good, and that mustn't stop posting.
busy=\$("\$GH" run list -R "\$REPO" -w autopost.yml -L 5 --json status,createdAt --jq '[.[] | select(.status != "completed") | select((now - (.createdAt | fromdateiso8601)) < 1800)] | length' 2>&1) \\
  || { echo "\$(stamp) couldn't reach GitHub: \$busy"; exit 0; }
if [ "\$busy" != "0" ]; then echo "\$(stamp) a posting run is already waiting or running"
elif out=\$("\$GH" workflow run autopost.yml -R "\$REPO" -f mode=post 2>&1); then
  echo "\$(stamp) started the posting job"
else
  echo "\$(stamp) couldn't start the posting job: \$out"
fi
hour=\$((10#\$(date +%H))); minute=\$((10#\$(date +%M)))
if [ \$((hour % 2)) -eq 1 ] && [ "\$minute" -lt 15 ]; then
  syncing=\$("\$GH" run list -R "\$SITE" -w hub-sync.yml -L 5 --json status,createdAt --jq '[.[] | select(.status != "completed") | select((now - (.createdAt | fromdateiso8601)) < 1800)] | length' 2>/dev/null || echo 1)
  if [ "\$syncing" = "0" ] && out=\$("\$GH" workflow run hub-sync.yml -R "\$SITE" 2>&1); then
    echo "\$(stamp) started the hub sync"
  elif [ "\$syncing" != "0" ]; then
    echo "\$(stamp) a hub sync is already waiting or running"
  else
    echo "\$(stamp) couldn't start the hub sync: \$out"
  fi
fi
# keep the log short
if [ -f "$LOG" ] && [ "\$(wc -l < "$LOG")" -gt 3000 ]; then tail -n 1500 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"; fi
SH
chmod +x "$DIR/start-posting.sh"

# 4. The timer: 02, 17, 32 and 47 minutes past each hour, 07:02 to 21:47.
{
  echo '<?xml version="1.0" encoding="UTF-8"?>'
  echo '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">'
  echo '<plist version="1.0"><dict>'
  echo "  <key>Label</key><string>$LABEL</string>"
  echo "  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$DIR/start-posting.sh</string></array>"
  echo '  <key>StartCalendarInterval</key><array>'
  for h in $(seq 7 21); do
    for m in 2 17 32 47; do
      echo "    <dict><key>Hour</key><integer>$h</integer><key>Minute</key><integer>$m</integer></dict>"
    done
  done
  echo '  </array>'
  echo "  <key>StandardOutPath</key><string>$LOG</string>"
  echo "  <key>StandardErrorPath</key><string>$LOG</string>"
  echo '</dict></plist>'
} > "$PLIST"
plutil -lint "$PLIST" >/dev/null

# 5. Load it (replacing an older copy).
launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null || launchctl load -w "$PLIST"

say "Done. The timer is on."
echo "It asks GitHub to start the posting job at 02, 17, 32 and 47 minutes past each hour, 07:02 to 21:47,"
echo "and the hub sync at 07:02, 09:02 and every two hours after, to 21:02."
echo "Each start is logged in $LOG. After the next quarter hour you should see a line like"
echo "'started the posting job' there, and a new run under Actions › Instagram autopost on GitHub."
echo "Keep the Mac on, plugged in and awake from 7am to 10pm, as before."
