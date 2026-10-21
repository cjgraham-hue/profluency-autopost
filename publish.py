#!/usr/bin/env python3
"""ProFluency autopost: publishes the month's stories, feed posts and Reels to @profluencyuk at the planned times,
then adds the first comment. Runs every 15 minutes (GitHub Actions, or cron on your computer); each run posts
whatever is due and not yet posted. Python 3.9+, standard library only.

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
they are emailed at their time instead.
"""
import json, os, sys, time, urllib.request, urllib.parse, urllib.error, datetime as dt
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEDULE = json.load(open(os.path.join(HERE, 'schedule.json'), encoding='utf-8'))
STATE_FILE = os.path.join(HERE, 'posted.json')
LONDON = ZoneInfo('Europe/London')
VERSION = os.environ.get('GRAPH_VERSION', 'v23.0')
API = f'https://graph.instagram.com/{VERSION}'
WINDOW = dt.timedelta(hours=float(os.environ.get('WINDOW_HOURS', '3')))

def env(name):
    v = os.environ.get(name, '').strip()
    if not v: sys.exit(f'Missing setting: {name}. See README.md.')
    return v

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
        try: msg = json.loads(body).get('error', {}).get('message', body)
        except ValueError: msg = body
        raise RuntimeError(f'{method} {path}: {e.code} {msg}') from None

def media_url(name): return env('MEDIA_BASE_URL').rstrip('/') + '/' + urllib.parse.quote(name)

def load_state():
    try: return json.load(open(STATE_FILE, encoding='utf-8'))
    except (OSError, ValueError): return {}
def save_state(s): json.dump(s, open(STATE_FILE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

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
    else: raise RuntimeError(f'unknown type {kind}')
    container = call('POST', f'{ig}/media', **p)['id']
    wait_ready(container, kind)
    media_id = call('POST', f'{ig}/media_publish', creation_id=container)['id']
    note = ''
    if it.get('first_comment'):
        try: call('POST', f'{media_id}/comments', message=it['first_comment'])
        except RuntimeError as e: note = f'posted, but the first comment failed ({e}); add the hashtags by hand'
    return media_id, note

def now_london(arg=None):
    return dt.datetime.fromisoformat(arg).astimezone(LONDON) if arg else dt.datetime.now(LONDON)

def main(argv):
    args = argv[1:]; state = load_state()
    items = SCHEDULE['items']; by_id = {i['id']: i for i in items}
    report = []          # lines for the run summary (and a GitHub issue when something needs you)

    if '--list' in args:
        for i in items:
            s = state.get(i['id'], {}).get('status', 'by hand' if 'manual' in i else 'waiting')
            print(f"{i['post_at'][:16].replace('T', ' ')}  {i['type']:<12} {s:<10} {i['id']}")
        return 0

    if '--check' in args:
        me = call('GET', 'me', fields='user_id,username,account_type')
        print('Account:', me.get('username'), '| type:', me.get('account_type'), '| id:', me.get('user_id'))
        if str(me.get('user_id')) != env('IG_USER_ID'): print('WARNING: IG_USER_ID does not match this token\'s account', me.get('user_id'))
        if me.get('account_type') not in ('BUSINESS',): print('WARNING: Stories can only be published by the API on a Business account.')
        lim = call('GET', f"{env('IG_USER_ID')}/content_publishing_limit", fields='quota_usage,config')
        print('Publishing allowance:', json.dumps(lim.get('data', lim)))
        bad = 0
        for i in items:
            if i['id'] in state: continue      # already done: its file may have been removed by the weekly cleanup
            for name in [i['media']] + ([i['cover']] if i.get('cover') else []):
                try:
                    with urllib.request.urlopen(urllib.request.Request(media_url(name), method='HEAD'), timeout=30) as r:
                        ct = r.headers.get('Content-Type', '')
                        if not (ct.startswith('image/') or ct.startswith('video/')): bad += 1; print('Not an image/video:', name, ct)
                except Exception as e: bad += 1; print('Media link not reachable:', media_url(name), e)
        print(f'{len(items)} items in the schedule; media links checked, {bad} problem(s).')
        return 1 if bad else 0

    if '--only' in args:
        it = by_id[args[args.index('--only') + 1]]
        mid, note = publish(it)
        state[it['id']] = dict(status='posted', media_id=mid, at=now_london().isoformat(), note=note); save_state(state)
        print('Posted', it['id'], mid, note); return 0

    dry = '--dry-run' in args or os.environ.get('DRY_RUN') == '1'
    now = now_london(args[args.index('--now') + 1] if '--now' in args else None)
    for it in items:
        if it['id'] in state: continue
        at = dt.datetime.fromisoformat(it['post_at'])
        if at > now: continue
        late = now - at
        if 'manual' in it:
            report.append(f"- **{at.strftime('%a %d %b %H:%M')}** · {it['source']}: {it['manual']}")
            if not dry: state[it['id']] = dict(status='by hand', at=now.isoformat())
            continue
        if late > WINDOW:
            report.append(f"- **Missed** {at.strftime('%a %d %b %H:%M')} · {it['source']} ({int(late.total_seconds() // 60)} min late, not posted). Post it by hand or run publish.py --only {it['id']}.")
            if not dry: state[it['id']] = dict(status='missed', at=now.isoformat())
            continue
        if dry: print('Would post', it['id'], it['type'], media_url(it['media']) if os.environ.get('MEDIA_BASE_URL') else it['media']); continue
        try:
            mid, note = publish(it)
            state[it['id']] = dict(status='posted', media_id=mid, at=now.isoformat(), note=note); save_state(state)
            print('Posted', it['id'], mid);
            if note: report.append(f"- {it['source']}: {note}")
            if it.get('follow_up'): report.append(f"- **Posted** {at.strftime('%a %d %b %H:%M')} · {it['source']}. Follow-up, if you want it: {it['follow_up']}")
        except Exception as e:
            print('FAILED', it['id'], e)
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
