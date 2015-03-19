# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from wtforms import Form, TextField, BooleanField, SelectMultipleField, \
    validators, widgets

from trivia.models import *


class MultiCheckboxField(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()


class CategoryForm(Form):
    name = TextField('Name', [validators.Length(min=2, max=25)])

    def get_data(self):
        return {
            'name': self.name.data,
        }


class QuestionForm(Form):
    question = TextField('Question', [validators.Length(min=10, max=140)])
    answer = TextField('Answer', [validators.Length(min=2, max=40)])
    active = BooleanField('Is active?')

    category_list = MultiCheckboxField('Categories', [validators.DataRequired()], coerce=int)

    def __init__(self, *args, **kwargs):
        super(QuestionForm, self).__init__(*args, **kwargs)
        self.category_list.choices = select((c.id, c.name) for c in Category)[:]

    def get_data(self):
        return {
            'question': self.question.data,
            'answer': self.answer.data,
            'active': self.active.data,
            'categories': [Category[id] for id in self.category_list.data]
        }
