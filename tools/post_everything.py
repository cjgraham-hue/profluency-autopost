#!/usr/bin/env python3
"""Turn every by-hand ("manual") item that is still to come into an automatic post with a follow-up note.
Items already in posted.json are left alone. Run from the repo root: python3 tools/post_everything.py"""
import json, os, datetime as dt
from zoneinfo import ZoneInfo
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
path = os.path.join(HERE, 'schedule.json')
data = json.load(open(path, encoding='utf-8'))
try: done = json.load(open(os.path.join(HERE, 'posted.json'), encoding='utf-8'))
except (OSError, ValueError): done = {}
now = dt.datetime.now(ZoneInfo('Europe/London'))

def follow_up(text):
    t = text.replace('Post from the Instagram app: this story was made for', 'This story was made for')
    t = t.replace('Add the sticker.', 'To add it, save the story from Instagram, then post it again with the sticker.')
    t = t.replace("Post from the Instagram app: share three to five of this week's replies on top of this story.",
                  "This story was made to have three to five of this week's replies on top. Save it from Instagram, "
                  "then post it again with the replies, or share the replies as stories of their own.")
    return t

changed = []
for it in data['items']:
    if 'manual' in it and it['id'] not in done and dt.datetime.fromisoformat(it['post_at']) > now:
        it['follow_up'] = follow_up(it.pop('manual'))
        changed.append(it['id'])
json.dump(data, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
open(path, 'a', encoding='utf-8').write('\n')
print(f'{len(changed)} item(s) will now post automatically:', *changed, sep='\n  ')
