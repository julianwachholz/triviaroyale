import os
import re
import time
import math
from datetime import datetime, timedelta

from pony.orm import *
from passlib.hash import bcrypt_sha256


db = Database()
sql_debug(bool(os.environ.get('SQL_DEBUG', False)))


class Category(db.Entity):
    """
    Questions should have at least one category.

    """
    name = Required(str, 40, unique=True)
    questions = Set('Question')


class Question(db.Entity):
    """
    Question objects.

    Multiple answers are separated using "|".

    TODO: Remove questions based on ratings relative to the number
          of times they have been played.

    """
    GET_RANDOM_SQL = """
        SELECT * FROM question
        WHERE active = true
        AND last_played < $round_start
        AND (vote_up - vote_down) > $min_rating
        ORDER BY RANDOM() * (GREATEST(times_solved, 1) / (SELECT SUM(times_solved)+1 FROM question)::float)
        LIMIT 100
    """
    MIN_POINTS = 100
    BASE_POINTS = 500
    MIN_RATING = -3  # Questions with lower rating will not be played
    MIN_PLAYED_ROUNDS = 3
    HINTS_PENALTY = 0.5
    STREAK_MODIFIER = 1.05

    MASK_CHAR = '_'
    COMMON_WORDS = ['the', 'a', 'an', 'and', 'of']

    active = Required(bool, default=False)

    question = Required(str, 200)
    media_url = Optional(str, 500)
    answer = Required(str, 200)

    categories = Set(Category)
    additional_info = Optional(str)

    times_played = Required(int, default=0)
    times_solved = Required(int, default=0)

    vote_up = Required(int, default=0)
    vote_down = Required(int, default=0)

    date_added = Required(datetime, sql_default='CURRENT_TIMESTAMP')
    date_modified = Required(datetime, sql_default='CURRENT_TIMESTAMP')
    last_played = Required(datetime, sql_default='CURRENT_TIMESTAMP')

    rounds = Set('Round')
    reports = Set('Report')
    player = Optional('Player')

    def __str__(self):
        return '{} *** {}'.format(self.question, self.primary_answer)

    @property
    def primary_answer(self):
        return self.answer.split('|')[0]

    @property
    def answer_re(self):
        if not hasattr(self, '_answer_re'):
            answers = map(lambda a: re.escape(a), self.answer.split('|'))
            pattern = r'\b{}\b'.format('|'.join(answers))
            self._answer_re = re.compile(pattern, re.IGNORECASE)
        return self._answer_re

    @property
    def category_names(self):
        if not hasattr(self, '_category_names'):
            with db_session():
                self._category_names = ', '.join([c.name for c in self.categories.order_by(Category.name)])
        return self._category_names

    @property
    def solve_percentage(self):
        if self.times_played == 0:
            return 0
        return self.times_solved / self.times_played * 100

    def check_answer(self, answer):
        return self.answer_re.search(answer) is not None

    def _mask_word(self, word, vowels_fn=None, consonants_fn=None):
        if word.lower() in self.COMMON_WORDS:
            return word

        word_len = len(word)
        masked_word = list(self.MASK_CHAR * word_len)

        vowels = vowels_fn(word_len)
        consonants = consonants_fn(word_len)

        if vowels:
            r = re.compile(r'(?:\b|[^aeiou])([aeiou])', re.I)
            for i, match in enumerate(r.finditer(word)):
                masked_word[match.end() - 1] = match.group(1)
                if i + 1 >= vowels:
                    break
            else:
                # no vowels!
                consonants += 1

        if consonants:
            r = re.compile(r'([^aeiou])', re.I)
            for i, match in enumerate(r.finditer(word)):
                masked_word[match.end() - 1] = match.group(1)
                if i + 1 >= consonants or word_len < 4:
                    break
        return ''.join(masked_word)

    def get_hint(self, num):
        """
        Give some hints about the answer.

        :param num: Hint number from 1 - 3

        """
        answer = self.primary_answer

        if num == 1 and not re.search(r'[^A-Za-z]', answer):
            return "{} letters".format(len(answer))

        words = re.compile(r'\w{2,}').findall(answer)

        def _letters(hint_num, consonants=False):
            base = hint_num - (1 if consonants else 0)
            return lambda l: max(0, base if l > 6 else (base - 1))

        vowels = _letters(num)
        consonants = _letters(num, True)

        hint = answer
        for word in words:
            hint = hint.replace(word, self._mask_word(word, vowels, consonants))
        return "<kbd>{}</kbd>".format(hint)

    def calculate_points(self, time_percentage, hints=0, streak=1):
        """
        Calculate how many points answering this question got someone.

        If a question has been played several times and was never correctly
        answered the possible awarded points for this question will grow
        on a logarithmic scale.

        Furthermore, an ongoing streak of a player will slowly increase
        base awarded points exponentially (winning consecutive rounds, not
        counting unsolved rounds).

        Anything beyond the first hint will also reduce the points
        awarded, as guessing the answer becomes easier with them.

        At last, we'll make sure that even the latest possible answer will
        get a bare minimum amount of points.

        """
        if self.times_played < self.MIN_PLAYED_ROUNDS:
            difficulty_factor = 1
        else:
            difficulty_factor = 0.5
            difficulty_factor += 1 / math.log10(max(self.solve_percentage, 1.1))  # prevent division by zero

        base_points = self.BASE_POINTS * difficulty_factor
        base_points *= self.STREAK_MODIFIER ** (streak - 1)

        penalty = 1
        if hints > 0:
            # first hint does not reduce points
            penalty += (hints - 1) * self.HINTS_PENALTY

        base = max(self.MIN_POINTS, base_points * (1 - time_percentage))
        return int(base / penalty)


class Player(db.Entity):
    """
    A player.

    """
    NAME_MAX_LEN = 40
    BCRYPT_ROUNDS = 11
    PERMISSIONS = [
        '__EVERYTHING__',
        'stop',
        'start',
        'unlock',
        'next',
    ]

    name = Required(str, NAME_MAX_LEN, unique=True)
    password_hash = Optional(str, 200)
    email = Optional(str, 200)
    permissions = Required(int, default=0)

    date_joined = Required(datetime, sql_default='CURRENT_TIMESTAMP')
    last_played = Required(datetime, sql_default='CURRENT_TIMESTAMP')

    rounds_solved = Set('Round')
    submitted_reports = Set('Report')
    submitted_questions = Set(Question)

    def __str__(self):
        return '{} (#{})'.format(self.name, self.id)

    def logged_in(self):
        self.last_played = datetime.now()

    def has_password(self):
        return bool(self.password_hash)

    def set_password(self, password):
        self.password_hash = bcrypt_sha256.encrypt(password, rounds=self.BCRYPT_ROUNDS)

    def check_password(self, password):
        if not self.has_password():
            return True
        if password is None:
            return False
        return bcrypt_sha256.verify(password, self.password_hash)

    def add_perm(self, command):
        try:
            perm = 1 << self.PERMISSIONS.index(command)
        except ValueError:
            return
        self.permissions |= perm

    def remove_perm(self, command):
        try:
            perm = 1 << self.PERMISSIONS.index(command)
        except ValueError:
            return
        self.permissions ^= perm

    def has_perm(self, command):
        try:
            perm = 1 << self.PERMISSIONS.index(command)
        except ValueError:
            return False
        return 1 & self.permissions or perm & self.permissions


class Round(db.Entity):
    """
    A single round with a single question.

    """
    question = Required(Question)
    start_time = Required(datetime, sql_default='CURRENT_TIMESTAMP')

    solved = Required(bool, default=False)
    solver = Optional(Player)
    time_taken = Optional(float)
    points = Required(int, default=0)

    @classmethod
    def new(cls, round_start):
        """
        Select a new random question for a new round.

        """
        question = Question.select_by_sql(Question.GET_RANDOM_SQL, locals={
            'round_start': round_start,
            'min_rating': Question.MIN_RATING,
        })[0]
        return cls(question=question)

    @db_session
    def solved_by(self, player, total_time, hints=0, streak=1):
        self.solved = True
        self.solver = player
        self.time_taken = datetime.now().timestamp() - self.start_time.timestamp()
        self.points = self.question.calculate_points(
            self.time_taken / total_time, hints, streak)

    @db_session
    def end_round(self):
        """
        Update the question statistics after a round.

        """
        self.question.set(
            last_played=datetime.now(),
            times_played=self.question.times_played + 1
        )
        if self.solved:
            self.question.set(
                times_solved=self.question.times_solved + 1
            )


class Report(db.Entity):
    """
    A report for a question.

    """
    question = Required(Question)
    player = Required(Player)
    text = Required(str)
    created = Required(datetime, sql_default='CURRENT_TIMESTAMP')
    done = Required(bool, default=False)
