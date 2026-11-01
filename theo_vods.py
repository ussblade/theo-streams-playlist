#!/usr/bin/env python3
"""Keep a private YouTube playlist of Theo's (t3dotgg) unlisted stream VODs.

Reads the fan-maintained index, adds new streams to the top of the playlist,
and removes each stream KEEP_DAYS after its stream date.
"""

import argparse
import datetime
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

INDEX_URL = 'https://raw.githubusercontent.com/NikolaM-Dev/theo-t3dotgg-vods__md/main/README.md'
PLAYLIST_TITLE = 'Theo streams'
START_DATE = datetime.date(2026, 10, 25)
KEEP_DAYS = 30
TIMEZONE = ZoneInfo('America/Chicago')
STATE_PATH = Path(__file__).with_name('state.json')
API = 'https://www.googleapis.com/youtube/v3'

# - _2026-10-25_ [Title](https://www.youtube.com/watch?v=ID); one old entry is dated 2025-06_25.
ENTRY_RE = re.compile(r'^\s*-\s*_(\d{4})-(\d{2})[-_](\d{2})_\s*\[(.*)\]\((\S+)\)\s*$')
VIDEO_ID_RE = re.compile(r'(?:[?&]v=|/live/|youtu\.be/)([A-Za-z0-9_-]{11})')


def parse_index(markdown):
    """Return [{'id', 'date', 'title'}] for every stream line in the index."""
    streams = []
    for line in markdown.splitlines():
        entry = ENTRY_RE.match(line)
        if not entry:
            continue
        video = VIDEO_ID_RE.search(entry.group(5))
        if not video:
            continue
        year, month, day, title = entry.group(1, 2, 3, 4)
        streams.append({
            'id': video.group(1),
            'date': datetime.date(int(year), int(month), int(day)),
            'title': title,
        })
    return streams


def fetch_index():
    with urllib.request.urlopen(INDEX_URL, timeout=30) as response:
        return response.read().decode('utf-8')


def load_state():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {'playlist_id': None, 'videos': {}}


def save_state(state):
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True) + '\n')


class ApiError(Exception):
    def __init__(self, status, reason, message):
        super().__init__(f'YouTube API error {status} ({reason}): {message}')
        self.status = status
        self.reason = reason


class YouTube:
    def __init__(self, client_id, client_secret, refresh_token):
        body = urllib.parse.urlencode({
            'client_id': client_id,
            'client_secret': client_secret,
            'refresh_token': refresh_token,
            'grant_type': 'refresh_token',
        }).encode()
        try:
            with urllib.request.urlopen('https://oauth2.googleapis.com/token', body, timeout=30) as response:
                self.token = json.load(response)['access_token']
        except urllib.error.HTTPError as error:
            raise SystemExit(f'Google sign-in failed ({error.code}): {error.read().decode()}\n'
                             'The refresh token may have been revoked; run get_refresh_token.py again.')

    def call(self, method, path, params, body=None):
        url = f'{API}/{path}?{urllib.parse.urlencode(params)}'
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(url, data=data, method=method, headers={
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json',
        })
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                text = response.read()
                return json.loads(text) if text else {}
        except urllib.error.HTTPError as error:
            try:
                details = json.loads(error.read())['error']
                reason = details['errors'][0]['reason']
                message = details['message']
            except (ValueError, KeyError, IndexError):
                reason, message = 'unknown', error.reason
            raise ApiError(error.code, reason, message) from None

    def pages(self, path, params):
        params = dict(params, maxResults=50)
        while True:
            page = self.call('GET', path, params)
            yield from page.get('items', [])
            if 'nextPageToken' not in page:
                return
            params['pageToken'] = page['nextPageToken']

    def find_playlist(self, title):
        for playlist in self.pages('playlists', {'part': 'snippet', 'mine': 'true'}):
            if playlist['snippet']['title'] == title:
                return playlist['id']
        return None

    def create_playlist(self, title):
        return self.call('POST', 'playlists', {'part': 'snippet,status'}, {
            'snippet': {'title': title, 'description': "Theo's stream VODs, added automatically."},
            'status': {'privacyStatus': 'private'},
        })['id']

    def playlist_items(self, playlist_id):
        """Return {video_id: playlist_item_id} for the playlist's current contents."""
        items = self.pages('playlistItems', {'part': 'snippet', 'playlistId': playlist_id})
        return {item['snippet']['resourceId']['videoId']: item['id'] for item in items}

    def add_to_top(self, playlist_id, video_id):
        self.call('POST', 'playlistItems', {'part': 'snippet'}, {'snippet': {
            'playlistId': playlist_id,
            'position': 0,
            'resourceId': {'kind': 'youtube#video', 'videoId': video_id},
        }})

    def remove(self, item_id):
        self.call('DELETE', 'playlistItems', {'id': item_id})


def is_expired(stream_date, today):
    return today >= stream_date + datetime.timedelta(days=KEEP_DAYS)


def plan(streams, state, today):
    """Return (streams to add oldest first, video ids to remove)."""
    to_add = sorted(
        (s for s in streams
         if s['date'] >= START_DATE and not is_expired(s['date'], today) and s['id'] not in state['videos']),
        key=lambda s: s['date'],
    )
    to_remove = [
        video_id for video_id, video in state['videos'].items()
        if video['status'] == 'added' and is_expired(datetime.date.fromisoformat(video['date']), today)
    ]
    return to_add, to_remove


def sync(youtube, streams, state, today):
    if not state['playlist_id']:
        state['playlist_id'] = youtube.find_playlist(PLAYLIST_TITLE) or youtube.create_playlist(PLAYLIST_TITLE)
        print(f'Using playlist "{PLAYLIST_TITLE}" ({state["playlist_id"]})')
        save_state(state)
    current = youtube.playlist_items(state['playlist_id'])
    to_add, to_remove = plan(streams, state, today)

    # Oldest first, each at the top, so the newest stream ends up first.
    for stream in to_add:
        record = {'date': stream['date'].isoformat(), 'title': stream['title'], 'status': 'added'}
        if stream['id'] in current:
            print(f'Already in playlist: {stream["date"]} {stream["title"]}')
        else:
            try:
                youtube.add_to_top(state['playlist_id'], stream['id'])
            except ApiError as error:
                if error.reason != 'videoNotFound':
                    raise
                # Removed or made private; it stays out of state so a later run can retry.
                print(f'Skipped, video unavailable: {stream["date"]} {stream["title"]} ({stream["id"]})')
                continue
            print(f'Added: {stream["date"]} {stream["title"]}')
        state['videos'][stream['id']] = record
        save_state(state)

    for video_id in to_remove:
        video = state['videos'][video_id]
        item_id = current.get(video_id)
        if item_id:
            youtube.remove(item_id)
            print(f'Removed (older than {KEEP_DAYS} days): {video["date"]} {video["title"]}')
        video['status'] = 'removed'
        save_state(state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true',
                        help='show what would change, without signing in to YouTube')
    args = parser.parse_args()

    streams = parse_index(fetch_index())
    if not streams:
        raise SystemExit('No streams found in the fan index; its format may have changed.')
    today = datetime.datetime.now(TIMEZONE).date()
    print(f'Fan index: {len(streams)} streams, newest {max(s["date"] for s in streams)}. Today: {today}.')
    state = load_state()

    if args.dry_run:
        to_add, to_remove = plan(streams, state, today)
        for stream in to_add:
            print(f'Would add: {stream["date"]} {stream["title"]} ({stream["id"]})')
        for video_id in to_remove:
            print(f'Would remove: {state["videos"][video_id]["date"]} {state["videos"][video_id]["title"]}')
        if not to_add and not to_remove:
            print('Nothing to change.')
        return

    missing = [name for name in ('YT_CLIENT_ID', 'YT_CLIENT_SECRET', 'YT_REFRESH_TOKEN') if not os.environ.get(name)]
    if missing:
        raise SystemExit(f'Missing settings: {", ".join(missing)}. See README.md, step 3.')
    youtube = YouTube(os.environ['YT_CLIENT_ID'], os.environ['YT_CLIENT_SECRET'], os.environ['YT_REFRESH_TOKEN'])
    sync(youtube, streams, state, today)


if __name__ == '__main__':
    sys.exit(main())
