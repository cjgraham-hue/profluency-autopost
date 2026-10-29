#!/usr/bin/env python3
"""Weekly media cleanup: removes the files in docs/media that belong to earlier weeks, once they're finished with.
Runs every Monday morning from .github/workflows/cleanup-media.yml. Run from the repo root:

  python3 tools/cleanup_media.py --dry-run              show what would be removed; removes nothing
  python3 tools/cleanup_media.py                        remove them (git rm), ready to commit
  python3 tools/cleanup_media.py --now 2026-11-02T06:30 pretend it's another time (for testing)

What goes: anything dated before this Monday 00:00 (UK time) that is finished with, i.e.
  - a scheduled item's file, carousel slides and Reel cover, once posted.json records it as "posted" or "by hand";
  - a file no item uses any more (e.g. the artwork a restyle replaced), going by the date in its name.
What stays: everything from this week on; anything not yet posted; and a "missed", failed or on-hold item's file
for four weeks, in case you want to post it by hand (python3 publish.py --only ID).
The originals are all backed up in Drive (Social media backup), and git history keeps every removed file.
"""
import json, os, re, sys, subprocess, datetime as dt
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA = os.path.join(HERE, 'docs', 'media')
LONDON = ZoneInfo('Europe/London')
DONE = ('posted', 'by hand')
KEEP_UNPOSTED = dt.timedelta(weeks=4)

def main(args):
    now = dt.datetime.fromisoformat(args[args.index('--now') + 1]).replace(tzinfo=LONDON) if '--now' in args else dt.datetime.now(LONDON)
    week_start = (now - dt.timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    items = json.load(open(os.path.join(HERE, 'schedule.json'), encoding='utf-8'))['items']
    try: state = json.load(open(os.path.join(HERE, 'posted.json'), encoding='utf-8'))
    except (OSError, ValueError): state = {}

    used = {}                                             # file -> the items that use it
    for it in items:
        for name in dict.fromkeys([it['media']] + it.get('slides', []) + ([it['cover']] if it.get('cover') else [])):
            used.setdefault(name, []).append(it)

    remove, kept = [], []
    for name in sorted(os.listdir(MEDIA)):
        if name.startswith('.'): continue
        if name in used:
            ok = True
            for it in used[name]:
                at = dt.datetime.fromisoformat(it['post_at'])
                status = state.get(it['id'], {}).get('status') or ('on hold' if it.get('hold') else None)
                if at >= week_start: ok = False                                   # this week or later
                elif status not in DONE:
                    ok = at < week_start - KEEP_UNPOSTED and ok                   # missed or failed: keep 4 weeks
                    if not ok: kept.append(f'{name} ({it["id"]} is {status or "not posted"})')
            if ok: remove.append(name)
        else:
            m = re.match(r'(\d{4}-\d{2}-\d{2})-', name)
            if not m: kept.append(f'{name} (no date in its name)'); continue
            if dt.date.fromisoformat(m.group(1)) < week_start.date(): remove.append(name)

    size = sum(os.path.getsize(os.path.join(MEDIA, n)) for n in remove)
    print(f'Removing {len(remove)} file(s), {size / 1e6:.0f} MB, from before {week_start:%a %d %b %Y}.')
    for n in remove: print('  -', n)
    if kept:
        print(f'Kept {len(kept)} older file(s) on purpose:')
        for k in kept: print('  ·', k)
    if remove and '--dry-run' not in args:
        for i in range(0, len(remove), 100):
            subprocess.run(['git', 'rm', '-q', '--'] + [os.path.join('docs', 'media', n) for n in remove[i:i + 100]], cwd=HERE, check=True)
    out = os.environ.get('GITHUB_STEP_SUMMARY')
    if out:
        with open(out, 'a', encoding='utf-8') as f:
            f.write(f'### Media cleanup\nRemoved {len(remove)} file(s), {size / 1e6:.0f} MB, from before {week_start:%a %d %b %Y}.\n')
            if kept: f.write('\nKept on purpose:\n' + ''.join(f'- {k}\n' for k in kept))
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
