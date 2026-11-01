# Theo streams playlist

Theo (t3dotgg) now posts his stream VODs as **unlisted**, so they don't show up on his channel, in
subscriptions or in search, and SmartTube can't find them. This repo keeps a **private YouTube
playlist called "Theo streams"** on your account up to date, so the VODs show up in SmartTube under
your playlists.

Once a day, around midnight Central, a GitHub Action:

1. Reads the fan-maintained VOD index:
   [NikolaM-Dev/theo-t3dotgg-vods__md](https://github.com/NikolaM-Dev/theo-t3dotgg-vods__md).
2. Adds any stream from **Oct 25, 2026 onward** that isn't in the playlist yet, putting it at the
   **top** so the newest stream is listed first.
3. Removes each stream **30 days after its stream date**.

The script only removes videos it added itself. It never re-adds a video you deleted from the
playlist, and it leaves alone anything you add to the playlist by hand. What it has done is recorded
in `state.json`, which the Action commits back to this repo.

**Costs:** none. Public repos get free Actions minutes, and the job saves no files, so it doesn't use
your 0.5 GB of Actions storage. It uses under 100 of the free 10,000 YouTube API units a day.

---

## One-time setup (about 15 minutes)

You need the Google account that SmartTube is signed in to. You'll do this on the Linux PC.

### 1. Create the Google Cloud project and turn on the YouTube API

1. Go to <https://console.cloud.google.com/projectcreate>. Name it `Theo streams` and click
   **Create**. Make sure the project picker at the top of the page shows **Theo streams** for the
   rest of these steps. No billing account is needed.
2. Go to <https://console.cloud.google.com/apis/library/youtube.googleapis.com> and click **Enable**.

### 2. Set up sign-in for the project

1. Go to <https://console.cloud.google.com/auth/overview> and click **Get started**.
   - App name: `Theo streams`. User support email: your email. Click **Next**.
   - Audience: **External**. Click **Next**.
   - Contact email: your email. Click **Next**, tick the agreement, and click **Create**.
2. Go to **Audience** (<https://console.cloud.google.com/auth/audience>). Under *Publishing status*,
   click **Publish app**, then **Confirm**. It should now say **In production**.
   > ⚠️ Don't skip this. If it stays on *Testing*, Google cancels the sign-in after 7 days and the
   > playlist stops updating. You don't need to submit the app for verification.
3. Go to **Clients** (<https://console.cloud.google.com/auth/clients>) and click **Create client**.
   - Application type: **Desktop app**. Name: `Theo streams`. Click **Create**.
   - Click **Download JSON**. It saves a file named like `client_secret_….json` to `~/Downloads`.

### 3. Sign in once and save the keys to GitHub

In a terminal on the PC (the GitHub CLI `gh` is already signed in there as `ussblade`):

```bash
git clone https://github.com/ussblade/theo-streams-playlist.git ~/theo-streams-playlist
cd ~/theo-streams-playlist
python3 get_refresh_token.py ~/Downloads/client_secret_*.json ussblade/theo-streams-playlist
```

A browser opens:

1. Pick the Google account SmartTube uses. If it asks you to choose a channel, pick the one
   SmartTube uses.
2. On **"Google hasn't verified this app"**, click **Advanced**, then **Go to Theo streams (unsafe)**.
   You're seeing this because it's your own app, not a published one.
3. Allow **Manage your YouTube account** (needed to edit your playlist) and click **Continue**.

The terminal should then say
`Saved YT_CLIENT_ID, YT_CLIENT_SECRET and YT_REFRESH_TOKEN as secrets on ussblade/theo-streams-playlist.`
GitHub stores these encrypted. They aren't visible in the public repo. You can now delete the
downloaded `client_secret_….json`.

### 4. Run it once now

1. Open <https://github.com/ussblade/theo-streams-playlist/actions/workflows/sync.yml>.
2. Click **Run workflow** → **Run workflow**. After about 30 seconds, the run should show a green
   check, and its log should say `Added: 2026-10-25 I shipped a lot and learned even more :)`.
3. Check <https://www.youtube.com/feed/playlists>. You should see a private playlist named
   **Theo streams**.

### 5. Watch in SmartTube

1. On the Fire TV, open SmartTube. Under **Settings → Accounts**, make sure you're signed in to the
   same Google account. If not, add it there; SmartTube shows a code to enter on your phone.
2. Open the **Playlists** section in the left menu, then **Theo streams**.

From then on, new streams appear at the top within about a day of airing.

---

## Good to know

- **If something goes wrong,** GitHub emails you when a run fails, and the run's log on the Actions
  page says why. The most likely cause is the sign-in being cancelled (for example, the app was left
  on *Testing*, or you removed its access in your Google account settings). To fix it, run step 3
  again.
- **If no new streams are being added,** it may be because the fan index has stopped updating. This
  setup depends on it. Each run's log shows the newest date in the index.
- **GitHub turns off scheduled jobs in public repos after 60 days without commits.** Each new stream
  creates a commit, so this only happens if nothing has been added or removed for 60 days. GitHub
  emails you first, and you can turn the job back on from the Actions page with one click.
- **To change the settings,** edit the values at the top of `theo_vods.py`: `PLAYLIST_TITLE`,
  `START_DATE`, `KEEP_DAYS`. If you rename the playlist on YouTube, the script keeps using it.
  Deleting the playlist on YouTube stops the job with an error. To make a fresh playlist, delete the
  `playlist_id` line from `state.json`.
- **To preview without signing in:** `python3 theo_vods.py --dry-run` lists what would be added or
  removed.
- **To run the tests:** `python3 -m unittest discover -s tests -v`.
