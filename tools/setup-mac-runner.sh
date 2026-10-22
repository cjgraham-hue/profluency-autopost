#!/bin/bash
# ProFluency autopost: run the Instagram poster from this Mac instead of GitHub's servers.
#
# It installs a GitHub "self-hosted runner" called cameron-mac with the label "autopost". The Instagram
# autopost workflow only runs on a runner with that label, so every post now goes out from your home
# connection. Your Instagram token stays in GitHub's secrets; nothing secret is saved on the Mac.
#
# Run it from Terminal with:
#   bash <(curl -fsSL https://raw.githubusercontent.com/cjgraham-hue/profluency-autopost/main/tools/setup-mac-runner.sh)
#
# Safe to run again: it reuses what is already installed.

set -euo pipefail

REPO_URL="https://github.com/cjgraham-hue/profluency-autopost"
DIR="$HOME/profluency-runner"
NAME="cameron-mac"
LABEL="autopost"

say() { printf '\n%s\n' "$*"; }

say "Setting up the ProFluency autopost runner on this Mac."

# 1. Python 3.9 or later, which the poster needs (standard library only).
if ! python3 -c 'import sys, zoneinfo; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
  say "Python 3 isn't ready on this Mac yet. Run this, let it finish, then run this script again:"
  echo "  xcode-select --install"
  exit 1
fi
if ! python3 - <<'PY' >/dev/null 2>&1
import ssl, urllib.request, urllib.error
try:
    urllib.request.urlopen('https://graph.instagram.com/', timeout=15)
except urllib.error.HTTPError:
    pass  # any answer from Instagram means the secure connection works
PY
then
  say "Python can't make a secure connection to Instagram from this Mac."
  echo "If you installed Python from python.org, open Applications › Python 3.x and double-click"
  echo "'Install Certificates.command', then run this script again."
  exit 1
fi
echo "Python is ready."

# 2. Download the GitHub runner for this Mac (Apple silicon or Intel).
case "$(uname -m)" in
  arm64) ARCH=arm64 ;;
  x86_64) ARCH=x64 ;;
  *) say "This Mac's processor ($(uname -m)) isn't one GitHub's runner supports."; exit 1 ;;
esac
mkdir -p "$DIR"
cd "$DIR"
if [ ! -f ./config.sh ]; then
  VER=$(curl -fsSL https://api.github.com/repos/actions/runner/releases/latest \
        | python3 -c 'import json, sys; print(json.load(sys.stdin)["tag_name"].lstrip("v"))')
  say "Downloading the GitHub runner $VER for $ARCH..."
  curl -fsSL -o runner.tar.gz \
    "https://github.com/actions/runner/releases/download/v${VER}/actions-runner-osx-${ARCH}-${VER}.tar.gz"
  tar xzf runner.tar.gz
  rm runner.tar.gz
fi

# 3. Connect it to the repository (needs a one-off code from GitHub, valid for an hour).
if [ ! -f ./.runner ]; then
  say "Now get a one-off code from GitHub:"
  echo "  1. Open $REPO_URL/settings/actions/runners/new"
  echo "  2. Under 'Configure', double-click the long code after  --token  to select all of it, and copy it"
  echo
  read -r -p "Paste the code here and press Return: " TOKEN </dev/tty
  TOKEN=$(printf '%s' "$TOKEN" | tr -d '[:space:]')
  if [ -z "$TOKEN" ]; then say "No code pasted, so nothing was connected. Run the script again when you have it."; exit 1; fi
  if ! printf '%s' "$TOKEN" | grep -Eq '^[A-Z0-9]{29,}$'; then
    say "That doesn't look like the whole code (it has ${#TOKEN} characters; GitHub's are at least 29 capital letters and numbers)."
    echo "Reload the GitHub page for a fresh code, double-click it to select all of it, and run this script again."
    exit 1
  fi
  if ! ./config.sh --url "$REPO_URL" --token "$TOKEN" --name "$NAME" --labels "$LABEL" \
                   --work _work --unattended --replace; then
    unset TOKEN
    say "GitHub didn't accept that code. Codes only last an hour, so reload the GitHub page for a fresh one"
    echo "and run this script again."
    exit 1
  fi
  unset TOKEN
else
  echo "Already connected to GitHub as $(python3 -c 'import json; print(json.load(open(".runner", encoding="utf-8-sig")).get("agentName", "this Mac"))')."
fi

# 4. Keep it running in the background whenever you're logged in to the Mac.
if ! ./svc.sh status 2>/dev/null | grep -qi "started"; then
  ./svc.sh install >/dev/null 2>&1 || true
  ./svc.sh start
fi
./svc.sh status 2>/dev/null | tail -n 3 || true

say "Done. The runner '$NAME' is listening for posts."
echo "Next:"
echo "  1. Keep the Mac on, plugged in and awake between 7am and 10pm. On a MacBook: System Settings ›"
echo "     Battery › Options › turn on 'Prevent automatic sleeping on power adapter when the display is off'."
echo "     If the Mac is asleep at a post's time, it posts when the Mac wakes, up to 3 hours late."
echo "  2. In GitHub: Actions › Instagram autopost › Run workflow › type check › Run. When it goes green,"
echo "     posting carries on."
