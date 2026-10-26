"""Behind the sign-in gate, signing the Webapp out signs every browser out.

On a LAN or own-URL Webapp a browser signs in with the dashboard's sign-in (a password, or an OAuth
provider) and keeps that login in cookies. Each login on the Webapp is bound to the gateway's browser
credential, so ``hermes webapp --sign-out``, which replaces that credential, ends every one of them:
the login's requests get 401 and the sign-in view, the sockets and host terminals it opened close with
4401, tickets it minted open nothing, and its cookies replayed from anywhere get nothing. The provider
tokens those cookies hold work only as those cookies: the Webapp's listener refuses them as a bearer
token, on the refresh route and as a socket's ``?token=``, before and after sign-out and across a
restart. Signing in again works. A native app's own sign-in on the same listener (RFC 8252) works on
its own and survives a restart that does not sign out; sign-out ends it as it ends a login: its tokens
stop working on their own, after a restart too, a renewal sign-out overtakes hands out nothing, a
loopback code minted before sign-out redeems nothing after it, and the sockets it opened close. A
sign-out that cannot replace the credential says that it signed out native apps only. The standalone
dashboard has no browser credential and keeps its logins as on main.
"""
import json
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tests.hermes_cli.test_web_host_terminal_persistence import metadata
from tests.hermes_cli.test_webapp_sign_out_sockets import _close_code
from tests.hermes_cli.test_webapp_socket_tickets import _TOKEN, serve_webapp

WEBAPP = "http://hermes.lan:9120"
USER, PASSWORD = "owner", "throwaway-test-password"


@pytest.fixture
def gated(tmp_path, monkeypatch):
    """The Webapp behind the sign-in gate with a password and an OAuth provider registered."""
    from hermes_cli import webapp_sign_in
    from hermes_cli.dashboard_auth import clear_providers, register_provider
    from hermes_cli.dashboard_auth.routes import _reset_password_rate_limit
    from hermes_cli.dashboard_auth.ws_tickets import _reset_for_tests
    from plugins.dashboard_auth.basic import BasicAuthProvider, hash_password
    from tests.hermes_cli.conftest_dashboard_auth import StubAuthProvider

    webapp = serve_webapp(tmp_path, monkeypatch)
    state = webapp.server.app.state
    monkeypatch.setattr(state, "bound_host", "hermes.lan")
    monkeypatch.setattr(state, "bound_port", 9120, raising=False)
    monkeypatch.setattr(state, "auth_required", True)
    monkeypatch.setattr(state, "webapp_home", tmp_path / ".hermes", raising=False)
    _reset_for_tests()
    webapp_sign_in._reset_for_tests()
    _reset_password_rate_limit()
    clear_providers()
    register_provider(BasicAuthProvider(username=USER, password_hash=hash_password(PASSWORD), secret=b"k" * 32))
    register_provider(StubAuthProvider())
    webapp.browser = lambda: TestClient(webapp.server.app, base_url=WEBAPP)
    try:
        yield webapp
    finally:
        clear_providers()
        _reset_for_tests()
        webapp_sign_in._reset_for_tests()
        _reset_password_rate_limit()


def _sign_in_with_password(client):
    signed_in = client.post("/auth/password-login", json={"provider": "basic", "username": USER, "password": PASSWORD})
    assert signed_in.status_code == 200, signed_in.text


def _sign_in_with_oauth(client):
    started = client.get("/auth/login?provider=stub", follow_redirects=False)
    state = started.headers["location"].split("state=")[1]
    assert client.get(f"/auth/callback?code=stub_code&state={state}", follow_redirects=False).status_code == 302


SIGN_INS = {"password": _sign_in_with_password, "oauth": _sign_in_with_oauth}


@pytest.fixture
def control(gated, tmp_path):
    """The control socket of the gateway serving *gated*: asks it for a verb, returns its answer."""
    from gateway.control_socket import GatewayControlServer
    from gateway.webapp_listener import register_control_verbs

    home = tmp_path / ".hermes"
    runner = SimpleNamespace(
        session_control_server=GatewayControlServer(home),
        webapp_status={"state": "serving", "url": WEBAPP, "reason": None},
        session_api=SimpleNamespace(app=SimpleNamespace(web=gated.server)))
    register_control_verbs(runner, home)

    def ask(verb):
        raw = json.dumps({"protocol": 1, "verb": verb, "id": 1, "params": {}}).encode()
        return json.loads(runner.session_control_server.handle_request_line(raw, "same-user"))
    return ask


@pytest.fixture
def sign_out(gated, control):
    """Ask the gateway serving *gated* for ``webapp-sign-out`` over its control socket."""
    def ask():
        answer = control("webapp-sign-out")
        assert answer["ok"], answer
        assert gated.server._SESSION_TOKEN != _TOKEN
        return answer["result"]
    return ask


def _signed_out(response):
    assert response.status_code == 401, response.text
    body = response.json()
    assert body["error"] in {"unauthenticated", "session_expired"} and body["login_url"].startswith("/login")


@pytest.mark.parametrize("sign_in", SIGN_INS)
def test_signing_out_ends_every_login_behind_the_gate(gated, sign_out, sign_in):
    browser = gated.browser()
    SIGN_INS[sign_in](browser)
    assert browser.get("/api/auth/me").status_code == 200
    sign_out()
    _signed_out(browser.get("/api/auth/me"))
    _signed_out(browser.post("/api/webapp/socket-ticket?socket=host-terminal"))
    _signed_out(browser.post("/api/auth/ws-ticket"))
    page = browser.get("/", follow_redirects=False)
    assert page.status_code == 302 and page.headers["location"].startswith("/login")


def test_old_login_cookies_replayed_after_sign_out_get_nothing(gated, sign_out):
    browser = gated.browser()
    _sign_in_with_password(browser)
    stolen = dict(browser.cookies.items())
    sign_out()
    replay = gated.browser()
    replay.cookies.update(stolen)
    _signed_out(replay.get("/api/auth/me"))


def test_signing_in_again_after_sign_out_works(gated, sign_out):
    browser = gated.browser()
    _sign_in_with_password(browser)
    sign_out()
    _signed_out(browser.get("/api/auth/me"))
    _sign_in_with_password(browser)
    assert browser.get("/api/auth/me").status_code == 200
    assert browser.post("/api/webapp/socket-ticket?socket=host-terminal").status_code == 200


def test_a_credential_replaced_while_the_gateway_was_down_signs_logins_out(gated, monkeypatch):
    """The CLI replaces the stored credential when no gateway is running; the next gateway serves
    the new one, and logins bound to the old one are signed out."""
    browser = gated.browser()
    _sign_in_with_password(browser)
    monkeypatch.setattr(gated.server, "_SESSION_TOKEN", "n" * 43)
    _signed_out(browser.get("/api/auth/me"))


def test_signing_out_closes_the_sockets_and_host_terminal_a_login_opened(gated, sign_out):
    from hermes_cli.dashboard_auth.ws_tickets import mint_ticket

    browser = gated.browser()
    _sign_in_with_password(browser)
    terminal = browser.post("/api/webapp/socket-ticket?socket=host-terminal").json()["ticket"]
    events = browser.post("/api/auth/ws-ticket").json()["ticket"]
    other = mint_ticket(user_id="someone-else", provider="stub")
    with TestClient(gated.host, base_url=WEBAPP) as shells, \
            shells.websocket_connect(f"ws://hermes.lan:9120/api/host-terminal?ticket={terminal}") as shell, \
            browser.websocket_connect(f"ws://hermes.lan:9120/api/events?channel=tab-1&ticket={events}") as stream, \
            browser.websocket_connect(f"ws://hermes.lan:9120/api/events?channel=kept&ticket={other}") as kept:
        metadata(shell)
        assert _close_code(shell, 0.2) is None and _close_code(stream, 0.2) is None
        result = sign_out()
        assert _close_code(shell) == 4401
        assert _close_code(stream) == 4401
        assert _close_code(kept, 0.5) is None
    assert result["connections_closed"] == 2
    assert result["sign_in_gate"] is True


def test_tickets_a_login_minted_before_sign_out_open_nothing_after(gated, sign_out):
    browser = gated.browser()
    _sign_in_with_password(browser)
    terminal = browser.post("/api/webapp/socket-ticket?socket=host-terminal").json()["ticket"]
    events = browser.post("/api/auth/ws-ticket").json()["ticket"]
    sign_out()
    with TestClient(gated.host, base_url=WEBAPP) as shells:
        for client, url in ((shells, f"ws://hermes.lan:9120/api/host-terminal?ticket={terminal}"),
                            (browser, f"ws://hermes.lan:9120/api/events?channel=tab-1&ticket={events}")):
            with pytest.raises(WebSocketDisconnect) as closed:
                with client.websocket_connect(url) as ws:
                    ws.receive_text()
            assert closed.value.code == 4401
    assert gated.shells == []


def test_the_standalone_dashboard_keeps_its_logins_as_on_main(gated, monkeypatch):
    monkeypatch.setattr(gated.server.app.state, "ui_surface", "dashboard")
    browser = gated.browser()
    _sign_in_with_password(browser)
    assert not any("hermes_webapp_signin" in name for name in browser.cookies.keys())
    monkeypatch.setattr(gated.server, "_SESSION_TOKEN", "n" * 43)
    assert browser.get("/api/auth/me").status_code == 200


def test_two_gateways_on_one_hostname_keep_their_own_sign_ins(gated, monkeypatch, tmp_path):
    """Cookies are not scoped to a port, so one browser sends the Webapps of two gateways on one host
    the same cookies. Signing in to one leaves the other signed in (here both accept the same account
    tokens, as two gateways sharing a sign-in provider do), and signing one out leaves the other."""
    state = gated.server.app.state
    gateways = {9120: (tmp_path / ".hermes", _TOKEN), 9121: (tmp_path / "other-home", "o" * 43)}
    browser = gated.browser()  # one cookie jar for both

    def at(port, path):
        home, token = gateways[port]
        monkeypatch.setattr(state, "webapp_home", home)
        monkeypatch.setattr(state, "bound_port", port)
        monkeypatch.setattr(gated.server, "_SESSION_TOKEN", token)
        return f"http://hermes.lan:{port}{path}"

    for port in (9120, 9121):
        signed_in = browser.post(at(port, "/auth/password-login"),
                                 json={"provider": "basic", "username": USER, "password": PASSWORD})
        assert signed_in.status_code == 200
    assert browser.get(at(9121, "/api/auth/me")).status_code == 200
    assert browser.get(at(9120, "/api/auth/me")).status_code == 200
    gateways[9121] = (gateways[9121][0], "r" * 43)  # the second gateway signs its browsers out
    _signed_out(browser.get(at(9121, "/api/auth/me")))
    assert browser.get(at(9120, "/api/auth/me")).status_code == 200


def test_two_gateways_with_their_own_sign_in_on_one_hostname_keep_their_logins_apart(gated, monkeypatch, tmp_path):
    """The Webapp's listener names every sign-in cookie it sets for its gateway (the login's access and
    refresh token, its provider hint and binding, the OAuth state and the auto sign-in marker), so two
    gateways on one hostname whose sign-in providers differ (two users' or two profiles' gateways, each
    with its own provider secret) keep their own logins in one browser: signing in to one leaves the
    other signed in, and signing out of one in the browser leaves the other."""
    from hermes_cli.dashboard_auth import clear_providers, register_provider
    from plugins.dashboard_auth.basic import BasicAuthProvider, hash_password

    state = gated.server.app.state
    providers = {port: BasicAuthProvider(username=USER, password_hash=hash_password(PASSWORD), secret=secret * 32)
                 for port, secret in ((9120, b"1"), (9121, b"2"))}
    gateways = {9120: (tmp_path / ".hermes", _TOKEN), 9121: (tmp_path / "other-home", "o" * 43)}
    browser = gated.browser()  # one cookie jar for both

    def at(port, path):
        home, token = gateways[port]
        monkeypatch.setattr(state, "webapp_home", home)
        monkeypatch.setattr(state, "bound_port", port)
        monkeypatch.setattr(gated.server, "_SESSION_TOKEN", token)
        clear_providers()
        register_provider(providers[port])
        return f"http://hermes.lan:{port}{path}"

    for port in (9120, 9121):
        signed_in = browser.post(at(port, "/auth/password-login"),
                                 json={"provider": "basic", "username": USER, "password": PASSWORD})
        assert signed_in.status_code == 200
    assert browser.get(at(9121, "/api/auth/me")).status_code == 200
    first = browser.get(at(9120, "/api/auth/me"))
    assert first.status_code == 200, f"signing in to the second gateway signed the first out: {first.text}"
    assert browser.post(at(9121, "/auth/logout"), headers={"Origin": "http://hermes.lan:9121"},
                        follow_redirects=False).status_code == 302
    _signed_out(browser.get(at(9121, "/api/auth/me")))
    assert browser.get(at(9120, "/api/auth/me")).status_code == 200


def test_the_webapp_leaves_cookies_named_for_no_gateway_to_the_dashboard(gated, monkeypatch):
    """The standalone dashboard on the same hostname keeps main's cookie names, as did earlier builds
    of the Webapp. The Webapp's listener neither reads nor clears them: a browser holding only such a
    login gets the sign-in view there, and the dashboard keeps it."""
    monkeypatch.setattr(gated.server.app.state, "ui_surface", "dashboard")
    browser = gated.browser()
    _sign_in_with_password(browser)
    names = set(browser.cookies.keys())
    assert {"hermes_session_at", "hermes_session_rt", "hermes_session_provider"} <= names
    monkeypatch.setattr(gated.server.app.state, "ui_surface", "webapp")
    on_webapp = browser.get("/api/auth/me")
    _signed_out(on_webapp)
    assert "hermes_session_at=" not in on_webapp.headers.get("set-cookie", "")
    signed_out = browser.post("/auth/logout", headers={"Origin": WEBAPP}, follow_redirects=False)
    assert signed_out.status_code == 302
    assert "hermes_session_at=" not in signed_out.headers.get("set-cookie", "")
    monkeypatch.setattr(gated.server.app.state, "ui_surface", "dashboard")
    assert browser.get("/api/auth/me").status_code == 200


# A browser's login keeps the sign-in provider's access and refresh token in its cookies. Copied out of
# them they are the kind of token a native app presents as ``Authorization: Bearer`` and renews on
# ``/auth/native/refresh``. On the Webapp's listener they work only as that login's cookies, so signing
# out ends them everywhere there. A native app's own sign-in works on its own until sign-out ends it.

@pytest.fixture
def clock(monkeypatch):
    """Moves the password provider's clock forward. It signs each token's expiry in whole seconds, so
    without this a renewal or a second login in the same second gets byte-identical tokens."""
    import time

    from plugins.dashboard_auth import basic

    offset = [0]
    monkeypatch.setattr(basic, "time", SimpleNamespace(time=lambda: time.time() + offset[0]))

    def advance(seconds=5):
        offset[0] += seconds
    return advance


def _cookie(client, bare):
    """The name of *client*'s cookie *bare*: on the Webapp's listener followed by its gateway, elsewhere
    as on main."""
    return next(name for name in client.cookies.keys() if name == bare or name.startswith(f"{bare}_"))


def _tokens(client):
    """The access and refresh token the cookie login on *client* holds, as a copy taken out of the
    browser would present them (the cookie keeps them in quotes)."""
    return tuple(client.cookies.get(_cookie(client, name)).strip('"')
                 for name in ("hermes_session_at", "hermes_session_rt"))


def _bearer(token):
    return {"Authorization": "Bearer " + token}


def _renew(gated, refresh_token):
    """``/auth/native/refresh`` from a client holding nothing but *refresh_token*."""
    return gated.browser().post("/auth/native/refresh", json={"refresh_token": refresh_token})


def _refused(response):
    assert (response.status_code, response.json().get("error")) == (401, "session_expired")


def _refused_alone(gated, access, refresh):
    """Neither token works on its own: the access token as a bearer, the refresh token on the
    refresh route."""
    stolen = gated.browser()
    _refused(stolen.get("/api/auth/me", headers=_bearer(access)))
    _refused(stolen.post("/api/webapp/socket-ticket?socket=host-terminal", headers=_bearer(access)))
    _refused(stolen.post("/api/auth/ws-ticket", headers=_bearer(access)))
    _refused(_renew(gated, refresh))


def _restart(gated, monkeypatch, *, token=None):
    """What a new gateway process starts from: nothing in memory but the files in its home, and the
    browser credential stored there (*token* when the CLI replaced it while no gateway ran)."""
    from hermes_cli import webapp_sign_in

    webapp_sign_in._reset_for_tests()
    if token is not None:
        monkeypatch.setattr(gated.server, "_SESSION_TOKEN", token)


@pytest.mark.parametrize("sign_in", SIGN_INS)
def test_after_sign_out_a_logins_tokens_work_nowhere_on_the_webapp(gated, sign_out, sign_in):
    browser = gated.browser()
    SIGN_INS[sign_in](browser)
    access, refresh = _tokens(browser)
    sign_out()
    _refused_alone(gated, access, refresh)


@pytest.mark.parametrize("sign_in", SIGN_INS)
def test_a_logins_tokens_work_only_as_its_cookies(gated, sign_in):
    """Before any sign-out too: the tokens a browser login holds open nothing without its cookies, in
    the spelling a copy would take from the browser or from the cookie as stored."""
    browser = gated.browser()
    SIGN_INS[sign_in](browser)
    assert browser.get("/api/auth/me").status_code == 200
    access, refresh = _tokens(browser)
    _refused_alone(gated, access, refresh)
    stored = (browser.cookies.get(_cookie(browser, "hermes_session_at")),
              browser.cookies.get(_cookie(browser, "hermes_session_rt")))
    _refused_alone(gated, *stored)


def test_a_pair_renewed_before_sign_out_is_refused_after_it(gated, sign_out, clock):
    browser = gated.browser()
    _sign_in_with_password(browser)
    first = _tokens(browser)
    # The gate renews the browser's pair once its access token lapses.
    clock()
    browser.cookies.delete(_cookie(browser, "hermes_session_at"))
    assert browser.get("/api/auth/me").status_code == 200
    renewed = _tokens(browser)
    assert renewed[0] != first[0]
    # The refresh route renews nothing from a browser login, before sign-out either.
    _refused(_renew(gated, first[1]))
    sign_out()
    _refused_alone(gated, *renewed)


def test_the_refusal_survives_a_gateway_restart(gated, sign_out, monkeypatch):
    browser = gated.browser()
    _sign_in_with_password(browser)
    access, refresh = _tokens(browser)
    sign_out()
    _restart(gated, monkeypatch)
    _refused_alone(gated, access, refresh)


def test_a_credential_replaced_while_the_gateway_was_down_ends_its_logins_tokens(gated, monkeypatch, tmp_path):
    from gateway.webapp_listener import browser_session_token

    browser = gated.browser()
    _sign_in_with_password(browser)
    access, refresh = _tokens(browser)
    # The gateway stops, hermes webapp --sign-out replaces the stored credential, a gateway starts.
    _restart(gated, monkeypatch, token=browser_session_token(tmp_path / ".hermes", rotate=True))
    _signed_out(browser.get("/api/auth/me"))
    _refused_alone(gated, access, refresh)


def test_a_login_after_sign_out_works(gated, sign_out, clock):
    browser = gated.browser()
    _sign_in_with_password(browser)
    sign_out()
    clock()
    _sign_in_with_password(browser)
    assert browser.get("/api/auth/me").status_code == 200
    assert browser.post("/api/webapp/socket-ticket?socket=host-terminal").status_code == 200


NATIVE_VERIFIER = "native-app-verifier-" + "v" * 40


def _start_native_sign_in(gated):
    """The start of an RFC 8252 sign-in (the native Desktop's) on the Webapp's listener: the system
    browser opens ``/auth/native/authorize``. Returns the step that finishes it, where the user signs in
    and the browser lands on the app's loopback redirect; that step returns the one-use code."""
    import base64
    import hashlib
    from urllib.parse import parse_qs, urlsplit

    challenge = base64.urlsafe_b64encode(hashlib.sha256(NATIVE_VERIFIER.encode()).digest()).rstrip(b"=").decode()
    system_browser = gated.browser()
    started = system_browser.get("/auth/native/authorize", follow_redirects=False, params={
        "provider": "stub", "code_challenge": challenge, "code_challenge_method": "S256",
        "redirect_uri": "http://127.0.0.1:53999/cb", "state": "desk"})
    callback = parse_qs(urlsplit(started.headers["location"]).query)

    def finish():
        landed = system_browser.get("/auth/callback", follow_redirects=False,
                                    params={"code": callback["code"][0], "state": callback["state"][0]})
        return parse_qs(urlsplit(landed.headers["location"]).query)["code"][0]
    return finish


def _redeem(gated, code):
    """The app redeems its loopback *code* for bearer tokens. No cookie login takes part."""
    return gated.browser().post("/auth/native/token", json={"code": code, "code_verifier": NATIVE_VERIFIER})


def _native_app_sign_in(gated):
    """A whole RFC 8252 sign-in on the Webapp's listener; returns the app's access and refresh token."""
    tokens = _redeem(gated, _start_native_sign_in(gated)())
    assert tokens.status_code == 200
    return tokens.json()["access_token"], tokens.json()["refresh_token"]


def test_sign_out_stops_a_native_apps_tokens_working_alone(gated, sign_out, monkeypatch):
    """``hermes webapp --sign-out`` drops the listener's record of the tokens it gave a native app.
    Those tokens then work nowhere on their own, including after a restart. A browser login's tokens
    stay refused on their own, a bearer never given to a native app still does not work alone, and a
    native app can sign in again."""
    import time

    import tests.hermes_cli.conftest_dashboard_auth as stub_auth

    access, refresh = _native_app_sign_in(gated)
    browser = gated.browser()
    _sign_in_with_password(browser)
    stolen = _tokens(browser)
    sign_out()
    _refused_alone(gated, access, refresh)
    _refused_alone(gated, *stolen)
    _restart(gated, monkeypatch)
    _refused_alone(gated, access, refresh)
    _refused_alone(gated, "never-issued-access", "never-issued-refresh")
    issued_at = time.time()
    monkeypatch.setattr(stub_auth.time, "time", lambda: issued_at + 5)
    fresh_access, fresh_refresh = _native_app_sign_in(gated)
    assert (fresh_access, fresh_refresh) != (access, refresh)
    assert gated.browser().get("/api/auth/me", headers=_bearer(fresh_access)).status_code == 200
    renewed = _renew(gated, fresh_refresh)
    assert renewed.status_code == 200
    _refused_alone(gated, access, refresh)


def test_a_restart_without_sign_out_keeps_a_native_apps_tokens(gated, monkeypatch):
    """The record lives in the gateway home, so a new process that does not sign out still accepts
    the tokens this listener gave a native app, and the pair it renews keeps working."""
    access, refresh = _native_app_sign_in(gated)
    _restart(gated, monkeypatch)
    assert gated.browser().get("/api/auth/me", headers=_bearer(access)).status_code == 200
    renewed = _renew(gated, refresh)
    assert renewed.status_code == 200
    assert gated.browser().get("/api/auth/me", headers=_bearer(renewed.json()["access_token"])).status_code == 200
    assert _renew(gated, renewed.json()["refresh_token"]).status_code == 200


def test_a_renewal_that_sign_out_overtakes_hands_out_nothing(gated, sign_out, monkeypatch):
    """Sign-out lands while the provider renews a native app's refresh token: the route answers
    ``session_expired`` and the pair the provider renewed works nowhere on its own, as the gate keeps
    no binding for a login whose credential was replaced while its refresh ran."""
    import time

    from hermes_cli.dashboard_auth import routes

    access, refresh = _native_app_sign_in(gated)
    renew_with_provider = routes.refresh_session_coalesced
    renewed = []

    def provider_answers_after_sign_out(*args, **kwargs):
        sign_out()
        later = time.time() + 5  # the stub provider signs whole seconds: a distinct pair
        monkeypatch.setattr(time, "time", lambda: later)
        answer = renew_with_provider(*args, **kwargs)
        renewed.append(answer[0])
        return answer

    monkeypatch.setattr(routes, "refresh_session_coalesced", provider_answers_after_sign_out)
    _refused(_renew(gated, refresh))
    assert renewed[0].refresh_token != refresh
    _refused_alone(gated, renewed[0].access_token, renewed[0].refresh_token)
    _refused_alone(gated, access, refresh)


def test_a_native_request_while_sign_out_replaces_the_credential_is_refused(gated, sign_out, monkeypatch):
    """Sign-out drops the native sign-ins before it replaces the credential, so a native app's request
    that lands once the new credential is in use, before any grant made under the old one has been
    ended, gets nothing that could outlive the sign-out under the new credential."""
    from hermes_cli import browser_credential

    access, _refresh = _native_app_sign_in(gated)
    during = []

    def a_native_request():
        during.append(gated.browser().post("/api/auth/ws-ticket", headers=_bearer(access)))
        return 0

    monkeypatch.setattr(browser_credential, "_revokers", {"probe": a_native_request, **browser_credential._revokers})
    sign_out()
    _refused(during[0])


def test_a_native_sign_in_finished_before_sign_out_ends_with_it(gated, sign_out):
    """The user finished a native app's sign-in (the system browser landed on the app's loopback
    redirect) just before the owner signed out, and the app redeems its code afterwards: it gets the
    answer any bad code gets, as a browser login finished before sign-out ends with it. A sign-in the
    user started before sign-out and finished after it is a new one, and works."""
    finished_before = _start_native_sign_in(gated)()
    started_before = _start_native_sign_in(gated)
    sign_out()
    refused, bad = _redeem(gated, finished_before), _redeem(gated, "never-minted")
    assert refused.status_code == bad.status_code == 400 and refused.json() == bad.json()
    tokens = _redeem(gated, started_before())
    assert tokens.status_code == 200, tokens.text
    assert gated.browser().get("/api/auth/me", headers=_bearer(tokens.json()["access_token"])).status_code == 200
    assert _renew(gated, tokens.json()["refresh_token"]).status_code == 200


def test_a_sign_out_that_lands_while_a_native_code_is_minted_ends_that_sign_in(gated, sign_out, monkeypatch):
    """What a loopback code is bound to is read before the code exists, so a code whose minting a
    sign-out overtakes still counts as minted before it and redeems nothing."""
    from hermes_cli.dashboard_auth import native_flow

    mint = native_flow.complete_pending

    def overtaken_by_sign_out(*args, **kwargs):
        sign_out()
        return mint(*args, **kwargs)

    finish = _start_native_sign_in(gated)
    monkeypatch.setattr(native_flow, "complete_pending", overtaken_by_sign_out)
    code = finish()
    assert _redeem(gated, code).status_code == 400


def test_no_native_sign_in_gets_through_while_sign_out_replaces_the_credential(gated, sign_out, monkeypatch):
    """Sign-out drops the native sign-ins, then stores the new credential and puts it in use. In
    between, while the old credential is still in use, a code minted before the sign-out is redeemed
    for nothing (its pair would be recorded after the drop and outlive the sign-out), and a sign-in the
    user finishes then was finished under the old credential, so its code redeems nothing after the
    sign-out, as a browser login finished then is bound to the old credential and ends."""
    from gateway import webapp_listener

    minted_before = _start_native_sign_in(gated)()
    finish = _start_native_sign_in(gated)
    store = webapp_listener.browser_session_token
    during = {}

    def store_the_new_credential(home, *, rotate=False):
        during["redeemed"] = _redeem(gated, minted_before)
        during["minted"] = finish()
        return store(home, rotate=rotate)

    monkeypatch.setattr(webapp_listener, "browser_session_token", store_the_new_credential)
    sign_out()
    assert during["redeemed"].status_code == 400, during["redeemed"].text
    after = _redeem(gated, during["minted"])
    assert after.status_code == 400, after.text


def test_a_sign_out_that_cannot_replace_the_credential_says_it_signed_out_native_apps_only(
        gated, control, monkeypatch, tmp_path, capsys):
    """Sign-out drops the native sign-ins first. When it then cannot store the new credential (a folder
    where its file goes), native apps are signed out and browsers are not, and no connection closes:
    ``hermes webapp --sign-out`` says that, names the file and fails. A native app can sign in again."""
    from gateway.webapp_listener import TOKEN_PATH
    from hermes_cli import webapp_launcher as launcher

    access, refresh = _native_app_sign_in(gated)
    browser = gated.browser()
    _sign_in_with_password(browser)
    token_path = tmp_path / ".hermes" / TOKEN_PATH
    token_path.unlink(missing_ok=True)
    token_path.mkdir(parents=True)
    monkeypatch.setattr(launcher, "_control", lambda _home, verb, params=None: control(verb))
    assert launcher._sign_out(tmp_path / ".hermes") == 1
    out = capsys.readouterr().out
    assert out.startswith("Native apps that signed in on the Webapp's listener were signed out, but")
    assert "browsers stay signed in" in out and str(token_path) in out and "No connection was closed." in out
    assert gated.server._SESSION_TOKEN == _TOKEN
    assert browser.get("/api/auth/me").status_code == 200
    _refused_alone(gated, access, refresh)
    _native_app_sign_in(gated)


def test_replacing_the_stored_credential_without_sign_out_keeps_native_tokens(gated, monkeypatch, tmp_path):
    """A listener that fails to start replaces the stored credential and is not a sign-out. The
    native tokens this listener gave out still work when it serves again."""
    from gateway.webapp_listener import browser_session_token

    access, refresh = _native_app_sign_in(gated)
    token = browser_session_token(tmp_path / ".hermes", rotate=True)
    _restart(gated, monkeypatch, token=token)
    assert gated.browser().get("/api/auth/me", headers=_bearer(access)).status_code == 200
    assert _renew(gated, refresh).status_code == 200


def test_sign_out_while_nothing_is_serving_drops_native_tokens(gated, monkeypatch, tmp_path):
    """With no Webapp being served, sign-out replaces the stored credential and drops the record,
    so the next start does not accept those tokens on their own."""
    from gateway.webapp_listener import sign_out_stored_credential

    access, refresh = _native_app_sign_in(gated)
    token = sign_out_stored_credential(tmp_path / ".hermes")
    _restart(gated, monkeypatch, token=token)
    _refused_alone(gated, access, refresh)


def test_only_the_spelling_given_to_a_native_app_works(gated):
    """The providers accept other spellings of a token (the password provider and the test provider
    decode base64 leniently); the listener takes only the one it gave out."""
    access, refresh = _native_app_sign_in(gated)
    _refused_alone(gated, f'"{access}"', f'"{refresh}"')


def test_off_the_webapp_any_provider_token_works_on_its_own_as_on_main(gated, monkeypatch):
    monkeypatch.setattr(gated.server.app.state, "ui_surface", "dashboard")
    browser = gated.browser()
    _sign_in_with_password(browser)
    access, refresh = _tokens(browser)
    assert gated.browser().get("/api/auth/me", headers=_bearer(access)).status_code == 200
    assert _socket_close_code(gated.browser(), "/api/events?channel=tab-1", access) is None
    assert _renew(gated, refresh).status_code == 200


def _gateway_socket_with(gated, access):
    """The ``/api/ws`` upgrade from a client holding nothing but *access* (``?token=``): the close
    code the gate answers with, or None when it lets the socket open."""
    from urllib.parse import quote

    try:
        with gated.browser().websocket_connect(f"ws://hermes.lan:9120/api/ws?token={quote(access)}") as ws:
            return _close_code(ws, 0.5)
    except WebSocketDisconnect as closed:
        return closed.code


# Sockets on the Webapp's listener that take a provider token as ``?token=`` (the host terminal takes
# only its own ticket); ``/api/console`` runs the same gate as ``/api/pty``.
TOKEN_SOCKETS = ("/api/ws", "/api/events?channel=tab-1", "/api/pub?channel=tab-1", "/api/pty",
                 "/api/audio/speak-stream", "/api/audio/transcribe-stream")


def _socket_close_code(client, path, token, *, credential="token"):
    """The code a dial of *path* presenting ``?token=`` *token* (or *credential*, such as ``ticket``)
    is closed with, or None while it stays open."""
    joiner = "&" if "?" in path else "?"
    try:
        with client.websocket_connect(f"ws://hermes.lan:9120{path}{joiner}{credential}={token}") as ws:
            return _close_code(ws, 0.5)
    except WebSocketDisconnect as closed:
        return closed.code


def test_a_logins_access_token_opens_no_socket_on_its_own(gated, monkeypatch):
    """The upgrade gate takes a provider token on its own on the same terms as the bearer header:
    on the Webapp only one given to a native app's sign-in, anywhere else any, as on main."""
    browser = gated.browser()
    _sign_in_with_password(browser)
    access, _ = _tokens(browser)
    native_access, _ = _native_app_sign_in(gated)
    assert _gateway_socket_with(gated, access) == 4401
    assert _gateway_socket_with(gated, native_access) is None
    monkeypatch.setattr(gated.server.app.state, "ui_surface", "dashboard")
    assert _gateway_socket_with(gated, access) is None


@pytest.mark.parametrize("path", TOKEN_SOCKETS)
def test_a_logins_access_token_opens_none_of_the_token_sockets(gated, sign_out, path):
    """A socket's ``?token=`` follows the bearer header's rule: a browser login's access token,
    copied out of its cookie, opens no socket on the Webapp's listener, before sign-out or after it."""
    browser = gated.browser()
    _sign_in_with_password(browser)
    access, _refresh = _tokens(browser)
    assert _socket_close_code(gated.browser(), path, access) == 4401
    sign_out()
    assert _socket_close_code(gated.browser(), path, access) == 4401


def test_sign_out_closes_the_socket_a_native_apps_token_opened(gated, sign_out):
    """A token the listener gave a native app's sign-in opens a socket as ``?token=``; sign-out closes
    that socket as it closes a login's, counts it, and the token opens none afterwards."""
    access, _refresh = _native_app_sign_in(gated)
    with gated.browser().websocket_connect(f"ws://hermes.lan:9120/api/events?channel=desk&token={access}") as events:
        assert _close_code(events, 0.2) is None
        assert sign_out()["connections_closed"] == 1
        assert _close_code(events) == 4401
    assert _socket_close_code(gated.browser(), "/api/events?channel=desk", access) == 4401


def test_sign_out_closes_the_sockets_a_native_apps_tickets_opened(gated, sign_out):
    """A native app's bearer mints socket tickets as a login does: the socket one opened closes at
    sign-out, and one minted before sign-out opens nothing after it."""
    access, _refresh = _native_app_sign_in(gated)
    app = gated.browser()

    def ticket():
        minted = app.post("/api/auth/ws-ticket", headers=_bearer(access))
        assert minted.status_code == 200, minted.text
        return minted.json()["ticket"]

    with app.websocket_connect(f"ws://hermes.lan:9120/api/events?channel=desk&ticket={ticket()}") as events:
        spare = ticket()
        assert _close_code(events, 0.2) is None
        sign_out()
        assert _close_code(events) == 4401
    assert _socket_close_code(app, "/api/events?channel=desk", spare, credential="ticket") == 4401


@pytest.mark.platforms("posix")
def test_the_record_of_native_sign_ins_is_user_only(gated, tmp_path):
    from hermes_cli.webapp_sign_in import RECORD_PATH

    _native_app_sign_in(gated)
    record = tmp_path / ".hermes" / RECORD_PATH
    assert record.stat().st_mode & 0o777 == 0o600
    assert record.parent.stat().st_mode & 0o777 == 0o700
