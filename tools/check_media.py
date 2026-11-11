#!/usr/bin/env python3
"""Checks Reels, stories and covers for a hard-edged box behind the words.

The Reel of 11 Nov 2026 went out with a translucent dark rectangle behind its words: the 4:5 grid crop
(rows 285 to 1635) was darkened and the strips above and below it weren't, so two straight lines crossed the
frame. The words should sit on the picture itself, on a darkening that covers the whole frame, or on a soft
gradient that fades out, never inside a visible rectangle.

What it looks for:
  videos  a straight edge across the whole width, at the top or bottom of the 4:5 crop, that stays put for most
          of the video while the picture on both sides of it moves (a fixed overlay over moving footage);
  stills  9:16 pictures (covers, story images) whose 4:5 crop is darker or lighter than the strips above and
          below it, with picture detail on both sides of each edge (so a deliberate flat colour panel passes).

usage:
  python3 tools/check_media.py FILE...          check these files (.mp4, .jpg, .png)
  python3 tools/check_media.py --schedule       check every Reel, story and cover in schedule.json not posted yet
Exit status 1 if anything is flagged. Needs ffmpeg, numpy and Pillow.
"""
import json, os, subprocess, sys, datetime as dt

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA = os.path.join(HERE, 'docs', 'media')
W, H = 540, 960          # videos are checked at half size
CROP_TOP, CROP_BOTTOM = 285, 1635   # the 4:5 crop of a 1080 x 1920 frame


def read_video(path, fps=2):
    cmd = ['ffmpeg', '-v', 'error', '-i', path, '-vf', f'fps={fps},scale={W}:{H},format=gray',
           '-f', 'rawvideo', '-']
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    n = len(raw) // (W * H)
    return np.frombuffer(raw[:n * W * H], np.uint8).reshape(n, H, W).astype(np.float32)


def row_steps(frame, k=3):
    """For each row y: the median change from the k rows above to the k rows below, and the share of columns
    that change the same way by more than 2 levels."""
    c = np.cumsum(np.vstack([np.zeros((1, frame.shape[1]), np.float32), frame]), axis=0)
    ys = np.arange(k, frame.shape[0] - k)
    above = (c[ys] - c[ys - k]) / k            # rows y-k .. y-1
    below = (c[ys + k] - c[ys]) / k            # rows y .. y+k-1
    d = below - above
    med = np.median(d, axis=1)
    agree = np.where(med[:, None] >= 0, d > 2, d < -2).mean(axis=1)
    return ys, med, agree


def fixed_edges(frames):
    """Rows where a strong, full-width edge sits in at least 60% of the frames, always the same way round."""
    hits, signs = {}, {}
    for f in frames:
        ys, med, agree = row_steps(f)
        for y in ys[(np.abs(med) >= 5) & (agree >= 0.8)]:
            m = med[y - ys[0]]
            hits[y] = hits.get(y, 0) + 1
            signs[y] = signs.get(y, 0) + (1 if m > 0 else -1)
    n = len(frames)
    rows = [y for y, c in hits.items() if c >= max(3, 0.6 * n) and abs(signs[y]) >= 0.9 * c]
    merged = []
    for y in sorted(rows):
        if merged and y - merged[-1][-1] <= 4:
            merged[-1].append(y)
        else:
            merged.append([y])
    return [int(round(np.mean(g))) for g in merged]


def moves(frames, y0, y1):
    """How much the picture changes between the first and last third of the video in rows y0..y1, after
    blurring away grain (mean absolute difference, in levels)."""
    n = len(frames)
    if n < 3 or y0 < 0 or y1 > H or y1 <= y0:
        return 0.0
    third = max(1, n // 3)
    a = frames[:third, y0:y1].mean(0)
    b = frames[-third:, y0:y1].mean(0)
    def blur(x):
        h = (x.shape[0] // 2) * 2
        w = (x.shape[1] // 4) * 4
        return x[:h, :w].reshape(h // 2, 2, w // 4, 4).mean((1, 3))
    return float(np.abs(blur(a) - blur(b)).mean())


def detail(frames, y0, y1):
    """Picture detail in rows y0..y1: the spread of brightness along the rows, averaged over the video."""
    return float(np.mean([f[y0:y1].std(axis=1).mean() for f in frames[::max(1, len(frames) // 8)]]))


def holds(frames, y):
    """The brightness change across row y measured a little further out (4 to 24 px either side at full size),
    so a thin line in the picture, which dips and comes back, doesn't count as an edge."""
    if y < 12 or y > H - 12:
        return 0.0
    return float(np.median([np.median(f[y + 2:y + 12].mean(0) - f[y - 12:y - 2].mean(0)) for f in frames]))


def check_video(path):
    frames = read_video(path)
    if len(frames) < 3:
        return []
    found = []
    for y in fixed_edges(frames):
        # Only the 4:5 crop's edges: a horizon or a window frame elsewhere can stay put during a slow pan too.
        if min(abs(y * 2 - CROP_TOP), abs(y * 2 - CROP_BOTTOM)) > 6 or abs(holds(frames, y)) < 5:
            continue
        # Look right next to the edge (4 to 24 px either side at full size), where words never sit.
        up, down = (y - 12, y - 2), (y + 2, y + 12)
        m_up, m_down = moves(frames, *up), moves(frames, *down)
        d_up, d_down = detail(frames, *up), detail(frames, *down)
        if min(m_up, m_down) >= 1.2 and min(d_up, d_down) >= 4:
            found.append(f'a straight line crosses the whole frame at {y * 2} px from the top, the edge of the 4:5 crop, '
                         f'and stays put while the picture moves on both sides of it (a box behind the words)')
    return found


def check_still(path):
    try:
        im = Image.open(path).convert('L')
    except OSError:
        return ['it could not be opened as a picture']
    if abs(im.width / im.height - 9 / 16) > 0.01:
        return []                       # only 9:16 frames have strips outside the 4:5 crop
    g = np.asarray(im.resize((1080, 1920)), np.float32)
    edges = []
    for y, darker_inside_means in ((CROP_TOP, -1), (CROP_BOTTOM, 1)):
        d = g[y:y + 4].mean(0) - g[y - 4:y].mean(0)
        mean = float(d.mean())
        share = float(max((d > 3).mean(), (d < -3).mean()))
        flat = min(g[y - 24:y - 4].std(axis=1).mean(), g[y + 4:y + 24].std(axis=1).mean()) < 4
        edges.append((mean, share, flat, darker_inside_means))
    (tm, ts, tflat, _), (bm, bs, bflat, _) = edges
    # A box: the top edge and the bottom edge change brightness opposite ways (inside darker, or inside lighter).
    box = (tm * bm < 0 and min(abs(tm), abs(bm)) >= 5 and min(ts, bs) >= 0.6 and max(ts, bs) >= 0.85
           and not tflat and not bflat)
    if box:
        return [f'the 4:5 crop ({CROP_TOP} to {CROP_BOTTOM} px) is {"darker" if bm > 0 else "lighter"} than the '
                f'strips above and below it, so a box shows on the full 9:16 frame']
    return []


def check(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in ('.mp4', '.mov', '.m4v'):
        return check_video(path)
    if ext in ('.jpg', '.jpeg', '.png'):
        return check_still(path)
    return []


def scheduled_files():
    with open(os.path.join(HERE, 'schedule.json')) as f:
        data = json.load(f)
    items = data['items'] if isinstance(data, dict) else data
    posted = {}
    try:
        with open(os.path.join(HERE, 'posted.json')) as f:
            posted = json.load(f)
    except (OSError, ValueError):
        pass
    now = dt.datetime.now(dt.timezone.utc)
    files = []
    for it in items:
        if it.get('id') in posted or it.get('type') not in ('reel', 'story_video', 'story_image'):
            continue
        try:
            if dt.datetime.fromisoformat(it['post_at']) < now:
                continue
        except (KeyError, ValueError):
            pass
        for key in ('media', 'cover'):
            if it.get(key):
                files.append(os.path.join(MEDIA, it[key]))
    return files


def main(argv):
    files = scheduled_files() if argv == ['--schedule'] else argv
    if not files:
        print(__doc__.strip().split('\n\n')[-1])
        return 0
    bad = 0
    for path in files:
        if not os.path.exists(path):
            print(f'?  {os.path.basename(path)}: file not found')
            continue
        try:
            problems = check(path)
        except subprocess.CalledProcessError:
            print(f'?  {os.path.basename(path)}: ffmpeg could not read it')
            continue
        for p in problems:
            print(f'✗  {os.path.basename(path)}: {p}')
        bad += bool(problems)
    print(f'{len(files)} files checked, {bad} with a box behind the words.' if bad
          else f'{len(files)} files checked, no boxes behind the words.')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
