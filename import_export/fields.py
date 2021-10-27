from __future__ import unicode_literals

import inspect

from django.core.exceptions import ObjectDoesNotExist
from django.db.models.manager import Manager
from django.db.models.fields import NOT_PROVIDED
from django.db.models.fields.related import RelatedField

from . import widgets


class Field:
    """
    Field represent mapping between `object` field and representation of
    this field.

    :param attribute: A string of either an instance attribute or callable off
        the object.

    :param column_name: Lets you provide a name for the column that represents
        this field in the export.

    :param widget: Defines a widget that will be used to represent this
        field's data in the export.

    :param readonly: A Boolean which defines if this field will be ignored
        during import.

    :param default: This value will be returned by
        :meth:`~import_export.fields.Field.clean` if this field's widget did
        not return an adequate value.

    :param saves_null_values: Controls whether null values are saved on the object
    """
    empty_values = [None, '']

    def __init__(self, attribute=None, column_name=None, widget=None,
                 default=NOT_PROVIDED, readonly=False, saves_null_values=True):
        self.attribute = attribute
        self.default = default
        self.column_name = column_name
        if not widget:
            widget = widgets.Widget()
        self.widget = widget
        self.readonly = readonly
        self.saves_null_values = saves_null_values

    def __repr__(self):
        """
        Displays the module, class and name of the field.
        """
        path = '%s.%s' % (self.__class__.__module__, self.__class__.__name__)
        column_name = getattr(self, 'column_name', None)
        if column_name is not None:
            return '<%s: %s>' % (path, column_name)
        return '<%s>' % path

    def clean(self, data, **kwargs):
        """
        Translates the value stored in the imported datasource to an
        appropriate Python object and returns it.
        """
        try:
            value = data[self.column_name]
        except KeyError:
            raise KeyError("Column '%s' not found in dataset. Available "
                           "columns are: %s" % (self.column_name, list(data)))

        # If ValueError is raised here, import_obj() will handle it
        value = self.widget.clean(value, row=data, **kwargs)

        if value in self.empty_values and self.default != NOT_PROVIDED:
            if callable(self.default):
                return self.default()
            return self.default

        return value

    def get_value(self, obj):
        """
        Returns the value of the object's attribute.
        """
        if self.attribute is None:
            return None

        attrs = self.attribute.split('__')
        value = obj

        for attr in attrs:
            try:
                #if the field is related we pass the id as value instead of querying the database
                if self.is_related_field(value):
                    field = obj._meta.get_field(self.column_name)
                    primary_key_name = Field.get_first_superclass_pk_alias(field.related_model)
                    value = getattr(value, "%s_%s" % (attr, primary_key_name), None)
                else:
                    value = getattr(value, attr, None)
            except (ValueError, ObjectDoesNotExist):
                # needs to have a primary key value before a many-to-many
                # relationship can be used.
                return None
            if value is None:
                return None

        # RelatedManager and ManyRelatedManager classes are callable in
        # Django >= 1.7 but we don't want to call them
        if callable(value) and not isinstance(value, Manager):
            value = value()
        return value

    def is_related_field(self, obj):
        attrs = self.attribute.split('__')
        # doesn't work on complicated query fields
        if len(attrs) != 1:
            return False
        field = obj._meta.get_field(attrs[0])
        return isinstance(field, RelatedField)

    def save(self, obj, data, is_m2m=False, **kwargs):
        """
        If this field is not declared readonly, the object's attribute will
        be set to the value returned by :meth:`~import_export.fields.Field.clean`.
        """
        if not self.readonly:
            attrs = self.attribute.split('__')
            for attr in attrs[:-1]:
                obj = getattr(obj, attr, None)
            cleaned = self.clean(data, **kwargs)
            if cleaned is not None or self.saves_null_values:
                if not is_m2m:
                    setattr(obj, attrs[-1], cleaned)
                else:
                    getattr(obj, attrs[-1]).set(cleaned)

    def export(self, obj):
        """
        Returns value from the provided object converted to export
        representation.
        """
        value = self.get_value(obj)
        if value is None:
            return ""
        elif self.is_related_field(obj):    # if related field the id is passes as is
            return value
        return self.widget.render(value, obj)

    @staticmethod
    def get_first_superclass_pk_alias(model_class):
        superclasses_list = inspect.getmro(model_class)
        for sc in superclasses_list:
            if hasattr(sc, '_meta') and sc._meta.pk is not None:
                pk = sc._meta.pk.name

        return pk
