#!/usr/bin/env python3
"""ProFluency pins: posts the month's Pinterest pins from platforms/platforms-*.json at their planned UK times.
Runs with the Instagram autopost (every 15 minutes). Python 3.9+, standard library only.

Only pins with "status": "to do" are posted. Pins marked "scheduled" or "already there" were set up by hand in
Pinterest, so they are left alone. After a pin posts, its status becomes "posted" and its Pinterest id is saved
in the same file, so it is never posted twice and the hub counts it as live.

Settings (environment variables)
  PINTEREST_TOKEN    an access token with boards:read and pins:write (pins:read and user_accounts:read too)
  PINTEREST_API      optional, default https://api.pinterest.com/v5
  WINDOW_HOURS       optional, default 12: a pin more than this late is reported, not posted

Usage
  python3 pins.py --check      check the token, that every board exists and every image link works; posts nothing
  python3 pins.py --dry-run    show what would be posted now; posts nothing
  python3 pins.py              post every pin that is due
  python3 pins.py --only ID    post one pin now, whatever its time
"""
import glob, json, os, sys, urllib.request, urllib.error, datetime as dt
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
LONDON = ZoneInfo('Europe/London')
API = os.environ.get('PINTEREST_API', 'https://api.pinterest.com/v5').rstrip('/')
WINDOW = dt.timedelta(hours=float(os.environ.get('WINDOW_HOURS', '12')))


def call(method, path, body=None):
    token = os.environ.get('PINTEREST_TOKEN', '').strip()
    if not token: raise SystemExit('PINTEREST_TOKEN is not set.')
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body else None,
                                 headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=60) as r: return json.loads(r.read() or b'{}')
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'Pinterest {e.code}: {e.read().decode(errors="replace")[:300]}')


def boards():
    out, bookmark = {}, None
    while True:
        page = call('GET', '/boards?page_size=100' + (f'&bookmark={bookmark}' if bookmark else ''))
        for b in page.get('items', []): out[b['name'].strip().lower()] = b['id']
        bookmark = page.get('bookmark')
        if not bookmark: return out


def load():
    """Every pin from every month file, with the file it came from."""
    months = []
    for path in sorted(glob.glob(os.path.join(HERE, 'platforms', 'platforms-*.json'))):
        months.append((path, json.load(open(path, encoding='utf-8'))))
    return months


def image_url(month, pin): return month.get('image_base', '').rstrip('/') + '/' + pin['image']


def when(pin): return dt.datetime.fromisoformat(f"{pin['date']}T{pin['time']}").replace(tzinfo=LONDON)


def post(month, pin, board_ids):
    board = board_ids.get(pin['board'].strip().lower())
    if not board: raise RuntimeError(f"no board called \"{pin['board']}\" on the account")
    body = {'board_id': board, 'title': pin['title'][:100], 'description': pin.get('description', '')[:800],
            'link': pin.get('link') or None, 'alt_text': (pin.get('alt') or '')[:500] or None,
            'media_source': {'source_type': 'image_url', 'url': image_url(month, pin)}}
    return call('POST', '/pins', {k: v for k, v in body.items() if v is not None})['id']


def main(args):
    months = load()
    todo = [(path, m, p) for path, m in months for p in m.get('pins', []) if (p.get('status') or '').strip().lower() == 'to do']

    if '--check' in args:
        me = call('GET', '/user_account')
        print('Account:', me.get('username'), '| type:', me.get('account_type'))
        ids = boards(); bad = 0
        for _, m, p in todo:
            if p['board'].strip().lower() not in ids: bad += 1; print('No such board:', p['board'], '(', p['id'], ')')
            try:
                with urllib.request.urlopen(urllib.request.Request(image_url(m, p), method='HEAD'), timeout=30) as r:
                    if not r.headers.get('Content-Type', '').startswith('image/'): bad += 1; print('Not an image:', image_url(m, p))
            except Exception as e: bad += 1; print('Image not reachable:', image_url(m, p), e)
        print(f'{len(todo)} pins to post; {len(ids)} boards on the account; {bad} problem(s).')
        return 1 if bad else 0

    dry = '--dry-run' in args
    only = args[args.index('--only') + 1] if '--only' in args else None
    now = dt.datetime.now(LONDON)
    report, changed, ids = [], set(), None
    for path, m, p in todo:
        if only and p['id'] != only: continue
        at = when(p)
        if not only and at > now: continue
        if not only and now - at > WINDOW:
            report.append(f"- **Missed pin** {at:%a %d %b %H:%M} · {p['title'][:80]} (more than {WINDOW.total_seconds() / 3600:g} h late, not posted). "
                          f"Post it with pins.py --only {p['id']}.")
            if not dry: p['status'] = 'missed'; changed.add(path)
            continue
        if dry: print('Would pin', p['id'], 'to', p['board'], image_url(m, p)); continue
        try:
            if ids is None: ids = boards()
            pid = post(m, p, ids)
            p['status'] = 'posted'; p['pin_id'] = pid; p['posted_at'] = now.isoformat(timespec='minutes'); changed.add(path)
            print('Pinned', p['id'], pid)
        except Exception as e:
            print('FAILED', p['id'], e)
            report.append(f"- **Pin failed** {at:%a %d %b %H:%M} · {p['title'][:80]} ({e}). It is tried again on the next run.")
    for path, m in months:
        if path in changed:
            with open(path, 'w', encoding='utf-8') as f: json.dump(m, f, ensure_ascii=False, indent=1); f.write('\n')
    if report:
        text = 'Pinterest update for @cjgraham-hue:\n\n' + '\n'.join(report) + '\n'
        print(text)
        out = os.environ.get('REPORT_FILE')
        if out: open(out, 'a', encoding='utf-8').write(text)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
