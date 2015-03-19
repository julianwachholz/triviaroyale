from datetime import date, datetime
from pony.orm import *


db = Database()
sql_debug(True)


class Category(db.Entity):
    """
    Questions should have at least one category.

    """
    name = Required(str, 25, unique=True)
    questions = Set('Question')


class Question(db.Entity):
    """
    Tweet sized questions.

    Multiple answers are separated using "|"

    """
    active = Required(bool, default=False)

    question = Required(str, 140)
    answer = Required(str, 40)
    categories = Set(Category)

    times_played = Required(int, default=0)
    times_solved = Required(int, default=0)

    date_added = Required(datetime, sql_default='CURRENT_TIMESTAMP')
    date_modified = Optional(datetime)

    rounds = Set('Round')
    reports = Set('Report')
    player = Optional('Player')

    @property
    def primary_answer(self):
        if '|' not in self.answer:
            return self.answer
        return self.answer.split('|')[0]

    @property
    def category_names(self):
        return [c.name for c in self.categories.order_by(Category.name)]

    @property
    def solve_percentage(self):
        if self.times_played == 0:
            return 0
        return self.times_solved / self.times_played

    def before_update(self):
        self.date_modified = datetime.now()


class Player(db.Entity):
    name = Required(str, 40, unique=True)

    date_joined = Required(datetime, sql_default='CURRENT_TIMESTAMP')
    last_played = Optional(datetime)

    rounds_solved = Set('Round')
    submitted_reports = Set('Report')
    submitted_questions = Set(Question)

    def before_update(self):
        self.date_modified = datetime.now()


class Round(db.Entity):
    """
    A single round with a single question.

    """
    question = Required(Question)
    start_time = Required(datetime, sql_default='CURRENT_TIMESTAMP')

    solved = Required(bool, default=False)
    solver = Optional(Player)
    time_taken = Optional(float)
    points_awarded = Optional(int)


class Report(db.Entity):
    """
    A report for a question.

    """
    question = Required(Question)
    player = Required(Player)
    text = Required(str)
    created = Required(datetime, sql_default='CURRENT_TIMESTAMP')
    done = Required(bool, default=False)
