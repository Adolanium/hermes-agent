"""Behind the sign-in gate, a Webapp login lasts only while the browser credential it is bound to does.

On the gateway's Webapp (``app.state.ui_surface == "webapp"``) with the sign-in gate engaged, every
successful cookie login (a password login or an OAuth callback) also sets the cookie
``hermes_webapp_signin_<gateway>``: the hex HMAC-SHA256 of ``"webapp-sign-in"`` keyed with the browser
session token the gateway serves (``web_server._SESSION_TOKEN``, kept in the gateway home by ``gateway.webapp_listener``). The gate treats
a cookie session without a matching value as signed out. Replacing that token (``hermes webapp
--sign-out``, or the CLI replacing the stored token while no gateway runs) therefore signs every browser
out, whichever provider it signed in with. ``<gateway>`` comes from a digest of the gateway's home
(:func:`cookie_gateway`), and the Webapp's listener names every sign-in cookie it sets that way, so two
gateways' Webapps on one hostname keep their own logins and leave the standalone dashboard's alone.

A request that passes records the generation of the credential it was checked against
(``hermes_cli.browser_credential``) on ``request.state.webapp_sign_in``; the socket tickets it mints
carry that generation, so the sockets they open are tracked (``web_session_sockets.track``) and close
at sign-out, and a ticket minted before a sign-out opens nothing after it. The standalone dashboard
never sets or checks the binding.

Such a login's cookies also hold the sign-in provider's access and refresh token. Presented on their own
(``Authorization: Bearer``, a socket's ``?token=``, ``/auth/native/refresh``) they would skip the
binding, and a list of tokens to refuse cannot catch them: a provider may accept many spellings of one
token (the bundled password provider decodes base64 leniently, so the quoted cookie value verifies too).
So on the gateway's Webapp behind the gate a provider token works on its own only when this listener
gave it to a native app's sign-in (RFC 8252: ``/auth/native/token``, then ``/auth/native/refresh``). The
listener keeps a digest of each such token until it expires, in ``RECORD_PATH`` under the gateway home
(``app.state.webapp_home``), so a restart that does not sign out still accepts them. A browser login's
tokens therefore work only as that login's cookies and end with it.

A native app's sign-in on the Webapp signs out with the browsers. A request whose token passes
:func:`token_works_alone` records the browser credential's generation as a login's does, so the
tickets it mints and the sockets it opens end at sign-out the same way. Sign-out first drops the record
(:func:`revoke`), then replaces the credential: a token checked before the drop was checked under the
credential being replaced, and one checked after it no longer works alone, in this process or after a
restart. Nothing is revoked at the provider (the bundled password provider cannot revoke its tokens);
sign-out ends them on this listener.

A sign-in the user finished before a sign-out ends with it, even when the app redeems its loopback code
afterwards. Before the code is minted, :func:`native_code_binding` reads the generation of the credential
in use and how many sign-outs have dropped the home's record; :func:`gave_native_app` records the pair
the code redeems only while both are unchanged. The credential alone is not enough: sign-out drops the
record before it replaces the credential, so a code redeemed between the two would pass that check and
its pair would be recorded after the drop. The count alone is not enough either: a code minted between
the two was minted under the old credential, as a login finished then is bound to it and ends. A sign-in
finished after the sign-out is a new one and works.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
import time
from pathlib import Path
from typing import Optional

from fastapi import Request
from fastapi.responses import Response

from hermes_cli import browser_credential

_MESSAGE = b"webapp-sign-in"
_log = logging.getLogger(__name__)

#: Where the gateway home keeps the digests of the provider tokens its listener gave native apps.
RECORD_PATH = Path("webapp") / "native-sign-in-tokens.json"
#: How long a refresh token stays recorded. Providers do not say when theirs expire; this is the longest
#: the bundled providers issue (the password provider's 30 days) and how long a browser keeps one.
REFRESH_TOKEN_LIFETIME = 30 * 24 * 60 * 60

_records_lock = threading.Lock()
#: Per gateway home: token digest -> expiry in Unix seconds. Read from the home's file once per
#: process; this process is its only writer.
_records: dict[Optional[Path], dict[str, int]] = {}
#: Per gateway home: how many sign-outs have dropped its record in this process (:func:`revoke`).
_sign_outs: dict[Optional[Path], int] = {}


def binding(token: str) -> str:
    """The ``hermes_webapp_signin`` value for browser session token *token*."""
    return hmac.new(token.encode(), _MESSAGE, hashlib.sha256).hexdigest()


def applies(request: Request) -> bool:
    """Whether *request* reaches the gateway's Webapp behind the sign-in gate."""
    state = request.app.state
    return getattr(state, "ui_surface", None) == "webapp" and bool(getattr(state, "auth_required", False))


def check(request: Request) -> bool:
    """Whether the cookie login on *request* is bound to the browser credential in use now. When it
    is, records that credential's generation on ``request.state.webapp_sign_in``."""
    from hermes_cli.dashboard_auth.cookies import read_webapp_signin_cookie

    token = browser_credential.current()
    presented = read_webapp_signin_cookie(request, _gateway(request)) or ""
    if not hmac.compare_digest(presented.encode(), binding(token).encode()):
        return False
    request.state.webapp_sign_in = browser_credential.generation_of(token)
    return True


def sign_in_of(request: Request) -> Optional[str]:
    """The browser credential generation *request*'s login, or the native app token it presented
    alone, was checked against; None off the Webapp's gate (the socket tickets it mints then carry no
    binding)."""
    return getattr(request.state, "webapp_sign_in", None)


def _set(response: Response, request: Request, token: str) -> None:
    from hermes_cli.dashboard_auth.cookies import detect_https, set_webapp_signin_cookie
    from hermes_cli.dashboard_auth.prefix import prefix_from_request

    set_webapp_signin_cookie(response, value=binding(token), use_https=detect_https(request),
                             prefix=prefix_from_request(request), gateway=_gateway(request))


def bind(response: Response, request: Request) -> None:
    """Bind the login *request* just completed to the browser credential in use now."""
    if applies(request):
        _set(response, request, browser_credential.current())


def renew(response: Response, request: Request) -> None:
    """Keep the binding as long-lived as the session cookies a refresh just rotated, unless the
    credential it was checked against was replaced while the request ran."""
    token = browser_credential.current_if(sign_in_of(request))
    if token is not None:
        _set(response, request, token)


def token_works_alone(request: Request, token: str) -> bool:
    """Whether provider token *token* may be used on its own (a bearer header, a socket's
    ``?token=``, the refresh route) on *request*'s listener: anywhere but the gateway's Webapp behind
    the gate, as on main; there, only when this listener gave it to a native app's sign-in and it has
    not expired. When it works there, records the generation of the browser credential in use on
    ``request.state.webapp_sign_in``, as :func:`check` does for a login, so the tickets the request
    mints and the socket it opens end at sign-out."""
    if not applies(request):
        return True
    # Read before the record: sign-out drops the record before it replaces the credential, so a token
    # still found there was found under the credential that sign-out replaces, and what it grants ends.
    generation = browser_credential.generation()
    with _records_lock:
        works = _recorded(_loaded(_home(request)), token, time.time())
    if works:
        request.state.webapp_sign_in = generation
    return works


def native_code_binding(request: Request) -> Optional[tuple[str, int]]:
    """What the loopback code a native app's sign-in on *request* is about to mint is bound to: the
    generation of the browser credential in use and how many sign-outs the home has had, read before
    the code exists; None off the Webapp's gate. :func:`gave_native_app` takes it back at redemption."""
    if not applies(request):
        return None
    with _records_lock:
        return browser_credential.generation(), _sign_outs.get(_home(request), 0)


def gave_native_app(request: Request, session, *, minted_under: Optional[tuple[str, int]] = None,
                    renewing: Optional[str] = None) -> bool:
    """Record that this listener just gave *session*'s tokens to a native app's sign-in, so they work
    on their own on the gateway's Webapp behind the gate (:func:`token_works_alone`).

    Nothing is recorded, and this returns False so the caller hands the pair out to no one, when a
    sign-out came first. For a loopback code, *minted_under* is its :func:`native_code_binding`: a
    sign-out since the code was minted refuses it, as it ends a login finished before it. For a
    renewal, *renewing* is the refresh token renewed: a sign-out that dropped it while the provider
    ran refuses it, as the gate renews a login's binding only while its credential is in use
    (:func:`renew`). Both are checked under the lock :func:`revoke` holds while it drops the record."""
    if not applies(request):
        return True
    now = int(time.time())
    given = ((session.access_token, int(session.expires_at or 0) or now + REFRESH_TOKEN_LIFETIME),
             (session.refresh_token, now + REFRESH_TOKEN_LIFETIME))
    home = _home(request)
    with _records_lock:
        records = _loaded(home)
        if not _no_sign_out_since(home, records, now, minted_under=minted_under, renewing=renewing):
            return False
        for token, expires in given:
            if token:
                records[_digest(token)] = expires
        for key in [key for key, expires in records.items() if expires <= now]:
            del records[key]
        if home is not None:
            _write(home / RECORD_PATH, records)
    return True


def revoke(home: Path) -> bool:
    """Drop the native sign-ins recorded for gateway home *home*: the tokens this listener gave native
    apps no longer work on their own, in this process or after a restart, and no loopback code minted
    before now redeems anything. Sign-out runs it before it replaces the browser credential (module
    docstring). Returns whether there was a record to drop. Raises OSError, having dropped nothing,
    when the record is there but cannot be removed: a sign-out that leaves it would be undone by a
    restart."""
    home = Path(home)
    path = home / RECORD_PATH
    with _records_lock:
        try:
            path.unlink()
        except (FileNotFoundError, NotADirectoryError):  # no file; this process may still hold some
            dropped = bool(_records.get(home))
        except OSError as exc:
            raise OSError(f"could not remove {path}, the Webapp's record of native sign-ins "
                          f"({exc.strerror or exc})") from exc
        else:
            dropped = True
        _records[home] = {}
        _sign_outs[home] = _sign_outs.get(home, 0) + 1
    return dropped


def _no_sign_out_since(home: Optional[Path], records: dict[str, int], now: float, *,
                       minted_under: Optional[tuple[str, int]], renewing: Optional[str]) -> bool:
    """Whether no sign-out came before the pair :func:`gave_native_app` is about to record (call with
    ``_records_lock`` held). A code minted off the Webapp's gate carries no binding and redeems nothing
    on it."""
    if renewing is not None:
        return _recorded(records, renewing, now)
    if minted_under is None:
        return False
    generation, sign_outs = minted_under
    return browser_credential.is_current(generation) and sign_outs == _sign_outs.get(home, 0)


def _recorded(records: dict[str, int], token: str, now: float) -> bool:
    expires = records.get(_digest(token))
    return expires is not None and expires > now


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _home(request: Request) -> Optional[Path]:
    home = getattr(request.app.state, "webapp_home", None)
    return Path(home) if home is not None else None


def cookie_gateway(request: Request) -> str:
    """The suffix the gateway's Webapp gives every sign-in cookie it sets (``hermes_session_at_<it>``
    and the rest, ``hermes_cli.dashboard_auth.cookies``): cookies are not scoped to a port. ``""`` off
    the Webapp, where the standalone dashboard keeps main's names."""
    return _gateway(request) if getattr(request.app.state, "ui_surface", None) == "webapp" else ""


def _gateway(request: Request) -> str:
    """This gateway's name in its sign-in cookie: a digest of its home, the same across restarts and
    different for every gateway on one machine (each home has its own); ``""`` without a home."""
    home = _home(request)
    return "" if home is None else hashlib.sha256(str(home.absolute()).encode()).hexdigest()[:16]


def _loaded(home: Optional[Path]) -> dict[str, int]:
    """*home*'s record, read from its file on first use (call with ``_records_lock`` held). Without a
    home it lives in memory only."""
    if home in _records:
        return _records[home]
    stored: object = {}
    if home is not None:
        try:
            stored = json.loads((home / RECORD_PATH).read_text(encoding="utf-8-sig"))
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as exc:  # native apps sign in again
            _log.warning("Could not read the Webapp's record of native sign-ins: %s", exc)
    records = ({key: value for key, value in stored.items() if isinstance(value, int)}
               if isinstance(stored, dict) else {})
    _records[home] = records
    return records


def _write(path: Path, records: dict[str, int]) -> None:
    from utils import atomic_write_text

    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        atomic_write_text(path, json.dumps(records, separators=(",", ":")) + "\n", mode=0o600)
    except OSError as exc:  # this process still accepts them; after a restart native apps sign in again
        _log.warning("Could not save the Webapp's record of native sign-ins: %s", exc)


def _reset_for_tests() -> None:
    """Forget every loaded record, as a new process starts with only the files."""
    with _records_lock:
        _records.clear()
        _sign_outs.clear()
