#!/usr/bin/env python3
"""Hub feed: links this repository to Cameron's private ProFluency hub.

Runs on the same self-hosted runner as the autopost (Cameron's own machine), so Meta sees the same home address
for everything the account does. Every 15 minutes in the day it asks the hub what Cameron has clicked, and:

  1. posts the replies to Instagram comments that Cameron pressed "Send" on in the hub (nothing is ever sent
     without that click), a few seconds apart, as replies from @profluencyuk to comments on its own posts;
  2. merges (or closes) this repository's pull requests that Cameron approved (or declined) in the hub;
  3. about every two hours (or straight after sending replies), sends the hub the account's numbers, recent posts
     with their likes and comments (plus reach, saves and shares if the token has the insights permission), the
     stories live right now, and the comments still waiting for a reply; and, if FB_PAGE_ID and FB_PAGE_TOKEN are
     set, the Facebook Page's numbers.

It never posts anything else, never touches the schedule, and stops at once if posting is paused (pause.json).
Because this repository is public, its logs show counts only: no comment text, no usernames, no numbers.

Settings (environment variables): IG_USER_ID, IG_ACCESS_TOKEN (as for publish.py), HUB_URL and HUB_FEED_TOKEN
(both repository secrets, so the hub's address never shows in this public repository's logs; HUB_FEED_TOKEN is the
same value as in the website repository, and it only lets the feed read clicks and send numbers back, not read the
hub's other data), GITHUB_TOKEN and REPO (from the workflow), optional FB_PAGE_ID and FB_PAGE_TOKEN, optional
GRAPH_VERSION, and HUB_FEED_FULL=1 to read Instagram whatever the time.
Python 3.9+, standard library only.
"""
import json, os, random, re, sys, time, urllib.error, urllib.parse, urllib.request, datetime as dt

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION = os.environ.get('GRAPH_VERSION', 'v23.0')
IG = os.environ.get('IG_API_BASE', 'https://graph.instagram.com').rstrip('/') + f'/{VERSION}'
FB = os.environ.get('FB_API_BASE', 'https://graph.facebook.com').rstrip('/') + f'/{VERSION}'
GITHUB_API = os.environ.get('GITHUB_API_BASE', 'https://api.github.com').rstrip('/')   # the three *_BASE settings are for testing only
MAX_REPLIES = 6            # per run; the rest wait for the next run
READ_EVERY = dt.timedelta(minutes=110)   # a full Instagram read at most this often, unless replies were just sent
# The hub may only merge plan and media changes here: this repo's code runs on Cameron's own machine,
# so anything touching publish.py, tools/ or workflows has to be reviewed and merged on GitHub.
SAFE_FILES = re.compile(r'^(schedule\.json|posted\.json|token-status\.json|platforms/[^/]+\.json|docs/.+|[^/]+\.md)$')
COMMENT_DAYS = 60          # comments on posts from the last 60 days
INSIGHT_POSTS = 20         # posts whose reach and saves are refreshed each run


def setting(name, required=True):
    value = os.environ.get(name, '').strip()
    if required and not value:
        sys.exit(f'hub feed: missing setting {name}')
    return value


class ApiError(RuntimeError):
    def __init__(self, status, code, msg):
        super().__init__(f'{status} {msg}')
        self.status, self.code, self.msg = status, code, msg


def request(url, method='GET', params=None, headers=None, body=None, timeout=60):
    params = dict(params or {})
    data = None
    if method == 'GET' and params:
        url += ('&' if '?' in url else '?') + urllib.parse.urlencode(params)
    elif body is not None:
        data = json.dumps(body).encode()
    elif params:
        data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors='replace')
        try:
            err = json.loads(raw)
            err = err.get('error', err) if isinstance(err, dict) else {}
        except ValueError:
            err = {}
        if not isinstance(err, dict):
            err = {'message': str(err)}
        raise ApiError(e.code, err.get('code'), str(err.get('message', raw))[:200]) from None


def ig(path, method='GET', **params):
    params['access_token'] = setting('IG_ACCESS_TOKEN')
    return request(f'{IG}/{path}', method, params)


def hub(path, body=None):
    headers = {'X-Hub-Sync': setting('HUB_FEED_TOKEN'), 'Accept': 'application/json', 'User-Agent': 'profluency-hub-feed'}
    if body is not None:
        headers['Content-Type'] = 'application/json'
    url = setting('HUB_URL').rstrip('/') + path
    return request(url, 'POST' if body is not None else 'GET', headers=headers, body=body, timeout=60)


def github(path, method='GET', body=None):
    headers = {'Authorization': 'Bearer ' + setting('GITHUB_TOKEN'), 'Accept': 'application/vnd.github+json', 'User-Agent': 'profluency-hub-feed'}
    if body is not None:
        headers['Content-Type'] = 'application/json'
    return request(GITHUB_API + path, method, headers=headers, body=body)


def is_block(e):
    m = (getattr(e, 'msg', '') or '').lower()
    return getattr(e, 'code', None) == 190 or any(w in m for w in ('blocked', 'restricted', 'checkpoint', 'suspicious', 'spam'))


def is_permission(e):
    return getattr(e, 'code', None) in (10, 200) or 'permission' in (getattr(e, 'msg', '') or '').lower()


def iso(ts):
    """Instagram's 2026-10-30T12:05:23+0000 as ISO 8601."""
    try:
        return dt.datetime.strptime(ts, '%Y-%m-%dT%H:%M:%S%z').isoformat()
    except (TypeError, ValueError):
        return ts


# ------------------------------------------------------------------------------------- replies Cameron sent

def send_replies(state, paused):
    acks = {}
    queue = [(k, v) for k, v in (state.get('replies') or {}).items()
             if k.startswith('ig:') and isinstance(v, dict) and v.get('status') == 'send'
             and not v.get('applied') and not v.get('failed') and (v.get('text') or '').strip()]
    if paused and queue:
        print(f'hub feed: {len(queue)} replies wait, because posting is paused')
        return acks
    for n, (key, item) in enumerate(queue[:MAX_REPLIES]):
        if n:
            time.sleep(random.uniform(6, 14))     # a person doesn't reply to five comments in the same second
        try:
            res = ig(f"{key[3:]}/replies", 'POST', message=item['text'].strip()[:2000])
            acks[key] = {'at': item.get('at'), 'applied': True, 'result': 'Sent on Instagram.', 'reply_id': res.get('id', '')}
        except ApiError as e:
            if is_block(e):
                acks[key] = {'at': item.get('at'), 'failed': True, 'result': 'Instagram refused it and may be limiting the account. Nothing else will be sent; check the Instagram app.'}
                print('hub feed: Instagram refused a reply; stopping replies for this run')
                break
            acks[key] = {'at': item.get('at'), 'failed': True, 'result': f'Instagram said no ({e.msg[:120]}). Reply in the app instead.'}
    sent = sum(1 for a in acks.values() if a.get('applied'))
    if queue:
        print(f'hub feed: replies sent {sent}, not sent {len(acks) - sent}, waiting {max(0, len(queue) - MAX_REPLIES)}')
    return acks


# ------------------------------------------------------------------------------------- pull requests approved in the hub

def pr_files(repo, number):
    """Every file a pull request changes (GitHub lists 100 a page, up to 3,000)."""
    names = []
    for page in range(1, 31):
        batch = github(f'/repos/{repo}/pulls/{number}/files?per_page=100&page={page}')
        names += [f.get('filename', '') for f in batch]
        if len(batch) < 100:
            break
    return names


def apply_decisions(state):
    acks = {}
    repo = setting('REPO')
    for key, item in (state.get('decisions') or {}).items():
        if not key.startswith('pr:autopost:') or not isinstance(item, dict):
            continue
        if item.get('applied') or item.get('failed') or item.get('decision') not in ('approve', 'decline'):
            continue
        number = key.split(':')[2]
        try:
            pr = github(f'/repos/{repo}/pulls/{number}')
            if pr.get('merged'):
                result = {'applied': True, 'result': 'Already merged.'}
            elif pr.get('state') != 'open':
                result = {'failed': True, 'result': 'That pull request was closed on GitHub.'}
            elif item['decision'] == 'decline':
                if item.get('note'):
                    github(f'/repos/{repo}/issues/{number}/comments', 'POST', {'body': 'Declined in the hub: ' + item['note'][:500]})
                github(f'/repos/{repo}/pulls/{number}', 'PATCH', {'state': 'closed'})
                result = {'applied': True, 'result': 'Declined and closed. The branch is kept, so it can be reopened on GitHub.'}
            elif ((pr.get('head') or {}).get('repo') or {}).get('full_name') != repo:
                result = {'failed': True, 'result': 'It comes from outside (a fork), so review and merge it on GitHub.'}
            else:
                files = pr_files(repo, number)
                if len(files) < int(pr.get('changed_files') or 0):
                    result = {'failed': True, 'result': "GitHub didn't list all of its files, so review and merge it on GitHub."}
                elif any(not SAFE_FILES.match(name) for name in files):
                    result = {'failed': True, 'result': 'It changes the autopost code or a workflow, so review and merge it on GitHub.'}
                elif pr.get('draft'):
                    result = {'failed': True, 'result': 'It is still a draft. Mark it ready on GitHub first.'}
                else:
                    github(f'/repos/{repo}/pulls/{number}/merge', 'PUT', {'merge_method': 'squash'})
                    result = {'applied': True, 'result': 'Merged. It is in the schedule now.'}
        except ApiError as e:
            result = {'failed': True, 'result': f'GitHub said no ({e.msg[:120]}).'}
        acks[key] = {'at': item.get('at'), **result}
        print(f'hub feed: pull request {number}: {"done" if result.get("applied") else "not done"}')
    return acks


# ------------------------------------------------------------------------------------- Instagram numbers and comments

def instagram(previous):
    out = {'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'ok': True, 'note': ''}
    me = ig('me', fields='user_id,username,followers_count,follows_count,media_count')
    username = me.get('username', '')
    out['account'] = {k: me.get(k) for k in ('username', 'followers_count', 'follows_count', 'media_count')}

    # One follower count a day, kept from earlier runs, for the trend line.
    today = dt.date.today().isoformat()
    series = [p for p in (previous.get('followers_series') or []) if isinstance(p, dict) and p.get('date') != today][-120:]
    if me.get('followers_count') is not None:
        series.append({'date': today, 'value': me['followers_count']})
    out['followers_series'] = series

    media = ig(f"{setting('IG_USER_ID')}/media", fields='id,caption,media_type,media_product_type,permalink,timestamp,like_count,comments_count,thumbnail_url,media_url', limit=40).get('data', [])
    posts = []
    for m in media:
        kind = 'reel' if m.get('media_product_type') == 'REELS' else 'carousel' if m.get('media_type') == 'CAROUSEL_ALBUM' else 'post'
        posts.append({'id': m['id'], 'type': kind, 'caption': (m.get('caption') or '')[:400], 'permalink': m.get('permalink', ''),
                      'at': iso(m.get('timestamp')), 'likes': m.get('like_count'), 'comments': m.get('comments_count'),
                      'image': m.get('thumbnail_url') or (m.get('media_url') if m.get('media_type') != 'VIDEO' else '') or ''})

    # Reach, saves and shares need the instagram_business_manage_insights permission. Without it, likes and comments still work.
    out['insights_ok'] = True
    for p in posts[:INSIGHT_POSTS]:
        metrics = 'reach,saved,shares,views,total_interactions'
        try:
            data = ig(f"{p['id']}/insights", metric=metrics).get('data', [])
        except ApiError as e:
            if is_permission(e):
                out['insights_ok'] = False
                out['insights_note'] = 'Reach, saves and shares need the instagram_business_manage_insights permission on the token.'
                break
            try:
                data = ig(f"{p['id']}/insights", metric='reach,saved').get('data', [])
            except ApiError:
                continue
        for row in data:
            value = (row.get('values') or [{}])[0].get('value')
            name = {'saved': 'saves'}.get(row.get('name'), row.get('name'))
            if name in ('reach', 'saves', 'shares', 'views', 'total_interactions'):
                p[name] = value
    out['media'] = posts

    # Stories are only readable while they're live, so each run keeps what it saw (30 days).
    seen = {s['id']: s for s in (previous.get('stories') or []) if isinstance(s, dict) and s.get('id')}
    try:
        live = ig(f"{setting('IG_USER_ID')}/stories", fields='id,timestamp,media_type,permalink').get('data', [])
    except ApiError:
        live = []
    for s in live:
        row = seen.get(s['id'], {'id': s['id'], 'at': iso(s.get('timestamp')), 'type': 'story'})
        if out['insights_ok']:
            try:
                for m in ig(f"{s['id']}/insights", metric='reach,replies,shares,total_interactions').get('data', []):
                    row[m.get('name')] = (m.get('values') or [{}])[0].get('value')
            except ApiError:
                pass
        seen[s['id']] = row
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)).isoformat()
    out['stories'] = sorted([s for s in seen.values() if (s.get('at') or '') >= cutoff], key=lambda s: s.get('at') or '', reverse=True)[:120]

    # Comments still waiting for a reply from the account (none of its own, none it has already answered).
    waiting = []
    recent = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=COMMENT_DAYS)).isoformat()
    out['comments_ok'] = True
    for p in posts:
        if not p.get('comments') or (p.get('at') or '') < recent:
            continue
        try:
            rows = ig(f"{p['id']}/comments", fields='id,text,timestamp,username,like_count,replies{username}', limit=50).get('data', [])
        except ApiError as e:
            if is_permission(e):
                out['comments_ok'] = False
                out['comments_note'] = 'Reading comments needs the instagram_business_manage_comments permission on the token.'
                break
            continue
        for c in rows:
            if not c.get('text') or c.get('username', '').lower() == username.lower():
                continue
            replies = (c.get('replies') or {}).get('data', [])
            if any((r.get('username') or '').lower() == username.lower() for r in replies):
                continue
            waiting.append({'id': c['id'], 'username': c.get('username', ''), 'text': c['text'][:600], 'at': iso(c.get('timestamp')),
                            'likes': c.get('like_count', 0), 'media_id': p['id'], 'media_caption': p['caption'][:200],
                            'media_permalink': p['permalink'], 'media_type': p['type']})
    out['comments'] = sorted(waiting, key=lambda c: c['at'] or '', reverse=True)[:40]
    return out


def facebook():
    page, token = setting('FB_PAGE_ID', False), setting('FB_PAGE_TOKEN', False)
    if not page or not token:
        return None
    out = {'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'ok': True, 'note': ''}
    try:
        info = request(f'{FB}/{page}', params={'fields': 'name,followers_count,fan_count,link', 'access_token': token})
        out['page'] = {k: info.get(k) for k in ('name', 'followers_count', 'fan_count', 'link')}
        posts = request(f'{FB}/{page}/posts', params={'fields': 'id,message,created_time,permalink_url,shares,reactions.summary(total_count).limit(0),comments.summary(total_count).limit(0)', 'limit': 15, 'access_token': token}).get('data', [])
        out['posts'] = [{'id': p['id'], 'message': (p.get('message') or '')[:200], 'at': iso(p.get('created_time')), 'permalink': p.get('permalink_url', ''),
                         'reactions': ((p.get('reactions') or {}).get('summary') or {}).get('total_count', 0),
                         'comments': ((p.get('comments') or {}).get('summary') or {}).get('total_count', 0),
                         'shares': (p.get('shares') or {}).get('count', 0)} for p in posts]
    except ApiError as e:
        out = {'generated_at': out['generated_at'], 'ok': False, 'note': f'Facebook said no ({e.msg[:120]}).'}
    return out


def read_due(previous, acks):
    """A full Instagram read about every two hours, after sending replies, or when asked."""
    if os.environ.get('HUB_FEED_FULL') == '1' or any(a.get('applied') for a in acks.values()):
        return True
    try:
        last = dt.datetime.fromisoformat(str(previous.get('generated_at')))
    except ValueError:
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=dt.timezone.utc)
    return dt.datetime.now(dt.timezone.utc) - last >= READ_EVERY


def main():
    paused = os.path.exists(os.path.join(HERE, 'pause.json'))
    try:
        export = hub('/api/sync/export')
    except ApiError as e:
        if e.status in (401, 404):
            # The hub isn't deployed yet, or doesn't know this token yet: nothing to do, and no failure email.
            print('hub feed: the hub is not ready for this token yet (deploy the site after adding HUB_FEED_TOKEN)')
            return
        raise
    state = export.get('state') or {}
    previous = (export.get('parts') or {}).get('instagram') or {}

    acks = {'replies': send_replies(state, paused), 'decisions': apply_decisions(state)}

    parts = {}
    if read_due(previous, acks['replies']):
        if paused:
            parts['instagram'] = {**previous, 'ok': False, 'note': 'Posting is paused (pause.json), so the hub feed is leaving Instagram alone until it is cleared.'}
            print('hub feed: posting is paused, so Instagram was not read')
        else:
            try:
                parts['instagram'] = instagram(previous)
                p = parts['instagram']
                print(f"hub feed: Instagram read: {len(p['media'])} posts, {len(p['stories'])} stories, {len(p['comments'])} comments waiting, insights {'on' if p['insights_ok'] else 'off'}")
            except ApiError as e:
                parts['instagram'] = {**previous, 'ok': False, 'note': f'Instagram said no ({e.msg[:120]}).'}
                print('hub feed: Instagram could not be read' + (' (Meta may be limiting the account)' if is_block(e) else ''))
        fb = facebook()
        if fb is not None:
            parts['facebook'] = fb
            print(f"hub feed: Facebook {'read' if fb.get('ok') else 'not read'}")

    if not parts and not acks['replies'] and not acks['decisions']:
        print('hub feed: nothing to do')
        return
    hub('/api/sync/import', {'parts': parts, 'acks': acks})
    print('hub feed: sent to the hub')


if __name__ == '__main__':
    try:
        main()
    except ApiError as e:
        sys.exit(f'hub feed: the hub or GitHub said no ({e.status})')
