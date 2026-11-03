# The hub Mac: Claude's checklist

Cameron has just run `tools/setup-hub-mac.sh` on a new Mac that stays on. From now on this Mac runs everything
local for ProFluency: the posting runner (`cameron-mac`, label `autopost`), the timer that starts posting every
15 minutes and the hub sync every two hours, Chrome with Claude in Chrome, and the Claude app for scheduled tasks
that need a computer. The hub itself is at https://hub.profluency.co.uk.

Your job is to check the move and finish the parts the script can't do, in as few steps as you can. Use the
Mac's shell for checks (it's cheaper than the browser), and the browser only for steps 3 and 5.

Rules: never type a password, token or key, and never sign in for Cameron; if something needs signing in, ask
him to do it. Don't post, publish, schedule or delete anything, and don't change account, channel or GitHub
settings. Changes to this repository go by pull request.

1. **Status.** Run `bash ~/profluency-hub-mac/status.sh` and read it. For anything marked ✗, find out why and fix
   it with the scripts in `tools/` (`setup-hub-mac.sh` is safe to run again; Cameron must run it himself in
   Terminal, because it may ask for the Mac's password). The runner's setup log is
   `~/profluency-hub-mac/runner-setup.log`; the timer's is `~/Library/Logs/profluency-post-timer.log`.
2. **GitHub.** Check `gh api repos/cjgraham-hue/profluency-autopost/actions/runners` lists `cameron-mac` online,
   and that an "Instagram autopost" run and a "Hub feed" run have succeeded since the setup
   (`gh run list -R cjgraham-hue/profluency-autopost -L 6`). If no run has happened yet, wait for the next quarter
   hour (02, 17, 32 or 47 past) and look again once.
3. **Chrome.** Load the chrome-browser skill and open https://hub.profluency.co.uk in a new tab. If the sign-in
   page shows, ask Cameron to sign in once (the hub remembers the Mac). Then open https://studio.youtube.com and
   https://www.pinterest.co.uk and check each is signed in to ProFluency. Close the tabs you opened.
4. **Scheduled tasks.** List Cameron's scheduled tasks. For each one that uses Chrome or this computer (for
   example "ProFluency: schedule Shorts and pins in Chrome"), tell him to open it in this app and turn on
   Require this computer, so it runs here. Don't change the tasks yourself.
5. **Old Mac.** Remind him to run this on the old Mac once everything here is green:
   `bash <(curl -fsSL https://raw.githubusercontent.com/cjgraham-hue/profluency-autopost/main/tools/retire-old-mac.sh)`

Finish with no more than four short lines: what works, and only the things Cameron has to do himself.

## What runs where, after the move

On GitHub, by itself: the hub sync (also started by this Mac's timer and by the hub when Cameron approves
something), the Journal workflows, and the Monday letter draft each Tuesday. On this Mac, with no Claude: posting
to Instagram, sending replies, merging approved Instagram changes, and the status check. On this Mac,
with Claude: the weekly Chrome task for YouTube Shorts and Pinterest pins, and anything Cameron asks for.
