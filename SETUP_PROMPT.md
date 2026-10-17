# Paste this into Claude Code or Cursor (agent mode), opened in the "ProFluency autopost" folder

You're helping Cameron set up automatic Instagram posting for @profluencyuk. Everything is already built in this folder: `schedule.json` (85 items, UK times), `docs/media/` (the files), `publish.py` (the poster, standard-library Python), and `.github/workflows/autopost.yml` (runs every 15 minutes on GitHub Actions). Read `README.md` first.

Don't change the schedule, the captions or the media. Your job is the setup, done with Cameron step by step. Explain each step in one or two plain sentences, and wait for him whenever a step needs him in a browser or app.

1. **Check the tools.** Check that `git`, `gh` (GitHub CLI) and `python3` (3.9+) are installed. If they aren't, install them; on a Mac, use Homebrew. Run `gh auth status` and, if needed, `gh auth login`.

2. **Run a local test.** Run `python3 publish.py --list | head` and `python3 publish.py --dry-run --now 2026-10-19T12:35:00+01:00`. You should see "Would post 2026-10-19-1230-story". Fix nothing in the code unless a test actually fails.

3. **Switch to a Business account.** Ask Cameron to set @profluencyuk to a Business account in the Instagram app (Settings › Account type and tools). The API can't publish Stories from a Creator account.

4. **Create the Meta app and token.** Open Meta's current documentation for "Instagram API with Instagram Login" and content publishing (developers.facebook.com/docs/instagram-platform), because these screens change. Guide Cameron to:
   - create a Meta app with the Instagram API use case;
   - in "API setup with Instagram login", add @profluencyuk and generate an access token;
   - grant `instagram_business_basic`, `instagram_business_content_publish` and `instagram_business_manage_comments`.

   Get the long-lived token (60 days) and the Instagram user ID. Never print the token in full and never commit it.

5. **Check the account.** Run `IG_ACCESS_TOKEN=… IG_USER_ID=… MEDIA_BASE_URL=x python3 publish.py --check`. The account and publishing-allowance lines must work. Media links will fail at this stage, which is expected.

6. **Create the GitHub repo.** Create a public repo, e.g. `gh repo create profluency-autopost --public --source . --push`. Enable GitHub Pages from branch `main`, folder `/docs` (with `gh api` or the web settings). Wait until `https://<owner>.github.io/profluency-autopost/media/2026-10-19-1930-reel.mp4` loads.

7. **Add the secrets and variable.** Run `gh secret set IG_ACCESS_TOKEN`, `gh secret set IG_USER_ID` and `gh variable set MEDIA_BASE_URL --body "https://<owner>.github.io/profluency-autopost/media"`. In the repo settings, make sure Actions may write (Settings › Actions › Workflow permissions › Read and write) and that Issues are on.

8. **Run the checks on GitHub.** Run `gh workflow run autopost.yml -f mode=check`, then `-f mode=dry-run`. Watch them with `gh run watch` and fix any setup problem until both pass (0 media problems).

9. **Hand over.** Tell Cameron:
   - the first automatic post is Mon 19 Oct 12:30;
   - by-hand items arrive as GitHub issue emails at their time;
   - `posted.json` in the repo shows what has gone out;
   - disabling the workflow stops everything.

   Remind him the token expires 60 days after it was made.

If anything in Meta's process differs from this prompt, follow Meta's current docs and tell Cameron what changed. Don't post anything to Instagram during setup unless Cameron asks for a test post. If he does, use `python3 publish.py --only <id>` on a story he chooses, and remember a real post can't be unpublished by the script.
