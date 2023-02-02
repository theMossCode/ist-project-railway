
from pymongo import MongoClient
from django.conf import settings

mongodb_client = MongoClient(settings.MONGODB_CONNECTION_URI)


def get_db_name(user):
    return f"{user.username}_{user.id}_db"

