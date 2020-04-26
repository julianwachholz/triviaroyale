#!/usr/bin/env python3

import calendar
import datetime
import os

from flask import Flask, abort, redirect, render_template, request, url_for
from pony.orm import count, db_session, left_join
from random_username.generate import generate_username
from raven.contrib.flask import Sentry

from trivia.helpers import format_number, get_week_tuple, timesince
from trivia.models import Player, db

app = Flask(__name__)
app.jinja_env.filters["timesince"] = timesince
app.jinja_env.filters["format_number"] = format_number

if "SENTRY_DSN" in os.environ:
    app.config["SENTRY_DSN"] = os.environ.get("SENTRY_DSN")
    sentry = Sentry(app)

WS_ADDR = os.environ.get("WS_ADDR", "ws://localhost:8080")

EARLIEST_DATE = datetime.date(2017, 5, 22)


@app.route("/")
def index():
    now = datetime.datetime.utcnow()
    return render_template("index.html", WS_ADDR=WS_ADDR, now=now)


@app.route("/stats/search/")
def stats_search(error=None, name=None):
    suggestions = []
    if name is None:
        name = ""
    else:
        with db_session():
            suggestions = Player.select(lambda p: name.lower() in p.name.lower())[:6]

    return render_template(
        "stats/search.html", error=error, name=name, suggestions=suggestions
    )


@app.route("/stats/user/", methods=["GET", "POST"])
@db_session
def stats_user():
    if request.method == "POST":
        args = request.form
    else:
        args = request.args

    backlink = request.args.get("back", None)

    player_name = args.get("name")
    player = Player.get(lambda p: p.name == player_name)

    if player is None:
        return stats_search(error="Player not found.", name=player_name)

    stats = player.get_stats()
    legends = [
        "Points",
        "Rounds",
        "Avg. Points",
        "Max. Points",
        "Avg. Time",
        "Fastest Answer",
    ]

    return render_template(
        "stats/user.html",
        backlink=backlink,
        player=player,
        legends=legends,
        stats=stats,
    )


@app.route("/highscores/search/", methods=["POST"])
def highscore_search():
    mode = request.form.get("mode", None)
    dt = request.form.get("dt").split("-")

    if mode == "year" and len(dt) == 1:
        return redirect(url_for("highscores", year=dt[0]))

    if mode == "month" and len(dt) == 2:
        return redirect(url_for("highscores", year=dt[0], month=dt[1]))

    if mode == "week" and len(dt) == 2:
        # expected format is e.g. "2015-W15", remove 'W' here from dt[1]
        return redirect(url_for("highscores", year=dt[0], week=dt[1][1:]))

    if mode == "day" and len(dt) == 3:
        return redirect(url_for("highscores", year=dt[0], month=dt[1], day=dt[2]))

    abort(400, "I don't understand this date.")


def url_for_highscore(mode, dt):
    if not isinstance(dt, (datetime.date, datetime.datetime)):
        return None
    now = datetime.datetime.utcnow().date()

    if mode == "year":
        if EARLIEST_DATE.year <= dt.year <= now.year:
            return url_for("highscores", year=dt.year)
        else:
            return None

    if mode == "month":
        if EARLIEST_DATE.replace(day=1) <= dt.replace(day=1) <= now.replace(day=1):
            return url_for("highscores", year=dt.year, month=dt.month)
        else:
            return None

    if mode == "week":
        if (
            EARLIEST_DATE.year <= dt.year < now.year
            or dt.isocalendar()[1] <= now.isocalendar()[1]
        ):
            cal = dt.isocalendar()
            return url_for("highscores", year=cal[0], week=cal[1])
        else:
            return None

    if mode == "day":
        if EARLIEST_DATE <= dt <= now:
            return url_for("highscores", year=dt.year, month=dt.month, day=dt.day)
        else:
            return None


app.jinja_env.globals["url_for_highscore"] = url_for_highscore


def _highscore_nav_links(mode, dt):
    prev_dt, next_dt = None, None

    if mode == "year":
        prev_dt = dt.replace(year=dt.year - 1)
        next_dt = dt.replace(year=dt.year + 1)

    if mode == "month":
        days = calendar.monthrange(dt.year, dt.month)[1]
        prev_dt = dt - datetime.timedelta(days=dt.day)
        next_dt = dt + datetime.timedelta(days=days - dt.day + 1)

    if mode == "week" or mode == "day":
        y = datetime.timedelta(days=7 if mode == "week" else 1)
        prev_dt = dt - y
        next_dt = dt + y

    return url_for_highscore(mode, prev_dt), url_for_highscore(mode, next_dt)


@app.route("/highscores/")
@app.route("/highscores/<int(4):year>/")
@app.route("/highscores/<int(4):year>/W<int(2):week>/")
@app.route("/highscores/<int(4):year>/<int(2):month>/")
@app.route("/highscores/<int(4):year>/<int(2):month>/<int(2):day>/")
@db_session
def highscores(year=None, month=None, day=None, week=None):
    mode = "all_time"
    title = "All Time"
    subtitle = None
    dt, f = None, None

    today = datetime.datetime.utcnow().date()
    r = today  # dummy for filter lambdas

    # daily highscores
    if year and month and day:
        mode = "day"
        dt = datetime.date(year, month, day)
        f = lambda: r.start_time.date() == dt
        title = dt.strftime("%B %d, %Y")

    # weekly highscores
    elif year and week:
        mode = "week"
        dt, dt_week_end = get_week_tuple(
            datetime.date(year, 1, 1) + datetime.timedelta(weeks=week - 1)
        )
        f = lambda: r.start_time.date() >= dt and r.start_time.date() <= dt_week_end
        title = "Week {}, {}".format(dt.isocalendar()[1], dt.isocalendar()[0])

        end_fmt = " - %B %d" if dt.month != dt_week_end.month else "-%d"
        subtitle = " ({}{})".format(dt.strftime("%B %d"), dt_week_end.strftime(end_fmt))

    # monthly highscores
    elif year and month:
        mode = "month"
        dt = datetime.date(year, month, 1)
        f = lambda: r.start_time.year == dt.year and r.start_time.month == dt.month
        title = dt.strftime("%B %Y")

    # yearly highscores
    elif year:
        mode = "year"
        dt = datetime.date(year, 1, 1)
        f = lambda: r.start_time.year == dt.year
        title = dt.strftime("%Y")

    if dt is not None and today < dt:
        # Can't see into the future :(
        abort(400, "Cannot see into the future: {}".format(dt))

    highscores = left_join(
        (p, sum(r.points), count(r)) for p in Player for r in p.rounds_solved
    ).order_by(-2)

    if f is not None:
        highscores = highscores.filter(f)

    if mode == "day":
        if dt == today:
            title = "Today's"
        if dt == today - datetime.timedelta(days=1):
            title = "Yesterday's"

    backlink = None
    if "player" in request.args:
        backlink = "{}?name={}".format(
            url_for("stats_user"), request.args.get("player")
        )

    prevlink, nextlink = _highscore_nav_links(mode, dt)

    return render_template(
        "stats/highscores.html",
        backlink=backlink,
        prevlink=prevlink,
        nextlink=nextlink,
        title=title,
        subtitle=subtitle,
        mode=mode,
        dt=dt,
        today=today,
        highscores=highscores[:10],
    )


@app.route("/randomnick", methods=["POST"])
def random_nickname():
    """
    Generate a random nickname for a new player.

    """
    nickname = generate_username()
    return {"nickname": nickname[0]}


db.bind(
    provider="postgres",
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASS", ""),
    host=os.getenv("DB_HOST", "localhost"),
    database=os.getenv("DB_NAME", "trivia"),
)
db.generate_mapping()


if __name__ == "__main__":
    host = os.environ.get("LISTEN_IP", "127.0.0.1")
    app.run(host=host, port=8000)
