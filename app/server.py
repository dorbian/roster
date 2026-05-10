#!/usr/bin/env python3
import base64
import hashlib
import hmac
import html
import json
import os
import random
import secrets
import sqlite3
import string
import time
from http import cookies
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

APP_NAME = "The Big Tree Roster"
HOSTNAME = os.environ.get("ROSTER_HOSTNAME", "roster.thebigtree.life")
DATA_DIR = os.environ.get("ROSTER_DATA_DIR", "/data")
DB_PATH = os.path.join(DATA_DIR, "roster.db")
SESSION_COOKIE = "roster_session"
SESSION_TTL_SECONDS = int(os.environ.get("SESSION_TTL_SECONDS", str(60 * 60 * 24 * 14)))
MAX_BODY = 1024 * 1024
GAME_TYPES = ["CardParty", "Klaverjassen", "Hartenjagen", "RummyClub", "BattleSolitaire", "Thirty-one", "Teasers", "Rummy", "Poker", "Skat", "Other"]


def now():
    return int(time.time())


def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def db():
    ensure_data_dir()
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def migrate():
    with db() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                gamepoint_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                game_type TEXT NOT NULL,
                invite_code TEXT NOT NULL UNIQUE,
                host_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                status TEXT NOT NULL CHECK(status IN ('setup','active','complete')),
                table_size INTEGER NOT NULL DEFAULT 4,
                total_rounds INTEGER NOT NULL DEFAULT 4,
                current_round INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                started_at INTEGER,
                completed_at INTEGER
            );
            CREATE TABLE IF NOT EXISTS game_members (
                game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK(role IN ('host','player')),
                joined_at INTEGER NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (game_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS rounds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
                round_number INTEGER NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('open','complete')),
                created_at INTEGER NOT NULL,
                completed_at INTEGER,
                UNIQUE(game_id, round_number)
            );
            CREATE TABLE IF NOT EXISTS tables (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                round_id INTEGER NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,
                table_number INTEGER NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('waiting','submitted')),
                submitted_by INTEGER REFERENCES users(id),
                submitted_at INTEGER,
                UNIQUE(round_id, table_number)
            );
            CREATE TABLE IF NOT EXISTS table_players (
                table_id INTEGER NOT NULL REFERENCES tables(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                seat_number INTEGER NOT NULL,
                score INTEGER,
                PRIMARY KEY(table_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS byes (
                round_id INTEGER NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                bye_points INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(round_id, user_id)
            );
            """
        )


def password_hash(password, salt=None):
    if not salt:
        salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 210_000)
    return f"pbkdf2_sha256$210000${salt}${base64.b64encode(digest).decode()}"


def verify_password(password, stored):
    try:
        algo, iterations, salt, expected = stored.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations))
        return hmac.compare_digest(base64.b64encode(digest).decode(), expected)
    except Exception:
        return False


def invite_code(length=8):
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def get_user_from_token(token):
    if not token:
        return None
    with db() as con:
        row = con.execute(
            """
            SELECT u.* FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token = ? AND s.expires_at > ?
            """,
            (token, now()),
        ).fetchone()
        return row


def create_session(user_id):
    token = secrets.token_urlsafe(32)
    ts = now()
    with db() as con:
        con.execute("INSERT INTO sessions(token,user_id,created_at,expires_at) VALUES(?,?,?,?)", (token, user_id, ts, ts + SESSION_TTL_SECONDS))
    return token


def html_escape(value):
    return html.escape(str(value or ""), quote=True)


def csrf_token(handler):
    # SameSite=Lax session cookies and POST-only mutations are sufficient for this MVP.
    return ""


class App(BaseHTTPRequestHandler):
    server_version = "RosterServer/0.1"

    def do_GET(self):
        self.route()

    def do_POST(self):
        self.route()

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} - {fmt % args}")

    def route(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        self.query = parse_qs(parsed.query)
        self.current_user = self.auth_user()
        try:
            if path == "/static/style.css":
                return self.static_css()
            if path == "/healthz":
                return self.text("ok")
            if path == "/":
                return self.home()
            if path == "/register":
                return self.register()
            if path == "/login":
                return self.login()
            if path == "/logout":
                return self.logout()
            if path == "/games/new":
                return self.require_login(self.new_game)()
            if path.startswith("/games/"):
                parts = path.split("/")
                if len(parts) >= 3 and parts[2].isdigit():
                    game_id = int(parts[2])
                    if len(parts) == 3:
                        return self.require_login(lambda: self.game_detail(game_id))()
                    if len(parts) == 4 and parts[3] == "start":
                        return self.require_login(lambda: self.start_game(game_id))()
                    if len(parts) == 4 and parts[3] == "score":
                        return self.require_login(lambda: self.submit_score(game_id))()
            if path.startswith("/j/"):
                code = path.split("/")[2].upper()
                return self.join_game(code)
            return self.not_found()
        except Exception as exc:
            print("ERROR", repr(exc))
            return self.render("Server error", f"<div class='card danger'><h1>Server error</h1><p>{html_escape(exc)}</p></div>", status=500)

    def read_form(self):
        length = int(self.headers.get("content-length", "0"))
        if length > MAX_BODY:
            raise ValueError("request too large")
        raw = self.rfile.read(length).decode("utf-8")
        data = parse_qs(raw)
        return {k: v[0].strip() for k, v in data.items()}

    def auth_user(self):
        jar = cookies.SimpleCookie(self.headers.get("Cookie"))
        morsel = jar.get(SESSION_COOKIE)
        return get_user_from_token(morsel.value if morsel else None)

    def set_session_cookie(self, token):
        cookie = cookies.SimpleCookie()
        cookie[SESSION_COOKIE] = token
        cookie[SESSION_COOKIE]["path"] = "/"
        cookie[SESSION_COOKIE]["httponly"] = True
        cookie[SESSION_COOKIE]["samesite"] = "Lax"
        cookie[SESSION_COOKIE]["max-age"] = SESSION_TTL_SECONDS
        self.extra_headers = [cookie.output(header="")]

    def clear_session_cookie(self):
        cookie = cookies.SimpleCookie()
        cookie[SESSION_COOKIE] = ""
        cookie[SESSION_COOKIE]["path"] = "/"
        cookie[SESSION_COOKIE]["httponly"] = True
        cookie[SESSION_COOKIE]["samesite"] = "Lax"
        cookie[SESSION_COOKIE]["max-age"] = 0
        self.extra_headers = [cookie.output(header="")]

    def send_html(self, body, status=200):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        for h in getattr(self, "extra_headers", []):
            name, value = h.strip().split(":", 1) if ":" in h else ("Set-Cookie", h.strip())
            self.send_header(name, value.strip())
        self.end_headers()
        self.wfile.write(data)
        self.extra_headers = []

    def redirect(self, location):
        self.send_response(303)
        self.send_header("Location", location)
        for h in getattr(self, "extra_headers", []):
            name, value = h.strip().split(":", 1) if ":" in h else ("Set-Cookie", h.strip())
            self.send_header(name, value.strip())
        self.end_headers()
        self.extra_headers = []

    def text(self, value):
        data = value.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def static_css(self):
        css_path = os.path.join(os.path.dirname(__file__), "style.css")
        with open(css_path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "text/css; charset=utf-8")
        self.send_header("Cache-Control", "public, max-age=3600")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def render(self, title, content, status=200):
        user = self.current_user
        nav_auth = ""
        if user:
            nav_auth = f"<a href='/'>My games</a><a href='/games/new'>Create game</a><span class='user-pill'>{html_escape(user['display_name'])}</span><form method='post' action='/logout'><button class='link-button'>Logout</button></form>"
        else:
            nav_auth = "<a href='/login'>Login</a><a class='button small' href='/register'>Create account</a>"
        body = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html_escape(title)} · {APP_NAME}</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <header class="topbar">
    <a class="brand" href="/"><span class="tree">♣</span><span>Roster</span><small>{HOSTNAME}</small></a>
    <nav>{nav_auth}</nav>
  </header>
  <main>{content}</main>
  <footer>Unofficial companion roster for hosted card-game evenings. No public roster directory.</footer>
</body>
</html>"""
        self.send_html(body, status=status)

    def home(self):
        if not self.current_user:
            content = """
<section class='hero'>
  <div>
    <p class='eyebrow'>Private roster hosting</p>
    <h1>Host a card-game night with invite-only rosters.</h1>
    <p>Create a game, share a private join URL, lock the roster, and let the server keep rounds fair.</p>
    <div class='actions'><a class='button' href='/register'>Create account</a><a class='button ghost' href='/login'>Login</a></div>
  </div>
  <div class='hero-card'><strong>Round engine</strong><span>Balanced tables</span><span>Score entry</span><span>Auto progression</span></div>
</section>
"""
            return self.render("Private rosters", content)
        with db() as con:
            games = con.execute(
                """
                SELECT g.*, u.display_name AS host_name, COUNT(gm2.user_id) AS members
                FROM games g
                JOIN game_members gm ON gm.game_id = g.id AND gm.user_id = ?
                JOIN users u ON u.id = g.host_user_id
                LEFT JOIN game_members gm2 ON gm2.game_id = g.id AND gm2.active = 1
                GROUP BY g.id
                ORDER BY CASE g.status WHEN 'active' THEN 0 WHEN 'setup' THEN 1 ELSE 2 END, g.created_at DESC
                """,
                (self.current_user["id"],),
            ).fetchall()
        rows = "".join([self.game_card(g) for g in games]) or "<div class='card empty'><h2>No active memberships</h2><p>Create a private game or open an invite link you received.</p></div>"
        content = f"<section class='page-title'><h1>My games</h1><a class='button' href='/games/new'>Create game</a></section><section class='grid'>{rows}</section>"
        return self.render("My games", content)

    def game_card(self, g):
        return f"""
<a class='card game-card' href='/games/{g['id']}'>
  <span class='status {g['status']}'>{html_escape(g['status'])}</span>
  <h2>{html_escape(g['title'])}</h2>
  <p>{html_escape(g['game_type'])} · hosted by {html_escape(g['host_name'])}</p>
  <div class='meta'><span>{g['members']} players</span><span>Round {g['current_round']} / {g['total_rounds']}</span></div>
</a>"""

    def register(self):
        if self.current_user:
            return self.redirect("/")
        error = ""
        if self.command == "POST":
            form = self.read_form()
            username = form.get("username", "").lower()
            display = form.get("display_name", "")
            gp = form.get("gamepoint_name", "")
            password = form.get("password", "")
            if len(username) < 3 or len(password) < 8 or not display or not gp:
                error = "Username, display name, GamePoint name and an 8+ character password are required."
            else:
                try:
                    with db() as con:
                        cur = con.execute("INSERT INTO users(username,display_name,gamepoint_name,password_hash,created_at) VALUES(?,?,?,?,?)", (username, display, gp, password_hash(password), now()))
                    token = create_session(cur.lastrowid)
                    self.set_session_cookie(token)
                    return self.redirect("/")
                except sqlite3.IntegrityError:
                    error = "That username is already taken."
        return self.auth_form("Create account", "/register", error, include_profile=True)

    def login(self):
        if self.current_user:
            return self.redirect("/")
        error = ""
        if self.command == "POST":
            form = self.read_form()
            username = form.get("username", "").lower()
            with db() as con:
                user = con.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            if user and verify_password(form.get("password", ""), user["password_hash"]):
                token = create_session(user["id"])
                self.set_session_cookie(token)
                return self.redirect("/")
            error = "Invalid username or password."
        return self.auth_form("Login", "/login", error, include_profile=False)

    def logout(self):
        jar = cookies.SimpleCookie(self.headers.get("Cookie"))
        morsel = jar.get(SESSION_COOKIE)
        if morsel:
            with db() as con:
                con.execute("DELETE FROM sessions WHERE token = ?", (morsel.value,))
        self.clear_session_cookie()
        return self.redirect("/")

    def auth_form(self, title, action, error, include_profile):
        extra = ""
        if include_profile:
            extra = """
<label>Display name<input name='display_name' required autocomplete='name'></label>
<label>GamePoint player name<input name='gamepoint_name' required></label>
"""
        err = f"<p class='error'>{html_escape(error)}</p>" if error else ""
        content = f"""
<section class='auth-panel card'>
<h1>{html_escape(title)}</h1>{err}
<form method='post' action='{action}' class='stack'>
<label>Username<input name='username' required autocomplete='username'></label>
{extra}
<label>Password<input type='password' name='password' required autocomplete='current-password'></label>
<button class='button' type='submit'>{html_escape(title)}</button>
</form>
</section>"""
        return self.render(title, content)

    def new_game(self):
        if self.command == "POST":
            form = self.read_form()
            title = form.get("title") or "Card game night"
            game_type = form.get("game_type") if form.get("game_type") in GAME_TYPES else "Other"
            table_size = max(2, min(8, int(form.get("table_size") or 4)))
            rounds = max(1, min(20, int(form.get("total_rounds") or 4)))
            code = invite_code()
            with db() as con:
                cur = con.execute("INSERT INTO games(title,game_type,invite_code,host_user_id,status,table_size,total_rounds,created_at) VALUES(?,?,?,?,?,?,?,?)", (title, game_type, code, self.current_user["id"], "setup", table_size, rounds, now()))
                game_id = cur.lastrowid
                con.execute("INSERT INTO game_members(game_id,user_id,role,joined_at,active) VALUES(?,?,?,?,1)", (game_id, self.current_user["id"], "host", now()))
            return self.redirect(f"/games/{game_id}")
        options = "".join([f"<option>{html_escape(x)}</option>" for x in GAME_TYPES])
        content = f"""
<section class='auth-panel card wide'><h1>Create private game</h1>
<form method='post' class='stack'>
<label>Title<input name='title' value='Friday card roster' required></label>
<label>Game type<select name='game_type'>{options}</select></label>
<div class='form-row'><label>Table size<input type='number' min='2' max='8' name='table_size' value='4'></label><label>Rounds<input type='number' min='1' max='20' name='total_rounds' value='4'></label></div>
<button class='button'>Create invite</button>
</form></section>"""
        return self.render("Create game", content)

    def join_game(self, code):
        if not self.current_user:
            return self.redirect(f"/login?next=/j/{code}")
        with db() as con:
            game = con.execute("SELECT * FROM games WHERE invite_code = ?", (code,)).fetchone()
            if not game:
                return self.not_found()
            if game["status"] != "setup":
                return self.render("Roster locked", "<div class='card danger'><h1>Roster locked</h1><p>This game has already started or completed.</p></div>", status=403)
            con.execute("INSERT OR IGNORE INTO game_members(game_id,user_id,role,joined_at,active) VALUES(?,?,?,?,1)", (game["id"], self.current_user["id"], "player", now()))
        return self.redirect(f"/games/{game['id']}")

    def load_game_for_member(self, game_id):
        with db() as con:
            game = con.execute("SELECT g.*, u.display_name host_name FROM games g JOIN users u ON u.id = g.host_user_id WHERE g.id = ?", (game_id,)).fetchone()
            if not game:
                return None, False
            member = con.execute("SELECT * FROM game_members WHERE game_id = ? AND user_id = ?", (game_id, self.current_user["id"])).fetchone()
            return game, bool(member)

    def game_detail(self, game_id):
        game, allowed = self.load_game_for_member(game_id)
        if not game or not allowed:
            return self.not_found()
        with db() as con:
            members = con.execute("SELECT gm.*, u.display_name, u.gamepoint_name FROM game_members gm JOIN users u ON u.id = gm.user_id WHERE gm.game_id = ? AND gm.active = 1 ORDER BY gm.joined_at", (game_id,)).fetchall()
            rounds = con.execute("SELECT * FROM rounds WHERE game_id = ? ORDER BY round_number", (game_id,)).fetchall()
            current_round = con.execute("SELECT * FROM rounds WHERE game_id = ? AND round_number = ?", (game_id, game["current_round"])).fetchone() if game["current_round"] else None
            tables = []
            byes = []
            if current_round:
                tables = con.execute("SELECT * FROM tables WHERE round_id = ? ORDER BY table_number", (current_round["id"],)).fetchall()
                byes = con.execute("SELECT b.*, u.display_name FROM byes b JOIN users u ON u.id = b.user_id WHERE b.round_id = ?", (current_round["id"],)).fetchall()
        member_list = "".join([f"<li><strong>{html_escape(m['display_name'])}</strong><span>{html_escape(m['gamepoint_name'])}</span></li>" for m in members])
        is_host = game["host_user_id"] == self.current_user["id"]
        invite_url = f"https://{HOSTNAME}/j/{game['invite_code']}"
        host_tools = ""
        if is_host and game["status"] == "setup":
            host_tools = f"<form method='post' action='/games/{game_id}/start'><button class='button'>Lock roster & start</button></form>"
        round_html = self.round_view(game, current_round, tables, byes)
        content = f"""
<section class='page-title'><div><p class='eyebrow'>{html_escape(game['game_type'])}</p><h1>{html_escape(game['title'])}</h1><p>Hosted by {html_escape(game['host_name'])}</p></div><span class='status {game['status']}'>{game['status']}</span></section>
<section class='split'>
<div class='card'><h2>Private join URL</h2><p class='muted'>Only people with this URL can join while the roster is still open.</p><input class='copy' readonly value='{html_escape(invite_url)}'>{host_tools}</div>
<div class='card'><h2>Roster</h2><ul class='roster'>{member_list}</ul></div>
</section>
{round_html}
"""
        return self.render(game["title"], content)

    def round_view(self, game, current_round, tables, byes):
        if game["status"] == "setup":
            return "<section class='card'><h2>Waiting to start</h2><p>The host can lock the roster when everyone has joined.</p></section>"
        if game["status"] == "complete":
            return self.scoreboard(game["id"], complete=True)
        if not current_round:
            return "<section class='card'><h2>No round created yet</h2></section>"
        table_html = ""
        for t in tables:
            with db() as con:
                players = con.execute("SELECT tp.*, u.display_name FROM table_players tp JOIN users u ON u.id = tp.user_id WHERE tp.table_id = ? ORDER BY tp.seat_number", (t["id"],)).fetchall()
            score_fields = "".join([f"<label>{html_escape(p['display_name'])}<input type='number' name='score_{p['user_id']}' value='{'' if p['score'] is None else p['score']}' required></label>" for p in players])
            hidden = "".join([f"<input type='hidden' name='player_ids' value='{p['user_id']}'>" for p in players])
            table_html += f"""
<div class='table-card'>
<h3>Table {t['table_number']} <span class='status {t['status']}'>{t['status']}</span></h3>
<form method='post' action='/games/{game['id']}/score' class='score-form'>
<input type='hidden' name='table_id' value='{t['id']}'>{hidden}
{score_fields}
<button class='button small'>Submit scores</button>
</form>
</div>"""
        bye_html = "".join([f"<li>{html_escape(b['display_name'])} <span>bye</span></li>" for b in byes]) or "<li>No byes this round</li>"
        return f"""
<section class='page-title compact'><h2>Round {current_round['round_number']} of {game['total_rounds']}</h2><p>When every table is submitted, the server creates the next round automatically.</p></section>
<section class='tables'>{table_html}</section>
<section class='split'><div class='card'><h2>Byes</h2><ul class='roster'>{bye_html}</ul></div>{self.scoreboard(game['id'], complete=False)}</section>
"""

    def scoreboard(self, game_id, complete=False):
        with db() as con:
            rows = con.execute("""
                SELECT u.display_name, u.gamepoint_name,
                       COALESCE(SUM(tp.score),0) + COALESCE((SELECT SUM(b.bye_points) FROM byes b WHERE b.user_id = u.id AND b.round_id IN (SELECT id FROM rounds WHERE game_id = ?)),0) AS total,
                       COUNT(DISTINCT tp.table_id) AS played,
                       COALESCE((SELECT COUNT(*) FROM byes b WHERE b.user_id = u.id AND b.round_id IN (SELECT id FROM rounds WHERE game_id = ?)),0) AS byes
                FROM game_members gm
                JOIN users u ON u.id = gm.user_id
                LEFT JOIN table_players tp ON tp.user_id = u.id AND tp.table_id IN (SELECT t.id FROM tables t JOIN rounds r ON r.id = t.round_id WHERE r.game_id = ? AND t.status = 'submitted')
                WHERE gm.game_id = ? AND gm.active = 1
                GROUP BY u.id
                ORDER BY total DESC, played DESC, u.display_name
            """, (game_id, game_id, game_id, game_id)).fetchall()
        trs = "".join([f"<tr><td>{html_escape(r['display_name'])}<small>{html_escape(r['gamepoint_name'])}</small></td><td>{r['total']}</td><td>{r['played']}</td><td>{r['byes']}</td></tr>" for r in rows])
        title = "Final standings" if complete else "Standings"
        return f"<div class='card'><h2>{title}</h2><table><thead><tr><th>Player</th><th>Score</th><th>Played</th><th>Byes</th></tr></thead><tbody>{trs}</tbody></table></div>"

    def start_game(self, game_id):
        game, allowed = self.load_game_for_member(game_id)
        if not game or not allowed or game["host_user_id"] != self.current_user["id"]:
            return self.not_found()
        if game["status"] != "setup":
            return self.redirect(f"/games/{game_id}")
        with db() as con:
            count = con.execute("SELECT COUNT(*) c FROM game_members WHERE game_id = ? AND active = 1", (game_id,)).fetchone()["c"]
            if count < 2:
                return self.render("Not enough players", "<div class='card danger'><h1>Not enough players</h1><p>At least two players are required.</p></div>", status=400)
            con.execute("UPDATE games SET status='active', started_at=?, current_round=1 WHERE id=?", (now(), game_id))
        self.create_round(game_id, 1)
        return self.redirect(f"/games/{game_id}")

    def submit_score(self, game_id):
        form = self.read_form()
        table_id = int(form.get("table_id"))
        with db() as con:
            game = con.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
            table = con.execute("SELECT t.*, r.game_id, r.round_number FROM tables t JOIN rounds r ON r.id = t.round_id WHERE t.id = ? AND r.game_id = ?", (table_id, game_id)).fetchone()
            if not game or not table:
                return self.not_found()
            member = con.execute("SELECT 1 FROM table_players WHERE table_id = ? AND user_id = ?", (table_id, self.current_user["id"])).fetchone()
            is_host = game["host_user_id"] == self.current_user["id"]
            if not member and not is_host:
                return self.render("Forbidden", "<div class='card danger'><h1>Forbidden</h1><p>Only table players or the host can submit this score.</p></div>", status=403)
            players = con.execute("SELECT user_id FROM table_players WHERE table_id = ?", (table_id,)).fetchall()
            for p in players:
                score = int(form.get(f"score_{p['user_id']}", "0") or 0)
                con.execute("UPDATE table_players SET score = ? WHERE table_id = ? AND user_id = ?", (score, table_id, p["user_id"]))
            con.execute("UPDATE tables SET status='submitted', submitted_by=?, submitted_at=? WHERE id=?", (self.current_user["id"], now(), table_id))
        self.auto_progress(game_id)
        return self.redirect(f"/games/{game_id}")

    def create_round(self, game_id, round_number):
        with db() as con:
            game = con.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
            members = [dict(r) for r in con.execute("SELECT u.id, u.display_name FROM game_members gm JOIN users u ON u.id = gm.user_id WHERE gm.game_id = ? AND gm.active = 1", (game_id,)).fetchall()]
            history = con.execute("SELECT tp.user_id, r.round_number FROM table_players tp JOIN tables t ON t.id = tp.table_id JOIN rounds r ON r.id = t.round_id WHERE r.game_id = ?", (game_id,)).fetchall()
            bye_counts = {r["user_id"]: r["c"] for r in con.execute("SELECT b.user_id, COUNT(*) c FROM byes b JOIN rounds r ON r.id = b.round_id WHERE r.game_id = ? GROUP BY b.user_id", (game_id,)).fetchall()}
            rnd = con.execute("INSERT INTO rounds(game_id,round_number,status,created_at) VALUES(?,?,?,?)", (game_id, round_number, "open", now()))
            round_id = rnd.lastrowid
            assignments, byes = make_assignments(members, game["table_size"], bye_counts, round_number)
            for user in byes:
                con.execute("INSERT INTO byes(round_id,user_id,bye_points) VALUES(?,?,0)", (round_id, user["id"]))
            for idx, group in enumerate(assignments, start=1):
                t = con.execute("INSERT INTO tables(round_id,table_number,status) VALUES(?,?,?)", (round_id, idx, "waiting"))
                for seat, user in enumerate(group, start=1):
                    con.execute("INSERT INTO table_players(table_id,user_id,seat_number) VALUES(?,?,?)", (t.lastrowid, user["id"], seat))

    def auto_progress(self, game_id):
        with db() as con:
            game = con.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
            if not game or game["status"] != "active":
                return
            round_row = con.execute("SELECT * FROM rounds WHERE game_id = ? AND round_number = ?", (game_id, game["current_round"])).fetchone()
            pending = con.execute("SELECT COUNT(*) c FROM tables WHERE round_id = ? AND status != 'submitted'", (round_row["id"],)).fetchone()["c"]
            if pending:
                return
            con.execute("UPDATE rounds SET status='complete', completed_at=? WHERE id=?", (now(), round_row["id"]))
            if game["current_round"] >= game["total_rounds"]:
                con.execute("UPDATE games SET status='complete', completed_at=? WHERE id=?", (now(), game_id))
                return
            next_round = game["current_round"] + 1
            con.execute("UPDATE games SET current_round=? WHERE id=?", (next_round, game_id))
        self.create_round(game_id, next_round)

    def require_login(self, func):
        def wrapped():
            if not self.current_user:
                return self.redirect("/login")
            return func()
        return wrapped

    def not_found(self):
        return self.render("Not found", "<div class='card danger'><h1>Not found</h1><p>This page does not exist or is private.</p></div>", status=404)


def make_assignments(members, table_size, bye_counts, round_number):
    members = members[:]
    random.Random(round_number).shuffle(members)
    player_count = len(members)
    remainder = player_count % table_size
    bye_count = 0 if remainder == 0 else remainder
    # Prefer one short table over many byes when it would otherwise remove too many people.
    if bye_count and player_count - bye_count < table_size:
        bye_count = 0
    byes = []
    if bye_count:
        members.sort(key=lambda u: (bye_counts.get(u["id"], 0), random.random()))
        byes = members[:bye_count]
        playing = members[bye_count:]
    else:
        playing = members
    random.Random(round_number * 17).shuffle(playing)
    groups = [playing[i:i + table_size] for i in range(0, len(playing), table_size)]
    if len(groups) > 1 and len(groups[-1]) == 1:
        groups[-2].append(groups[-1][0])
        groups.pop()
    return groups, byes


if __name__ == "__main__":
    migrate()
    port = int(os.environ.get("PORT", "8500"))
    bind = os.environ.get("BIND", "0.0.0.0")
    print(f"Starting {APP_NAME} on {bind}:{port}, db={DB_PATH}")
    ThreadingHTTPServer((bind, port), App).serve_forever()
