from __future__ import unicode_literals
from django.db import models
from django.conf import settings
from django.core import serializers
from django.core.exceptions import ObjectDoesNotExist


class SerializedObjectField(models.TextField):
    '''Model field that stores serialized value of model class instance
       and returns deserialized model instance

       >>> from django.db import models
       >>> import SerializedObjectField

       >>> class A(models.Model):
               object = SerializedObjectField(serialize_format='json')

       >>> class B(models.Model):
               field = models.CharField(max_length=10)
       >>> b = B(field='test')
       >>> b.save()
       >>> a = A()
       >>> a.object = b
       >>> a.save()
       >>> a = A.object.get(pk=1)
       >>> a.object
       <B: B object>
       >>> a.object.__dict__
       {'field': 'test', 'id': 1}

    '''

    def __init__(self, serialize_format='json', *args, **kwargs):
        self.serialize_format = serialize_format
        super(SerializedObjectField, self).__init__(*args, **kwargs)

    def _serialize(self, value):
        if not value:
            return ''
        value_set = [value]
        opts = value._meta.concrete_model._meta

        if value._meta.parents:
            value_set += [getattr(value, f.name)
                          for f in list(value._meta.parents.values())
                          if f is not None]

        value_set += (field.name for field in opts.local_fields + opts.local_many_to_many)
        return serializers.serialize(self.serialize_format, (value,), fields=value_set)

    def _deserialize(self, value):
        from django.utils.encoding import force_text
        obj_generator = list(serializers.deserialize(
            "json",
            force_text(value.encode("utf-8")),
            ignorenonexistent=True))[0]

        # for parent in obj_generator:
        #     opts = value._meta.concrete_model._meta
        #     value_set = (field.name for field in opts.local_fields + opts.local_many_to_many)
        result = {}

        obj = obj_generator.object
        for field in obj._meta.fields:
            result[field.name] = field.value_from_object(obj)
        # result.update(obj_generator.m2m_data)

        for field, value in result.iteritems():
            try:
                setattr(obj, field, value)
            except ValueError:
                setattr(obj, field+"id", value)


        for parent_class, field in obj._meta.concrete_model._meta.parents.items():
            if obj._meta.proxy and parent_class == obj._meta.concrete_model:
                continue
            content_type = ContentType.objects.get_for_model(parent_class)
            if field:
                parent_id = force_text(getattr(obj, field.attname))
            else:
                parent_id = obj.pk
            # for f in parent.object._meta.fields+value_set:
            #     try:
            #         setattr(obj, f.name, getattr(parent.object, f.name))
            #     except ObjectDoesNotExist:
            #         try:
            #             # Try to set non-existant foreign key reference to None
            #             setattr(obj, f.name, None)
            #         except ValueError:
            #             # Return None for changed_object if None not allowed
            #             return None
        return obj

    def db_type(self, connection=None):
        return 'text'

    def pre_save(self, model_instance, add):
        value = getattr(model_instance, self.attname, None)
        return self._serialize(value)

    def contribute_to_class(self, cls, name):
        self.class_name = cls
        super(SerializedObjectField, self).contribute_to_class(cls, name)
        models.signals.post_init.connect(self.post_init)

    def post_init(self, **kwargs):
        if 'sender' in kwargs and 'instance' in kwargs:
            sender = kwargs['sender']
            if (sender == self.class_name or sender._meta.proxy
                and issubclass(sender, self.class_name)) and\
               hasattr(kwargs['instance'], self.attname):
                value = self.value_from_object(kwargs['instance'])

                if value:
                    setattr(kwargs['instance'], self.attname,
                            self._deserialize(value))
                    # setattr(kwargs['instance'], self.attname, data.object)
                    # setattr(kwargs['instance'], 'm2m_data', data.m2m_data)
                else:
                    setattr(kwargs['instance'], self.attname, None)


try:
    from south.modelsinspector import add_introspection_rules

    add_introspection_rules(
        [
            (
                [SerializedObjectField],  # Class(es) these apply to
                [],  # Positional arguments (not used)
                {  # Keyword argument
                    "serialize_format": [
                        "serialize_format",
                        {"default": "json"}],
                },
            ),
        ],
        ["^moderation\.fields\.SerializedObjectField"]
    )
except ImportError:
    pass
