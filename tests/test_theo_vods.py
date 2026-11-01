import contextlib
import datetime
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import theo_vods  # noqa: E402

INDEX = """# Theo - t3.gg VODS

> [🔴 Theo - t3.gg YouTube Channel](https://www.youtube.com/@t3dotgg)

- _2026-11-04_ [Newest (with parens) stream](https://www.youtube.com/watch?v=newnewnew11)
- _2026-10-25_ [I shipped a lot and learned even more :)](https://www.youtube.com/watch?v=nc442naX8vo)
- _2026-10-21_ [I'm getting impatient...](https://www.youtube.com/watch?v=v4OMMTRsD5g)
- _2025-11-10_ [Is Today Finally the Day???](https://www.youtube.com/live/hsQvfMRGDfc)
- _2025-06_25_ [Gemini CLI? Fun day](https://www.youtube.com/watch?v=iSvxxGhPZUg)
"""


class FakeYouTube:
    def __init__(self, playlists=None, items=None, unavailable=()):
        self.playlists = playlists or {}
        self.items = list(items or [])  # [(item_id, video_id)], top first
        self.unavailable = set(unavailable)
        self.created = []

    def find_playlist(self, title):
        return self.playlists.get(title)

    def create_playlist(self, title):
        self.created.append(title)
        return 'PLnew'

    def playlist_items(self, playlist_id):
        return {video: item for item, video in self.items}

    def add_to_top(self, playlist_id, video_id):
        if video_id in self.unavailable:
            raise theo_vods.ApiError(404, 'videoNotFound', 'Video not found.')
        self.items.insert(0, (f'item-{video_id}', video_id))

    def remove(self, item_id):
        self.items = [(item, video) for item, video in self.items if item != item_id]

    def videos(self):
        return [video for _, video in self.items]


class ParseIndexTest(unittest.TestCase):
    def test_parses_every_entry_format(self):
        streams = theo_vods.parse_index(INDEX)
        self.assertEqual([s['id'] for s in streams],
                         ['newnewnew11', 'nc442naX8vo', 'v4OMMTRsD5g', 'hsQvfMRGDfc', 'iSvxxGhPZUg'])
        self.assertEqual(streams[0]['title'], 'Newest (with parens) stream')
        self.assertEqual(streams[4]['date'], datetime.date(2025, 6, 25))


class SyncTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        patcher = mock.patch.object(theo_vods, 'STATE_PATH', Path(directory.name) / 'state.json')
        patcher.start()
        self.addCleanup(patcher.stop)
        self.all_streams = theo_vods.parse_index(INDEX)
        self.streams = self.all_streams[1:]  # Without the 2026-11-04 stream.

    def run_sync(self, youtube, today, streams=None):
        state = theo_vods.load_state()
        with contextlib.redirect_stdout(io.StringIO()):
            theo_vods.sync(youtube, streams or self.streams, state, today)
        return theo_vods.load_state()

    def test_first_run_starts_at_oct_25_and_creates_private_playlist(self):
        youtube = FakeYouTube()
        state = self.run_sync(youtube, datetime.date(2026, 11, 1))
        self.assertEqual(youtube.created, ['Theo streams'])
        self.assertEqual(state['playlist_id'], 'PLnew')
        self.assertEqual(youtube.videos(), ['nc442naX8vo'])

    def test_reuses_existing_playlist_and_puts_newest_first(self):
        youtube = FakeYouTube(playlists={'Theo streams': 'PLold'})
        state = self.run_sync(youtube, datetime.date(2026, 11, 5), self.all_streams)
        self.assertEqual(youtube.created, [])
        self.assertEqual(state['playlist_id'], 'PLold')
        self.assertEqual(youtube.videos(), ['newnewnew11', 'nc442naX8vo'])

    def test_does_not_re_add_a_video_you_removed(self):
        youtube = FakeYouTube()
        self.run_sync(youtube, datetime.date(2026, 11, 1))
        youtube.items.clear()
        self.run_sync(youtube, datetime.date(2026, 11, 2))
        self.assertEqual(youtube.videos(), [])

    def test_does_not_duplicate_a_video_already_in_the_playlist(self):
        youtube = FakeYouTube(playlists={'Theo streams': 'PLold'}, items=[('item-x', 'nc442naX8vo')])
        state = self.run_sync(youtube, datetime.date(2026, 11, 1))
        self.assertEqual(youtube.videos(), ['nc442naX8vo'])
        self.assertEqual(state['videos']['nc442naX8vo']['status'], 'added')

    def test_removes_30_days_after_stream_date(self):
        youtube = FakeYouTube()
        self.run_sync(youtube, datetime.date(2026, 11, 1))
        self.run_sync(youtube, datetime.date(2026, 11, 23))
        self.assertEqual(youtube.videos(), ['nc442naX8vo'])
        state = self.run_sync(youtube, datetime.date(2026, 11, 24))
        self.assertEqual(youtube.videos(), [])
        self.assertEqual(state['videos']['nc442naX8vo']['status'], 'removed')

    def test_unavailable_video_is_skipped_and_retried_later(self):
        youtube = FakeYouTube(unavailable={'nc442naX8vo'})
        state = self.run_sync(youtube, datetime.date(2026, 11, 1))
        self.assertNotIn('nc442naX8vo', state['videos'])
        youtube.unavailable.clear()
        self.run_sync(youtube, datetime.date(2026, 11, 2))
        self.assertEqual(youtube.videos(), ['nc442naX8vo'])

    def test_other_api_errors_stop_the_run_but_keep_progress(self):
        youtube = FakeYouTube()
        add = youtube.add_to_top

        def fail_on_newest(playlist_id, video_id):
            if video_id == 'newnewnew11':
                raise theo_vods.ApiError(403, 'quotaExceeded', 'Quota exceeded.')
            add(playlist_id, video_id)

        youtube.add_to_top = fail_on_newest
        with self.assertRaises(theo_vods.ApiError):
            self.run_sync(youtube, datetime.date(2026, 11, 5), self.all_streams)
        self.assertIn('nc442naX8vo', theo_vods.load_state()['videos'])


if __name__ == '__main__':
    unittest.main()
