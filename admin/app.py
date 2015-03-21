# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division

import os
import math
import logging

from flask import Flask, flash, request, redirect, url_for, render_template

from trivia.models import *

from forms import CategoryForm, QuestionForm, PlayerForm


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'secret!'


@app.route('/')
def index():
    return render_template('index.html')


def make_admin(name, model, form_class, query, get_form_kwargs=None, count_query=None):
    if get_form_kwargs is None:
        get_form_kwargs = lambda obj: {}

    @app.route('/{}/'.format(name), endpoint='{}_list'.format(name))
    @db_session
    def model_list():
        page = int(request.args.get('p', 1))
        if page < 1:
            page = 1
        pagesize = 100

        objects = query()
        object_count = count(count_query() if count_query else objects)

        return render_template(
            '{}/list.html'.format(name),
            page=page,
            pages=int(math.ceil(object_count / pagesize)),
            **{
                '{}_list'.format(name): objects.page(page, pagesize),
                '{}_count'.format(name): object_count,
            }
        )

    @app.route('/{}/create/'.format(name), endpoint='{}_form'.format(name), methods=['GET', 'POST'])
    @app.route('/{}/<int:id>/'.format(name), endpoint='{}_form'.format(name), methods=['GET', 'POST'])
    @db_session
    def model_form(id=None):
        object = None
        if id:
            object = model[id]

        form_kwargs = get_form_kwargs(object)
        form_kwargs.update({
            'obj': object,
        })
        form = form_class(request.form, **form_kwargs)

        if request.method == 'POST' and form.validate():
            if object:
                object.set(**form.get_data())
                flash('{} updated!'.format(name.title()), 'success')
            else:
                model(**form.get_data())
                flash('{} created!'.format(name.title()), 'success')
            return redirect('/{}/'.format(name))

        return render_template(
            '{}/form.html'.format(name),
            form=form,
            **{name: object}
        )

    @app.route('/{}/<int:id>/delete/'.format(name), endpoint='{}_delete'.format(name), methods=['GET', 'POST'])
    @db_session
    def model_delete(id):
        object = model[id]

        if request.method == 'POST':
            object.delete()
            flash('{} deleted!'.format(name.title()), 'info')
            return redirect('/{}/'.format(name))

        return render_template(
            '{}/confirm_delete.html'.format(name),
            **{name: object}
        )

make_admin(
    name='category',
    model=Category,
    form_class=CategoryForm,
    query=lambda: select((c.id, c.name, count(c.questions)) for c in Category),
    count_query=lambda: select(c for c in Category)
)


def get_question_form_kwargs(obj):
    if not obj:
        return {}
    return {
        'category_list': [c.id for c in obj.categories],
    }

make_admin(
    name='question',
    model=Question,
    form_class=QuestionForm,
    query=lambda: select(q for q in Question),
    get_form_kwargs=get_question_form_kwargs
)


make_admin(
    name='player',
    model=Player,
    form_class=PlayerForm,
    query=lambda: select(p for p in Player),
)


if __name__ == '__main__':
    db.bind('postgres', database='trivia')
    db.generate_mapping(create_tables=True)
    app.run(debug=True, port=8081)
