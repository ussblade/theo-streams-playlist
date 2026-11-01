#!/usr/bin/env python3
"""One-time Google sign-in that saves the YouTube keys as GitHub secrets.

Usage: python3 get_refresh_token.py CLIENT_SECRET.json OWNER/REPO

CLIENT_SECRET.json is the Desktop app client downloaded from Google Cloud.
Needs the GitHub CLI (gh), signed in. Nothing secret is printed.
"""

import base64
import hashlib
import http.server
import json
import secrets
import subprocess
import sys
import urllib.parse
import urllib.request
import webbrowser

SCOPE = 'https://www.googleapis.com/auth/youtube'


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    client = json.load(open(sys.argv[1]))['installed']
    repo = sys.argv[2]

    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    state = secrets.token_urlsafe(16)
    result = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if query.get('state') == [state]:
                result.update({key: values[0] for key, values in query.items()})
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write('Done. You can close this tab and go back to the terminal.'.encode())

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(('127.0.0.1', 0), Handler)
    redirect_uri = f'http://127.0.0.1:{server.server_port}'
    url = client['auth_uri'] + '?' + urllib.parse.urlencode({
        'client_id': client['client_id'],
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': SCOPE,
        'access_type': 'offline',
        'prompt': 'consent',
        'state': state,
        'code_challenge': challenge,
        'code_challenge_method': 'S256',
    })
    print('Sign in with the Google account SmartTube uses. If the browser does not open, visit:\n')
    print(url + '\n')
    webbrowser.open(url)
    while 'code' not in result and 'error' not in result:
        server.handle_request()
    if 'error' in result:
        raise SystemExit(f'Google sign-in was not completed: {result["error"]}')

    body = urllib.parse.urlencode({
        'code': result['code'],
        'client_id': client['client_id'],
        'client_secret': client['client_secret'],
        'redirect_uri': redirect_uri,
        'grant_type': 'authorization_code',
        'code_verifier': verifier,
    }).encode()
    with urllib.request.urlopen(client['token_uri'], body, timeout=30) as response:
        tokens = json.load(response)
    if 'refresh_token' not in tokens:
        raise SystemExit('Google did not return a refresh token. Run this again.')

    for name, value in (('YT_CLIENT_ID', client['client_id']),
                        ('YT_CLIENT_SECRET', client['client_secret']),
                        ('YT_REFRESH_TOKEN', tokens['refresh_token'])):
        subprocess.run(['gh', 'secret', 'set', name, '--repo', repo], input=value.encode(), check=True)
    print(f'Saved YT_CLIENT_ID, YT_CLIENT_SECRET and YT_REFRESH_TOKEN as secrets on {repo}.')


if __name__ == '__main__':
    main()
