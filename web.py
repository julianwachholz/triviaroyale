#!/usr/bin/env python3

import os

from flask import Flask, render_template
from flask.ext.admin import Admin, AdminIndexView

from pony_admin import ModelView

from trivia.models import db
from trivia.models import Category, Question, Player, Round, Report


db.bind('postgres', database='trivia')
db.generate_mapping()

app = Flask(__name__)
admin = Admin(app, index_view=AdminIndexView(url='/admin'))

WS_ADDR = os.environ.get('WS_ADDR', 'ws://localhost:8080')


@app.route('/')
def index():
    return render_template('index.html', WS_ADDR=WS_ADDR)


class CategoryView(ModelView):
    column_list = ['name']

admin.add_view(CategoryView(Category))


class QuestionView(ModelView):
    column_list = ['active', 'question', 'answer', 'times_played', 'times_solved']

admin.add_view(QuestionView(Question))


class PlayerView(ModelView):
    column_list = ['name', 'has_password', 'email', 'date_joined', 'last_played']

admin.add_view(PlayerView(Player))


class RoundView(ModelView):
    column_list = ['id', 'question.id', 'start_time', 'solved', 'solver', 'time_taken', 'points']

admin.add_view(RoundView(Round))
admin.add_view(ModelView(Report))


if __name__ == '__main__':
    app.run(debug=True)
