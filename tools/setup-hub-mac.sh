#!/bin/bash
# ProFluency hub Mac: turns an always-on Mac into the place where everything local runs.
#
# Run it from Terminal on the new Mac with:
#   bash <(curl -fsSL https://raw.githubusercontent.com/cjgraham-hue/profluency-autopost/main/tools/setup-hub-mac.sh)
#
# What it does, asking before anything that changes the Mac:
#   1. power: never sleeps on mains power, wakes for the network, starts up again after a power cut
#   2. tools: Apple's command line tools, Python and GitHub's command line tool (gh), with Homebrew if the Mac has it
#   3. GitHub sign-in for gh (you do it in the browser; no password or token is typed here or saved by this script)
#   4. the posting runner "cameron-mac" (label autopost), which takes over from the old Mac's
#   5. the timer that starts posting every 15 minutes and the hub sync every two hours (tools/setup-mac-timer.sh)
#   6. Chrome and Claude: checks they're installed, opens them at login, opens the hub
#   7. "ProFluency status" on the Desktop: double-click it any time to see that everything is running, no Claude needed
# Then it copies a short prompt for Claude, which checks the parts that need a browser.
#
# Safe to run again. On the OLD Mac, run tools/retire-old-mac.sh once this one is working.

set -uo pipefail

REPO="cjgraham-hue/profluency-autopost"
RAW="https://raw.githubusercontent.com/$REPO/main"
RUNNER_DIR="$HOME/profluency-runner"
RUNNER_NAME="cameron-mac"
HUB_DIR="$HOME/profluency-hub-mac"
STATUS="$HUB_DIR/status.sh"
LATER=()

step() { printf '\n\033[1m%s\033[0m\n' "$*"; }
ask() { local a; read -r -p "$1 [Y/n] " a </dev/tty; [[ -z "$a" || "$a" =~ ^[Yy] ]]; }
later() { LATER+=("$*"); }

[ "$(uname)" = "Darwin" ] || { echo "This script is for a Mac."; exit 1; }
mkdir -p "$HUB_DIR"
echo "Setting up this Mac as the ProFluency hub Mac. It takes about ten minutes; keep this window open."

# ------------------------------------------------------------------------------------------------ 1. power
step "1 of 7 · Keep the Mac on"
echo "This sets: never sleep on mains power (the screen still turns off after 10 minutes), wake for network"
echo "access, and start up again by itself after a power cut. macOS asks for this Mac's password (typed here,"
echo "never saved)."
if ask "Change these power settings now?"; then
  if sudo pmset -c sleep 0 disksleep 0 displaysleep 10 womp 1 && sudo pmset -a autorestart 1; then
    echo "Done."
  else
    later "Power: in System Settings › Energy (or Battery › Options), turn off sleeping on power and turn on 'Start up automatically after a power failure'."
  fi
else
  later "Power: keep the Mac from sleeping, or posts wait until it wakes."
fi

# ------------------------------------------------------------------------------------------------ 2. tools
step "2 of 7 · Tools"
if ! xcode-select -p >/dev/null 2>&1; then
  echo "Apple's command line tools aren't installed yet. A window opens to install them: press Install,"
  echo "wait for it to finish, then run this script again."
  xcode-select --install >/dev/null 2>&1 || true
  exit 1
fi
find_gh() { GH=$(command -v gh || true); for p in /opt/homebrew/bin/gh /usr/local/bin/gh; do [ -z "$GH" ] && [ -x "$p" ] && GH="$p"; done; }
# Without Homebrew (it no longer supports Intel Macs): GitHub's own build of gh, copied to /usr/local/bin.
install_gh_direct() {
  local arch url tmp
  case "$(uname -m)" in arm64) arch=arm64 ;; *) arch=amd64 ;; esac
  url=$(curl -fsSL https://api.github.com/repos/cli/cli/releases/latest | grep -o "https://[^\"]*_macOS_${arch}\.zip" | head -n 1)
  [ -n "$url" ] || return 1
  tmp=$(mktemp -d) && curl -fsSL -o "$tmp/gh.zip" "$url" && unzip -q "$tmp/gh.zip" -d "$tmp" || return 1
  echo "Copying gh to /usr/local/bin (macOS may ask for this Mac's password)."
  sudo mkdir -p /usr/local/bin && sudo cp "$tmp"/gh_*/bin/gh /usr/local/bin/gh && sudo chmod 755 /usr/local/bin/gh
  rm -rf "$tmp"
}
# Without Homebrew: python.org's Python 3.12 (works on Intel and Apple silicon), with its certificates.
install_python_direct() {
  local v=3.12.8 pkg
  pkg="$HUB_DIR/python-$v.pkg"
  echo "Installing Python $v from python.org (macOS may ask for this Mac's password)..."
  curl -fsSL -o "$pkg" "https://www.python.org/ftp/python/$v/python-$v-macos11.pkg" && sudo installer -pkg "$pkg" -target / >/dev/null || return 1
  rm -f "$pkg"
  [ -f "/Applications/Python 3.12/Install Certificates.command" ] && bash "/Applications/Python 3.12/Install Certificates.command" >/dev/null 2>&1
  PATH="/Library/Frameworks/Python.framework/Versions/3.12/bin:$PATH"; export PATH; hash -r
}
BREW=$(command -v brew || true); for p in /opt/homebrew/bin/brew /usr/local/bin/brew; do [ -z "$BREW" ] && [ -x "$p" ] && BREW="$p"; done
find_gh
if [ -z "$GH" ]; then
  if [ -n "$BREW" ]; then "$BREW" install gh; else install_gh_direct; fi
  find_gh
fi
[ -n "$GH" ] || { echo "gh didn't install. Send this message to Claude."; exit 1; }
# The runner keeps the path it's set up with, so put the tools' folders first.
for d in /usr/local/bin /opt/homebrew/bin; do [ -d "$d" ] && case ":$PATH:" in *":$d:"*) ;; *) PATH="$d:$PATH" ;; esac; done
export PATH
py_ok() { python3 -c 'import sys, zoneinfo, ssl; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; }
if ! py_ok; then
  echo "Python 3.9 or later isn't ready on this Mac ($(python3 --version 2>&1 | head -n 1))."
  if [ -n "$BREW" ]; then "$BREW" install python; else install_python_direct; fi
  hash -r
  py_ok || { echo "Python still isn't ready. Send Claude this: $(uname -m) $(sw_vers -productVersion) $(xcode-select -p 2>&1) $(command -v python3) $(python3 --version 2>&1 | head -n 1)"; exit 1; }
fi
echo "Python ready: $(python3 --version 2>&1)."
if ! python3 -c 'import urllib.request, urllib.error
try: urllib.request.urlopen("https://graph.instagram.com/", timeout=15)
except urllib.error.HTTPError: pass' >/dev/null 2>&1; then
  later "Python can't reach Instagram securely. If Python came from python.org, run 'Install Certificates.command' in Applications › Python 3.x."
fi
echo "Tools ready (gh at $GH)."

# ------------------------------------------------------------------------------------------------ 3. GitHub sign-in
step "3 of 7 · GitHub sign-in"
if ! "$GH" auth status --hostname github.com >/dev/null 2>&1; then
  echo "gh opens GitHub in the browser. Choose to log in with a web browser, copy the one-time code it shows,"
  echo "and finish in the browser with the account that owns $REPO."
  "$GH" auth login --hostname github.com --git-protocol https --web </dev/tty || true
fi
if ! "$GH" api "repos/$REPO" --jq .full_name >/dev/null 2>&1; then
  echo "gh can't see $REPO. Run: $GH auth login --web (with the account that owns it), then this script again."
  exit 1
fi
echo "Signed in to GitHub."

# ------------------------------------------------------------------------------------------------ 4. posting runner
step "4 of 7 · Posting runner"
case "$(uname -m)" in arm64) ARCH=arm64 ;; x86_64) ARCH=x64 ;; *) echo "GitHub's runner doesn't support this processor."; exit 1 ;; esac
mkdir -p "$RUNNER_DIR" && cd "$RUNNER_DIR" || exit 1
if [ ! -f ./config.sh ] || ! ls ./externals/node*/bin/node >/dev/null 2>&1; then
  ./svc.sh stop >/dev/null 2>&1
  VER=$("$GH" api repos/actions/runner/releases/latest --jq '.tag_name' | sed 's/^v//')
  echo "Downloading GitHub's runner $VER..."
  curl -fsSL -o runner.tar.gz "https://github.com/actions/runner/releases/download/v${VER}/actions-runner-osx-${ARCH}-${VER}.tar.gz" \
    && tar xzf runner.tar.gz && rm -f runner.tar.gz || { echo "The download didn't work. Run this script again."; exit 1; }
fi
HOSTNAME_NOW=$(scutil --get LocalHostName 2>/dev/null || hostname)
if [ -f ./.runner ] && [ "$(cat ./.hub-mac 2>/dev/null)" != "$HOSTNAME_NOW" ]; then
  # A runner folder copied from the old Mac (by Migration Assistant) still carries the old Mac's connection.
  echo "Found the old Mac's runner settings; connecting this Mac instead."
  ./svc.sh stop >/dev/null 2>&1; ./svc.sh uninstall >/dev/null 2>&1
  RT=$("$GH" api -X POST "repos/$REPO/actions/runners/remove-token" --jq .token 2>/dev/null) && ./config.sh remove --token "$RT" >/dev/null 2>&1
  unset RT
  rm -f ./.runner ./.credentials ./.credentials_rsaparams
fi
if [ ! -f ./.runner ]; then
  # A one-off registration code straight from GitHub, never shown or saved; --replace takes over the old Mac's runner.
  TOKEN=$("$GH" api -X POST "repos/$REPO/actions/runners/registration-token" --jq .token 2>/dev/null)
  if [ -z "$TOKEN" ] || ! ./config.sh --url "https://github.com/$REPO" --token "$TOKEN" --name "$RUNNER_NAME" --labels autopost \
        --work _work --unattended --replace >"$HUB_DIR/runner-setup.log" 2>&1; then
    unset TOKEN
    echo "GitHub didn't connect the runner (details in $HUB_DIR/runner-setup.log). Run this script again;"
    echo "if it fails twice, ask Claude to look at that file."
    exit 1
  fi
  unset TOKEN
fi
printf '%s' "$HOSTNAME_NOW" > ./.hub-mac
./svc.sh status 2>/dev/null | grep -qi "started" || { ./svc.sh install >/dev/null 2>&1; ./svc.sh start >/dev/null 2>&1; }
if ./svc.sh status 2>/dev/null | grep -qi "started"; then echo "The runner '$RUNNER_NAME' is running."; else later "Runner: it didn't start. Double-click ProFluency status for details."; fi
cd "$HOME" || exit 1

# ------------------------------------------------------------------------------------------------ 5. timer
step "5 of 7 · Timer"
bash <(curl -fsSL "$RAW/tools/setup-mac-timer.sh") </dev/tty | tail -n 4

# ------------------------------------------------------------------------------------------------ 6. Chrome and Claude
step "6 of 7 · Chrome and Claude"
for app in "Google Chrome" "Claude"; do
  if [ -d "/Applications/$app.app" ]; then
    osascript -e "tell application \"System Events\" to if not (exists login item \"$app\") then make login item at end with properties {path:\"/Applications/$app.app\", hidden:false}" >/dev/null 2>&1 \
      && echo "$app opens by itself at login." || later "Login: add $app under System Settings › General › Login Items."
  else
    later "Install $app, sign in, then run this script again so it opens at login."
  fi
done
[ -d "/Applications/Google Chrome.app" ] || open "https://www.google.com/chrome/"
[ -d "/Applications/Claude.app" ] || open "https://claude.ai/download"
if [ -d "/Applications/Google Chrome.app" ]; then
  open -a "Google Chrome" "https://hub.profluency.co.uk"
  later "Chrome: sign in to the hub once (it remembers this Mac), and to YouTube Studio and Pinterest as ProFluency. Add the Claude extension from the Chrome Web Store and sign in to it."
fi

# ------------------------------------------------------------------------------------------------ 7. status
step "7 of 7 · ProFluency status"
cat > "$STATUS" <<'SH'
#!/bin/bash
# ProFluency hub Mac status: what's running, with no Claude needed. Double-click "ProFluency status" on the Desktop.
REPO="cjgraham-hue/profluency-autopost"; SITE="cjgraham-hue/profluency"
GH=$(command -v gh || true); for p in /usr/local/bin/gh /opt/homebrew/bin/gh; do [ -z "$GH" ] && [ -x "$p" ] && GH="$p"; done
ok() { printf '  \033[32m✓\033[0m %s\n' "$*"; }; no() { printf '  \033[31m✗\033[0m %s\n' "$*"; }
echo; echo "ProFluency hub Mac · $(date '+%a %d %b %H:%M')"; echo
if (cd "$HOME/profluency-runner" 2>/dev/null && ./svc.sh status 2>/dev/null | grep -qi started); then ok "Posting runner is running"; else no "Posting runner isn't running: run the setup command again"; fi
if [ -n "$GH" ]; then
  "$GH" api "repos/$REPO/actions/runners" --jq '.runners[] | "\(.name) \(.status)"' 2>/dev/null | while read -r n s; do
    [ "$s" = "online" ] && ok "GitHub sees runner $n online" || no "GitHub sees runner $n $s"; done
fi
if launchctl print "gui/$(id -u)/uk.co.profluency.post-timer" >/dev/null 2>&1; then ok "Timer is on"; else no "Timer is off: run the setup command again"; fi
LOG="$HOME/Library/Logs/profluency-post-timer.log"
[ -f "$LOG" ] && { echo "  Timer, last lines:"; tail -n 3 "$LOG" | sed 's/^/    /'; }
if [ -n "$GH" ]; then
  for w in "$REPO autopost.yml Posting" "$REPO hub-feed.yml Hub feed (replies)" "$SITE hub-sync.yml Hub sync"; do
    set -- $w; r=$1; f=$2; shift 2
    line=$("$GH" run list -R "$r" -w "$f" -L 1 --json conclusion,status,createdAt --jq '.[0] | "\(.status) \(.conclusion) \(.createdAt)"' 2>/dev/null)
    when=$(date -j -u -f '%Y-%m-%dT%H:%M:%SZ' "${line##* }" '+%s' 2>/dev/null); when=${when:+$(date -r "$when" '+%a %H:%M')}
    case "$line" in *success*) ok "$* last ran ${when:-${line##* }}";; in_progress*|queued*|waiting*|pending*) ok "$* running now";; "") no "$*: couldn't read it";; *) no "$* last run didn't finish well ($line)";; esac
  done
fi
pmset -g 2>/dev/null | grep -Eq '^ *sleep +0' && ok "Mac never sleeps on power" || no "Mac may sleep: run the setup command again"
pgrep -x "Google Chrome" >/dev/null && ok "Chrome is open" || no "Chrome isn't open"
pgrep -x "Claude" >/dev/null && ok "Claude is open" || no "Claude isn't open"
echo
SH
chmod +x "$STATUS"
printf '#!/bin/bash\nbash "%s"\nread -r -p "Press Return to close." _\n' "$STATUS" > "$HOME/Desktop/ProFluency status.command"
chmod +x "$HOME/Desktop/ProFluency status.command"
bash "$STATUS"

# ------------------------------------------------------------------------------------------------ done
PROMPT="Read and follow https://github.com/$REPO/blob/main/docs/hub-mac.md: this Mac is now ProFluency's hub Mac and I've just run its setup script. Check the move and finish it."
printf '%s' "$PROMPT" | pbcopy
step "Done"
if [ ${#LATER[@]} -gt 0 ]; then echo "Still for you:"; i=1; for t in "${LATER[@]}"; do echo "  $i. $t"; i=$((i + 1)); done; fi
echo
echo "Last step: open the Claude app on this Mac, start a new task linked to this Mac, and paste."
echo "The prompt is already copied:"
echo "  $PROMPT"
echo "Then, on the OLD Mac, run:"
echo "  bash <(curl -fsSL $RAW/tools/retire-old-mac.sh)"
[ -d "/Applications/Claude.app" ] && open -a "Claude"
