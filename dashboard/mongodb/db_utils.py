import logging
import datetime

import pymongo

from . import mongodb_client


def get_database(db_name):
    return mongodb_client[str(db_name)]


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
    logging.debug("Add data object")

    db = get_database(project.db_name)
    project_col = db[get_project_collection_name(project)]
    values_obj = dict()
    for key, value in data["values"].items():
        values_obj[f"{key}"] = value

    data_object = {
        "timestamp": data["time"].timestamp(),
        "value": values_obj,
    }

    doc_filters = {
        "topic": topic.pk,
        "date": data["time"].toordinal()
    }
    data_query = {
        "$push": {
            "values": data_object,
        },
    }

    res = project_col.update_one(doc_filters, data_query, upsert=True)
    logging.debug(f"Add data res: {res.acknowledged}")
    return res


def get_data_objects(project, topic):
    """
    Get data objects
    @param project: project
    @param topic: topic
    @return: values list
    """
    logging.debug(f"Get data objects {project.name}, {topic.name}")
    db = get_database(project.db_name)
    project_col = db[get_project_collection_name(project)]
    doc_filter = {
        "topic": topic.pk,
        "date": datetime.datetime.utcnow().toordinal(),
    }

    # Sort array
    sort_res = project_col.update_one(
        doc_filter,
        {
            "$push": {
                "values": {
                    "$each": [],
                    "$sort": {"timestamp": pymongo.DESCENDING}
                }
            }
        }
    )

    logging.debug(f"Sort res {sort_res.acknowledged}")
    values_list = list()
    try:
        for _obj in project_col.find(doc_filter):
            for value in _obj["values"]:
                values_list.append(value)
            return values_list
    except Exception as e:
        logging.exception(e)
        return None


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

