# ProFluency autopost

Posts the "Pull up a chair" month (Mon 19 Oct – Sun 15 Nov 2026) to @profluencyuk by itself: 74 items (58 stories, 8 feed posts, 8 Reels), each at its planned UK time, with the hashtags added as the first comment. Your computer can be off. It runs free on GitHub: every 15 minutes a small script (`publish.py`) checks the schedule and posts whatever is due through Instagram's official API.

Everything posts automatically, including the stories that were made for stickers (question, poll, countdown, link) and the Sunday "Your answers" stories. The API can't add stickers or other people's replies, so those items carry a `follow_up` note: once one has posted, GitHub opens an issue, which emails you what it was made for. If you want the sticker, save the story from Instagram and post it again with the sticker. An item with `"manual"` instead of `"follow_up"` is never posted: you're emailed at its time to post it yourself.

## What's here

- `schedule.json`: the 85 items, with time (Europe/London, clocks-change aware), type, file, caption and first comment, all copied from the month pack.
- `docs/media/`: the files, renamed for the web (e.g. `2026-10-19-1930-reel.mp4`). Stories use the animated MP4 wherever one exists. The videos have a silent audio track added, which Instagram's API expects.
- `publish.py`: the poster. It uses Python's standard library only.
- `.github/workflows/autopost.yml`: the 15-minute timer, a record of what's been posted (`posted.json`), and the email reminders.
- `SETUP_PROMPT.md`: paste this into Claude Code or Cursor in your terminal and it walks you through setup.

## One-off setup (about 30 minutes)

1. **Instagram:** make @profluencyuk a **Business** account (Settings › Account type and tools). A Creator account can't publish Stories through the API.
2. **Meta developer app:** at developers.facebook.com, create an app with the Instagram API ("API setup with Instagram login"), add @profluencyuk and generate a token. Grant `instagram_business_basic`, `instagram_business_content_publish` and `instagram_business_manage_comments`. Copy the **access token** (it lasts 60 days, which covers the month) and the **Instagram user ID**.
3. **GitHub:** push this folder to a **public** repository (free timer minutes and free hosting for the media). Turn on GitHub Pages from `main` › `/docs`. Add the secrets `IG_ACCESS_TOKEN` and `IG_USER_ID`, and the variable `MEDIA_BASE_URL` = `https://<your-github-name>.github.io/<repo>/media`.
4. **Test:** Actions › Instagram autopost › Run workflow. Run it with `check`, which tests the token, account type and every media link, then with `dry-run`. Nothing is posted in either mode.

Once that's done, it starts by itself. The first automatic post is **Mon 19 Oct 12:30**; the 08:30 story that day is one of the by-hand ones.

## Good to know

- **Timing:** posts go out within about 15 minutes of the planned time. GitHub's timer can occasionally run late. If a post is more than 3 hours late it's skipped, and you get an email instead, so nothing lands at a strange hour.
- **Reels are silent:** the API can't add music from Instagram's library. If you want a trending sound on a Reel, either set that Reel to by hand (add `"manual": "Add a sound"` to it in `schedule.json`), or let it post and add a sound afterwards from the app.
- **Public repo:** the files and captions can be seen by anyone who finds the repository before they're posted. If that matters, keep the repo private and host `docs/media` on profluency.co.uk instead (then set `MEDIA_BASE_URL` to that folder). The 15-minute timer stays inside GitHub's free private allowance.
- **Changing a post:** edit `schedule.json` (text, time) or replace a file in `docs/media`, then commit. To stop everything, disable the workflow in Actions.
- **Commands** (run with the three settings in your environment): `python3 publish.py --check`, `--dry-run`, `--list`, or `--only <id>` to post one item now.
- **Limits:** Instagram allows 50 API posts per 24 hours. The busiest day here has 4.
- **Token renewal:** `.github/workflows/refresh-token.yml` renews the Instagram token on the 1st and 15th of each month and writes the new expiry date to `token-status.json`. It needs one secret, `SECRETS_WRITER_TOKEN`: a fine-grained GitHub token for this repo only, with "Secrets: Read and write". If a renewal fails, you get an issue email.
- **New months:** Claude makes each month (plan, artwork, animations, InDesign backup in Drive) and, once you say "schedule it", adds the media to `docs/media` and the posts to `schedule.json` here.
