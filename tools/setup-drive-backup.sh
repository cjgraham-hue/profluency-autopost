#!/bin/bash
# ProFluency: a nightly backup on the hub Mac that copies every month's social media into Google Drive.
#
# Run it from Terminal on the hub Mac with:
#   bash <(curl -fsSL https://raw.githubusercontent.com/cjgraham-hue/profluency-autopost/main/tools/setup-drive-backup.sh)
#
# Every night at 03:47 it updates a light copy of this repository's media (no history, only docs/media, docs/pins,
# docs/backup/ and the plan files) and copies anything new into Drive's "Social media backup", by year then month:
#   Social media backup/2026/12 December/Media      pictures and videos from docs/media
#   Social media backup/2026/12 December/Pins       pin pictures from docs/pins/2026-12
#   Social media backup/2026/12 December/InDesign   IDML files and other sources from docs/backup/2026-12
#   Social media backup/2026/12 December/captions 2026-12.json   every post's caption and time for that month
# It only adds and updates files: it never deletes anything in Drive. Google Drive for desktop uploads them, with no
# size limit. The weekly media cleanup removes posted files from the repository a week after they go out; by then
# they're already in Drive, because a month lands here weeks before it posts.
#
# Needs Google Drive for desktop, signed in to the account that holds "Social media backup". Safe to run again.
#
# What it writes:
#   ~/profluency-hub-mac/drive-backup.sh                          the backup itself
#   ~/profluency-hub-mac/drive-backup.path                        where "Social media backup" is on this Mac
#   ~/profluency-hub-mac/media-mirror/                            the light copy of the repository's media
#   ~/Library/LaunchAgents/uk.co.profluency.drive-backup.plist    the nightly timer
#   ~/Library/Logs/profluency-drive-backup.log                    what each run copied
# To remove it:
#   launchctl bootout gui/$(id -u)/uk.co.profluency.drive-backup; rm ~/Library/LaunchAgents/uk.co.profluency.drive-backup.plist

set -uo pipefail

LABEL="uk.co.profluency.drive-backup"
HUB_DIR="$HOME/profluency-hub-mac"
SCRIPT="$HUB_DIR/drive-backup.sh"
PATHFILE="$HUB_DIR/drive-backup.path"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/profluency-drive-backup.log"

say() { printf '\n%s\n' "$*"; }
[ "$(uname)" = "Darwin" ] || { echo "This script is for a Mac."; exit 1; }
mkdir -p "$HUB_DIR" "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
say "Setting up the nightly Google Drive backup of ProFluency's social media."

# 1. Find "Social media backup" in Google Drive for desktop.
if [ ! -d "$HOME/Library/CloudStorage" ] || ! ls -d "$HOME"/Library/CloudStorage/GoogleDrive-* >/dev/null 2>&1; then
  say "Google Drive for desktop isn't set up on this Mac yet. Install it from https://www.google.com/drive/download/,"
  echo "sign in with the Google account that holds \"Social media backup\", then run this script again."
  exit 1
fi
DEST=""
for d in "$HOME"/Library/CloudStorage/GoogleDrive-*/"My Drive"/"Brand Logo Folders"/ProFluency/"ProFluency Social"/"ProFluency launch week - Instagram"/"Social media backup"; do
  [ -d "$d" ] && { DEST="$d"; break; }
done
if [ -z "$DEST" ]; then
  echo "Looking for \"Social media backup\" in Google Drive (this can take a minute)..."
  DEST=$(find "$HOME"/Library/CloudStorage/GoogleDrive-*/"My Drive" -maxdepth 7 -type d -name "Social media backup" 2>/dev/null | head -n 1)
fi
if [ -z "$DEST" ]; then
  say "Couldn't find a folder called \"Social media backup\" in Google Drive on this Mac. Check Google Drive for desktop"
  echo "is signed in to the right account and has finished starting up, then run this script again."
  exit 1
fi
printf '%s' "$DEST" > "$PATHFILE"
echo "Backing up to: $DEST"

# 2. The backup itself.
cat > "$SCRIPT" <<'SH'
#!/bin/bash
# The ProFluency nightly Drive backup (set up by tools/setup-drive-backup.sh). Adds and updates, never deletes.
set -uo pipefail
PATH="/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin"
HUB_DIR="$HOME/profluency-hub-mac"
MIRROR="$HUB_DIR/media-mirror"
URL="https://github.com/cjgraham-hue/profluency-autopost.git"
LOG="$HOME/Library/Logs/profluency-drive-backup.log"
MONTHS=(January February March April May June July August September October November December)
stamp() { date '+%Y-%m-%d %H:%M'; }
DEST=$(cat "$HUB_DIR/drive-backup.path" 2>/dev/null)
[ -n "$DEST" ] && [ -d "$DEST" ] || { echo "$(stamp) ✗ can't see Social media backup in Google Drive (is Google Drive for desktop running?)"; exit 1; }

# A light copy of the repository: no history, only the folders the backup needs.
if [ ! -d "$MIRROR/.git" ]; then
  rm -rf "$MIRROR"
  git clone -q --depth 1 --filter=blob:none --sparse "$URL" "$MIRROR" || { echo "$(stamp) ✗ couldn't copy the repository from GitHub"; exit 1; }
  git -C "$MIRROR" sparse-checkout set docs/media docs/pins docs/backup platforms >/dev/null 2>&1
fi
git -C "$MIRROR" fetch -q --depth 1 origin main && git -C "$MIRROR" reset -q --hard origin/main \
  || { echo "$(stamp) ✗ couldn't update from GitHub"; exit 1; }

copied=0; failed=0
month_dir() { local y=$1 m=$2; printf '%s/%s/%s %s' "$DEST" "$y" "$m" "${MONTHS[$((10#$m - 1))]}"; }
put() { # put SOURCE FOLDER: copy if missing or a different size (sizes only, so files Drive keeps online-only
  # aren't downloaded again to compare; the small caption files are compared in full)
  local src=$1 dir=$2 name; name=$(basename "$src")
  if [ -f "$dir/$name" ] && [ "$(stat -f %z "$src")" = "$(stat -f %z "$dir/$name")" ]; then
    case "$name" in *.json) cmp -s "$src" "$dir/$name" && return ;; *) return ;; esac
  fi
  if retry mkdir -p "$dir" && retry cp "$src" "$dir/$name"; then copied=$((copied + 1)); else failed=$((failed + 1)); fi
}
# Google Drive for desktop answers "Resource deadlock avoided" while it's still fetching a folder that's only online
# (an existing month folder, say). Looking at the folder makes it fetch it; then the same step works.
retry() {
  local i
  for i in 1 2 3 4 5 6; do
    "$@" 2>/dev/null && return 0
    ls "$DEST" "$DEST"/*/ "$dir" >/dev/null 2>&1
    sleep $((i * 2))
  done
  "$@"
}
for f in "$MIRROR"/docs/media/*; do
  [ -f "$f" ] || continue
  n=$(basename "$f"); [[ "$n" =~ ^([0-9]{4})-([0-9]{2})- ]] || continue
  put "$f" "$(month_dir "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}")/Media"
done
for d in "$MIRROR"/docs/pins/[0-9][0-9][0-9][0-9]-[0-9][0-9] "$MIRROR"/docs/backup/[0-9][0-9][0-9][0-9]-[0-9][0-9]; do
  [ -d "$d" ] || continue
  k=$(basename "$d"); sub=$([ "$(basename "$(dirname "$d")")" = "pins" ] && echo Pins || echo InDesign)
  while IFS= read -r -d '' f; do put "$f" "$(month_dir "${k%-*}" "${k#*-}")/$sub"; done < <(find "$d" -type f -print0)
done
# Each month's captions and times, from the posting schedule.
if [ -f "$MIRROR/schedule.json" ]; then
  tmp=$(mktemp -d)
  /usr/bin/python3 - "$MIRROR/schedule.json" "$tmp" <<'PY' || true
import json, sys, os
data = json.load(open(sys.argv[1]))
items = data.get("items", data) if isinstance(data, dict) else data
months = {}
for it in items:
    at = str(it.get("post_at", ""))
    if len(at) >= 7:
        months.setdefault(at[:7], []).append({k: it.get(k) for k in ("id", "post_at", "type", "media", "slides", "caption", "first_comment", "follow_up") if k in it})
for key, rows in months.items():
    with open(os.path.join(sys.argv[2], f"captions {key}.json"), "w") as fh:
        json.dump(sorted(rows, key=lambda r: r.get("post_at", "")), fh, ensure_ascii=False, indent=1)
PY
  for f in "$tmp"/captions\ *.json; do
    [ -f "$f" ] || continue
    k=$(basename "$f" .json); k=${k#captions }
    put "$f" "$(month_dir "${k%-*}" "${k#*-}")"
  done
  rm -rf "$tmp"
fi
if [ "$failed" -gt 0 ]; then echo "$(stamp) ✗ copied $copied, $failed couldn't be copied (is Google Drive for desktop running, with access allowed?)"
else echo "$(stamp) ✓ backed up ($copied new or changed)"; fi
if [ -f "$LOG" ] && [ "$(wc -l < "$LOG")" -gt 2000 ]; then tail -n 1000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"; fi
SH
chmod +x "$SCRIPT"

# 3. The nightly timer, 03:47.
cat > "$PLIST" <<XML
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$SCRIPT</string></array>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>3</integer><key>Minute</key><integer>47</integer></dict>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict></plist>
XML
plutil -lint "$PLIST" >/dev/null || { echo "The timer file didn't come out right. Send this to Claude."; exit 1; }
launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null || launchctl load -w "$PLIST"

# 4. A first run now, the way the timer runs it, so any macOS permission question shows up while you're here.
say "Running the first backup now. The first one copies everything still in the repository, so it can take a few minutes."
echo "If macOS asks whether bash may access Google Drive or files on this Mac, choose Allow."
touch "$LOG"; before=$(wc -l < "$LOG")
launchctl kickstart -k "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || bash "$SCRIPT" >> "$LOG" 2>&1
for _ in $(seq 1 180); do
  now=$(wc -l < "$LOG")
  [ "$now" -gt "$before" ] && tail -n 1 "$LOG" | grep -q -E '✓|✗' && break
  sleep 5
done
last=$(tail -n 1 "$LOG" 2>/dev/null)
echo "$last"
case "$last" in
  *✓*) say "Done. The backup runs every night at 03:47 and logs each run in $LOG." ;;
  *) say "The first backup didn't finish cleanly. If macOS showed a permission question, allow it (System Settings ›"
     echo "Privacy & Security › Files and Folders, or Full Disk Access for bash), then run this script again."
     echo "If it still fails, send Claude the last lines of $LOG." ;;
esac
