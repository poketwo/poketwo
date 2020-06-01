from mongoengine import *


class Member(Document):
    id = LongField(primary_key=True)
    pokemon = EmbeddedDocumentListField(default=list, required=True)


class Pokemon(EmbeddedDocument):
    number = SequenceField()
    species = IntField(min_value=1, max_value=807, required=True)

    level = IntField(min_value=1, max_value=100, required=True)
    xp = IntField(min_value=0, required=True)

    nature = StringField(required=True)
    iv_hp = IntField(min_value=0, max_value=31, required=True)
    iv_atk = IntField(min_value=0, max_value=31, required=True)
    iv_def = IntField(min_value=0, max_value=31, required=True)
    iv_spatk = IntField(min_value=0, max_value=31, required=True)
    iv_spdef = IntField(min_value=0, max_value=31, required=True)
    iv_spd = IntField(min_value=0, max_value=31, required=True)
