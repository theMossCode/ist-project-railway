import logging
import datetime
import pprint

import pymongo
from pymongo import MongoClient, results
from django.conf import settings


def get_database(db_name):
    client = MongoClient(settings.MONGO_DB_CONNECTION_STR)
    return client[str(db_name)]


def get_db_name(user):
    return "{}_{}_db".format(str(user.username), str(user.id))


def get_project_collection_name(project):
    return "{}_{}".format(str(project.name).replace(" ", "_"), project.id)


def add_document(collection, document):
    collection.insert_one(document)


def get_document(collection, topic):
    aggregation = [
        {"$match": {"date": datetime.date.today()}},
        {"$match": {"topic": "{}".format(topic.id)}},
    ]

    try:
        doc = collection.aggregate(aggregation)
        return doc
    except Exception as e:
        logging.debug(e)
        return None


async def add_data_obj(project, topic, data):
    logging.debug("Add data object topic: {}, data {}".format(topic.name, data))
    time = datetime.datetime.utcnow()
    date = time.today().toordinal()

    db = get_database(project.db_name)
    collection = db[get_project_collection_name(project)]
    value_obj = dict()
    for key, value in data.items():
        value_obj[str(key)] = value

    data_obj = {
        "timestamp": time.timestamp(),
        "value": value_obj
    }
    doc_filters = {
        "topic": topic.id,
        "date": date,
    }
    data_query = {
        "$push": {"values": data_obj}
    }

    res = collection.update_one(doc_filters, data_query, upsert=True)
    return res


def get_data_objects(project, topic):
    """
    Get data objects
    @param project: project
    @param topic: topic
    @return: values list
    """
    db = get_database(project.db_name)
    collection = db[get_project_collection_name(project)]
    doc_filter = {
        "topic": topic.pk,
        "date": datetime.date.today().toordinal()
    }
    values_list = list()
    try:
        cursor = collection.find(doc_filter)
        for mongo_obj in cursor:
            for value_obj in mongo_obj["values"]:
                values_list.append(value_obj)

        return values_list
    except Exception as e:
        logging.debug(e)
        return values_list


def delete_project_collection(project):
    db = get_database(project.db_name)
    collection = db[get_project_collection_name(project)]
    try:
        collection.drop()
        return True
    except Exception as e:
        logging.debug("Drop collection exception {}".format(e))
        return False


def delete_topic_documents(project, topic):
    db = get_database(project.db_name)
    collection = db[get_project_collection_name(project)]
    doc_filter = {
        "topic": topic.pk,
    }
    try:
        res = collection.delete_many(filter=doc_filter)
        return res.acknowledged
    except Exception as e:
        logging.debug(e)
        return None


def delete_dataobject(project, topic, dataobject):
    db = get_database(project.db_name)
    collection = db[get_project_collection_name(project)]
    doc_filter = {
        "topic": topic.pk,
    }
    query = {
        "$unset": {"values.$[].{}" : {"$exists": True}}
    }
    try:
        res = collection.update_many(doc_filter, query)
        return res.acknowledged
    except Exception as e:
        logging.debug("Update dataobject exception {}".format(e))
        return None

