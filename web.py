#!/usr/bin/env python3

import os

from flask import Flask, render_template
from trivia.models import db

app = Flask(__name__)

WS_ADDR = os.environ.get('WS_ADDR', 'ws://localhost:8080')


@app.route('/')
def index():
    return render_template('index.html', WS_ADDR=WS_ADDR)

db.bind('postgres', database='trivia')
db.generate_mapping()


if __name__ == '__main__':
    app.run(debug=True)
