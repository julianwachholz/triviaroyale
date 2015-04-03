import datetime
import logging
import types

from pony.orm import db_session, desc

from flask_admin.model import BaseModelView, typefmt
from wtforms import Form, fields


logger = logging.getLogger(__name__)


class ModelView(BaseModelView):
    """
    ModelView for PonyORM.

    Usage:

        admin = Admin()
        admin.add_view(ModelView(MyModel))

    """
    column_default_sort = 'pk'

    column_type_formatters = {
        datetime.datetime: lambda v, dt: dt.strftime('%c'),
        types.MethodType: lambda v, fun: fun(),
        bool: typefmt.bool_formatter,
    }

    def _get_fields(self):
        for attr in self.model._new_attrs_:
            if not attr.is_collection:
                yield attr

    def _get_prefetch_fields(self):
        for attr in self.model._new_attrs_:
            if attr.is_relation and not attr.is_collection:
                yield attr

    def get_pk_value(self, model):
        return self.model.get_pk(model)

    def scaffold_list_columns(self):
        columns = []
        for attr in self._get_fields():
            columns.append(attr.name)
        return columns

    def scaffold_sortable_columns(self):
        return self.scaffold_list_columns()

    def init_search(self):
        return False

    def scaffold_form(self):
        class ModelForm(Form):
            pass
        for attr in self._get_fields():
            setattr(ModelForm, attr.name, fields.StringField(attr.name))
        return ModelForm

    @db_session
    def get_list(self, page, sort_column, sort_desc, search, filters, execute=True):
        query = self.model.select()

        num = query.count()

        if sort_column is not None:
            sort_column = getattr(self.model, sort_column)
            if sort_desc:
                query = query.order_by(desc(sort_column))
            else:
                query = query.order_by(sort_column)

        query = query.prefetch(*self._get_prefetch_fields())

        if page is not None:
            query = query.page(page + 1, self.page_size)

        return num, query

    @db_session
    def get_one(self, id):
        return self.model[id]
