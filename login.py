"""Obtain a GotQuestions API JWT via the site's NextAuth credentials login.

The API is JWT-protected. The frontend uses NextAuth.js (providers: Google +
credentials). This scripts the *credentials* flow:

    1. GET  /api/auth/csrf                 → csrfToken (+ csrf cookie)
    2. POST /api/auth/callback/credentials → authenticates, sets session cookie
    3. GET  /api/auth/session              → the session, which should carry the
                                             backend JWT used as `Authorization: JWT …`

Set credentials in the environment (kept out of shell history):

    export GOTQUESTIONS_USER='you@example.com'   # email or username
    export GOTQUESTIONS_PASS='...'
    uv run login.py

On success it prints an `export GOTQUESTIONS_TOKEN=…` line for download.py.
If the session doesn't expose the token, it dumps the full session JSON so we
can see where the token lives (or fall back to copying it from DevTools).

NOTE: Google-only accounts can't use this — the credentials provider needs a
username/password set on the site. JWTs are short-lived; re-run when they expire.
"""

from __future__ import annotations

import json
import os
import sys

import niquests

BASE = "https://gotquestions.online"
# Keys to probe for the JWT inside the session JSON (top-level and under user).
TOKEN_KEYS = ("accessToken", "access", "jwt", "token", "apiToken", "access_token")


def find_token(obj):
    if isinstance(obj, dict):
        for k in TOKEN_KEYS:
            v = obj.get(k)
            if isinstance(v, str) and v.count(".") == 2:  # looks like a JWT
                return v
        for v in obj.values():
            t = find_token(v)
            if t:
                return t
    return None


def main() -> None:
    user = os.environ.get("GOTQUESTIONS_USER")
    pw = os.environ.get("GOTQUESTIONS_PASS")
    if not user or not pw:
        sys.exit("Set GOTQUESTIONS_USER and GOTQUESTIONS_PASS in the environment.")

    s = niquests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0"

    csrf = s.get(f"{BASE}/api/auth/csrf", timeout=30).json()["csrfToken"]

    # NextAuth credentials callback expects form-encoded fields. We send both
    # `username` and `email` (the provider reads whichever it defines) + password.
    s.post(
        f"{BASE}/api/auth/callback/credentials",
        data={
            "csrfToken": csrf,
            "callbackUrl": BASE,
            "json": "true",
            "username": user,
            "email": user,
            "password": pw,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
        allow_redirects=True,
    )

    session = s.get(f"{BASE}/api/auth/session", timeout=30).json()
    if not session:
        sys.exit(
            "Login failed: empty session. Check credentials, or the account may "
            "be Google-only (no username/password)."
        )

    token = find_token(session)
    if token:
        print("Authenticated. Use:\n")
        print(f"  export GOTQUESTIONS_TOKEN='{token}'\n")
    else:
        print(
            "Logged in, but no JWT found in the session payload. Full session "
            "below — look for the token field (or copy the Authorization header "
            "from a DevTools /api/pack request):\n",
            file=sys.stderr,
        )
        print(json.dumps(session, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
