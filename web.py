#!/usr/bin/env python3

import os

from flask import Flask, render_template
from pony.orm import db_session
from trivia.models import db, Player
from trivia.helpers import timesince, format_number


app = Flask(__name__)
app.jinja_env.filters['timesince'] = timesince
app.jinja_env.filters['format_number'] = format_number

WS_ADDR = os.environ.get('WS_ADDR', 'ws://localhost:8080')


@app.route('/')
def index():
    return render_template('index.html', WS_ADDR=WS_ADDR)


@app.route('/stats/<player_name>/')
@db_session
def stats_user(player_name):
    player = Player.get(lambda p: p.name == player_name)
    stats = player.get_stats()
    return render_template('stats/user.html', player=player, stats=stats)


db.bind('postgres', database='trivia')
db.generate_mapping()


if __name__ == '__main__':
    app.run(debug=True)
