#!/usr/bin/env python3
"""ProFluency autopost: publishes the month's stories, carousels and Reels to @profluencyuk at the planned times.
Runs every 15 minutes (GitHub Actions, or cron on your computer); each run posts whatever is due and not yet
posted. Python 3.9+, standard library only.

Settings (environment variables)
  IG_USER_ID        your Instagram account's ID (from the API setup)
  IG_ACCESS_TOKEN   a long-lived Instagram access token (lasts 60 days)
  MEDIA_BASE_URL    where the files in docs/media are public, e.g. https://cameron.github.io/profluency-autopost/media
  GRAPH_VERSION     optional, default v23.0
  WINDOW_HOURS      optional, default 3: a post more than this late is skipped (and reported) rather than posted

Usage
  python3 publish.py --check          check the token, the account and that the media links work; posts nothing
  python3 publish.py --dry-run        show what would be posted now; posts nothing
  python3 publish.py                  post everything that is due
  python3 publish.py --only ID        post one item now (e.g. a test), whatever its time
  python3 publish.py --list           the whole schedule, with what's been posted

Schedule items can carry "follow_up": a note emailed to Cameron (as a GitHub issue) once the item has been posted,
e.g. a sticker to add by downloading the story and posting it again. Items with "manual" are not posted at all;
they are emailed at their time instead. Items with "hold" are not posted or emailed: they stay in the schedule,
with the reason, until the line is removed.

A carousel ("type": "carousel") lists its 2 to 10 files in "slides", in order; "media" is the first slide.
Hashtags go at the end of the caption. No first comment is posted (from 29 Oct 2026).

Staying clear of Instagram's automation checks (added 21 Oct 2026, after the account was flagged):
  - each post goes out up to 12 minutes after its planned time, a different amount for each post, so the timing
    is never exactly on the clock;
  - if Meta blocks access ("API access blocked", a restricted or checkpointed account, suspected spam or a dead
    token), the run stops at once, writes pause.json and emails once. Nothing is tried again until you've sorted it
    in the Instagram app and run the workflow with "check", which resumes posting when the account answers.
"""
import json, os, sys, time, hashlib, urllib.request, urllib.parse, urllib.error, datetime as dt
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEDULE = json.load(open(os.path.join(HERE, 'schedule.json'), encoding='utf-8'))
STATE_FILE = os.path.join(HERE, 'posted.json')
PAUSE_FILE = os.path.join(HERE, 'pause.json')
LONDON = ZoneInfo('Europe/London')
VERSION = os.environ.get('GRAPH_VERSION', 'v23.0')
API = f'https://graph.instagram.com/{VERSION}'
WINDOW = dt.timedelta(hours=float(os.environ.get('WINDOW_HOURS', '3')))

def env(name):
    v = os.environ.get(name, '').strip()
    if not v: sys.exit(f'Missing setting: {name}. See README.md.')
    return v

class ApiError(RuntimeError):
    def __init__(self, method, path, http, code, subcode, msg):
        super().__init__(f'{method} {path}: {http} {msg}')
        self.http, self.code, self.subcode, self.msg = http, code, subcode, msg

def is_block(e):
    """Meta has stopped this app or account: retrying only makes it look more like a bot."""
    if not isinstance(e, ApiError): return False
    m = (e.msg or '').lower()
    return (e.code == 190 or e.subcode in (2207050, 2207051) or 'blocked' in m or 'restricted' in m
            or 'checkpoint' in m or 'suspicious' in m or 'spam' in m)

def call(method, path, **params):
    params['access_token'] = env('IG_ACCESS_TOKEN')
    data = urllib.parse.urlencode(params).encode()
    url = f'{API}/{path}'
    if method == 'GET': req = urllib.request.Request(url + '?' + data.decode())
    else: req = urllib.request.Request(url, data=data, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=60) as r: return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors='replace')
        try: err = json.loads(body).get('error', {})
        except ValueError: err = {}
        if not isinstance(err, dict): err = {}
        raise ApiError(method, path, e.code, err.get('code'), err.get('error_subcode'), err.get('message', body)) from None

def media_url(name): return env('MEDIA_BASE_URL').rstrip('/') + '/' + urllib.parse.quote(name)

def load_state():
    try: return json.load(open(STATE_FILE, encoding='utf-8'))
    except (OSError, ValueError): return {}
def save_state(s): json.dump(s, open(STATE_FILE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

def load_pause():
    try: return json.load(open(PAUSE_FILE, encoding='utf-8'))
    except (OSError, ValueError): return None
def save_pause(p): json.dump(p, open(PAUSE_FILE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
def clear_pause():
    if os.path.exists(PAUSE_FILE): os.remove(PAUSE_FILE); return True
    return False

def offset(it):
    """0 to 12 minutes after the planned time, fixed for each post, so posts never land exactly on the clock."""
    return dt.timedelta(seconds=int(hashlib.sha256(it['id'].encode()).hexdigest(), 16) % 721)

def files(it):
    """every file an item posts: its media, a carousel's slides and a Reel's cover"""
    return list(dict.fromkeys([it['media']] + it.get('slides', []) + ([it['cover']] if it.get('cover') else [])))

def wait_ready(container, kind):
    """videos take a while to process; images are usually ready at once"""
    limit = time.time() + (15 * 60 if kind in ('reel', 'story_video') else 120)
    while True:
        st = call('GET', container, fields='status_code,status').get('status_code')
        if st in ('FINISHED', 'PUBLISHED'): return
        if st in ('ERROR', 'EXPIRED'): raise RuntimeError(f'Instagram could not process the file (status {st})')
        if time.time() > limit: raise RuntimeError('Instagram is still processing the file after the time limit')
        time.sleep(8)

def publish(it):
    ig = env('IG_USER_ID'); kind = it['type']
    p = {}
    if kind == 'post': p = dict(image_url=media_url(it['media']), caption=it['caption'])
    elif kind == 'reel':
        p = dict(media_type='REELS', video_url=media_url(it['media']), caption=it['caption'], share_to_feed='true')
        if it.get('cover'): p['cover_url'] = media_url(it['cover'])
    elif kind == 'story_image': p = dict(media_type='STORIES', image_url=media_url(it['media']))
    elif kind == 'story_video': p = dict(media_type='STORIES', video_url=media_url(it['media']))
    elif kind == 'carousel':
        children = []
        for name in it['slides']:
            video = name.lower().endswith('.mp4')
            child = call('POST', f'{ig}/media', is_carousel_item='true',
                         **(dict(media_type='VIDEO', video_url=media_url(name)) if video else dict(image_url=media_url(name))))['id']
            wait_ready(child, 'reel' if video else 'post')
            children.append(child)
        p = dict(media_type='CAROUSEL', children=','.join(children), caption=it['caption'])
    else: raise RuntimeError(f'unknown type {kind}')
    container = call('POST', f'{ig}/media', **p)['id']
    wait_ready(container, kind)
    for attempt in range(5):          # "Media ID is not available": Instagram isn't ready to publish yet, so wait and ask again
        try: media_id = call('POST', f'{ig}/media_publish', creation_id=container)['id']; break
        except ApiError as e:
            if attempt == 4 or not (e.subcode == 2207027 or 'not available' in (e.msg or '').lower() or 'not ready' in (e.msg or '').lower()): raise
            time.sleep(20)
    return media_id

def now_london(arg=None):
    return dt.datetime.fromisoformat(arg).astimezone(LONDON) if arg else dt.datetime.now(LONDON)

def main(argv):
    args = argv[1:]; state = load_state()
    items = SCHEDULE['items']; by_id = {i['id']: i for i in items}
    report = []          # lines for the run summary (and a GitHub issue when something needs you)

    if '--list' in args:
        for i in items:
            s = state.get(i['id'], {}).get('status', 'on hold' if i.get('hold') else 'by hand' if 'manual' in i else 'waiting')
            print(f"{i['post_at'][:16].replace('T', ' ')}  {i['type']:<12} {s:<10} {i['id']}")
        return 0

    if '--check' in args:
        try: me = call('GET', 'me', fields='user_id,username,account_type')
        except ApiError as e:
            print('Instagram refused the check:', e)
            if is_block(e): print('Meta is still blocking access. Check the Instagram app for a notice, then run "check" again.')
            return 1
        print('Account:', me.get('username'), '| type:', me.get('account_type'), '| id:', me.get('user_id'))
        if str(me.get('user_id')) != env('IG_USER_ID'): print('WARNING: IG_USER_ID does not match this token\'s account', me.get('user_id'))
        if me.get('account_type') not in ('BUSINESS',): print('WARNING: Stories can only be published by the API on a Business account.')
        lim = call('GET', f"{env('IG_USER_ID')}/content_publishing_limit", fields='quota_usage,config')
        print('Publishing allowance:', json.dumps(lim.get('data', lim)))
        bad = 0
        for i in items:
            if i['id'] in state or i.get('hold'): continue      # done (its file may have been removed by the weekly cleanup) or on hold
            if i['type'] == 'carousel' and not 2 <= len(i.get('slides', [])) <= 10: bad += 1; print('A carousel needs 2 to 10 slides:', i['id'])
            if i.get('first_comment'): print('First comments are no longer posted, so move these hashtags into the caption:', i['id'])
            for name in files(i):
                try:
                    with urllib.request.urlopen(urllib.request.Request(media_url(name), method='HEAD'), timeout=30) as r:
                        ct = r.headers.get('Content-Type', '')
                        if not (ct.startswith('image/') or ct.startswith('video/')): bad += 1; print('Not an image/video:', name, ct)
                except Exception as e: bad += 1; print('Media link not reachable:', media_url(name), e)
        print(f'{len(items)} items in the schedule; media links checked, {bad} problem(s).')
        if clear_pause(): print('The account answered, so posting has resumed (pause.json removed).')
        return 1 if bad else 0

    if '--only' in args:
        it = by_id[args[args.index('--only') + 1]]
        mid = publish(it)
        state[it['id']] = dict(status='posted', media_id=mid, at=now_london().isoformat()); save_state(state)
        print('Posted', it['id'], mid); return 0

    dry = '--dry-run' in args or os.environ.get('DRY_RUN') == '1'
    now = now_london(args[args.index('--now') + 1] if '--now' in args else None)
    paused = load_pause()
    if paused: print(f"Posting is paused since {paused.get('since', '?')[:16]}: {paused.get('reason', '')}. Run the workflow with \"check\" to resume.")
    for it in items:
        if it['id'] in state or it.get('hold'): continue
        at = dt.datetime.fromisoformat(it['post_at'])
        if at + offset(it) > now: continue
        late = now - at
        if 'manual' in it:
            report.append(f"- **{at.strftime('%a %d %b %H:%M')}** · {it['source']}: {it['manual']}")
            if not dry: state[it['id']] = dict(status='by hand', at=now.isoformat())
            continue
        if late > WINDOW:
            report.append(f"- **Missed** {at.strftime('%a %d %b %H:%M')} · {it['source']} ({int(late.total_seconds() // 60)} min late, not posted). Post it by hand or run publish.py --only {it['id']}.")
            if not dry: state[it['id']] = dict(status='missed', at=now.isoformat())
            continue
        if paused: continue            # waits; once resumed it posts if still within the window, otherwise it's reported as missed
        if dry: print('Would post', it['id'], it['type'], media_url(it['media']) if os.environ.get('MEDIA_BASE_URL') else it['media']); continue
        try:
            mid = publish(it)
            state[it['id']] = dict(status='posted', media_id=mid, at=now.isoformat()); save_state(state)
            print('Posted', it['id'], mid);
            if it.get('follow_up'): report.append(f"- **Posted** {at.strftime('%a %d %b %H:%M')} · {it['source']}. Follow-up, if you want it: {it['follow_up']}")
        except Exception as e:
            print('FAILED', it['id'], e)
            if is_block(e) and not paused:
                paused = dict(since=now.isoformat(), reason=str(e), item=it['id'])
                save_pause(paused)
                report.append(f"- **Posting paused.** Instagram refused {it['source']} ({e}). Meta has blocked this app's access to the account, "
                              "so nothing more will be tried (retrying only looks more like a bot). Open the Instagram app and clear any notice "
                              "(\"confirm it's you\", Settings › Account Status). Then run Actions › Instagram autopost › Run workflow with \"check\": "
                              "if the account answers, posting resumes on the next run. Anything more than 3 hours late by then is reported as missed.")
                break
            report.append(f"- **Failed** {it['source']} ({e}). It will be tried again on the next run until {(at + WINDOW).strftime('%H:%M')}.")
    if not dry: save_state(state)
    if report:
        text = 'Instagram autopost update for @cjgraham-hue:\n\n' + '\n'.join(report) + '\n'
        print(text)
        out = os.environ.get('REPORT_FILE')
        if out: open(out, 'w', encoding='utf-8').write(text)
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv))
