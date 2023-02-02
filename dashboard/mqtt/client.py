import asyncio
import datetime
import logging
import json
import threading
import concurrent.futures

import django.db.models
from paho.mqtt import client
from ..models import Project, Topic, DataObject
from ..mongodb import db_utils
from asgiref.sync import async_to_sync, sync_to_async


class MQTTClient(client.Client):
    """
    MQTT Client class, new object created each time a project is created.
    """
    def __init__(self, project_id, host, port, userdata=None):
        super().__init__(client_id=str(project_id), userdata=userdata)
        self.id = project_id
        self.host = host
        self.port = port

        #callbacks
        self.on_connect = self._connected
        self.on_disconnect = self._disconnected
        self.on_message = self._message_received
        self.on_subscribe = self._subscribed
        self.on_publish = self._published

        # Start db save thread
        self.message_queue = list()
        self.db_thread_msg_received_event = threading.Event()
        self.db_thread = threading.Thread(target=self._update_db_thread_fun)
        self.db_thread.daemon = True
        self.db_thread.start()

    async def connect_broker(self):
        """
        Connect to client server asynchronously
        :param host: host string
        :param port: port (default 1883)
        """
        logging.debug("Connect {}".format(self.host))
        self.connect_async(host=self.host, port=self.port)

    async def disconnect_broker(self, reason=None):
        """
        Disconnect server \n
        :param reason: disconnect reason
        """
        self.disconnect()

    async def subscribe_topic(self, topic, qos=2):
        """
        Subscribe to topic \n
        :param topic: topic string
        :param qos: qos(int)
        :return: True if subscribe request was sent successfully
        """
        logging.debug(f"Subscribe {topic} on {self.host}. QOS: {qos}")
        res = await sync_to_async(self.subscribe)(topic=topic, qos=int(qos))
        if res[0] == client.MQTT_ERR_SUCCESS:
            return True

        return False

    async def unsubscribe_topic(self, topic):
        res = await sync_to_async(self.unsubscribe)(topic)
        if res[0] == client.MQTT_ERR_SUCCESS:
            logging.debug("Unsubscribe topic {}".format(topic))
            return True

        return False

    # Publish to topic
    async def publish_to_topic(self, topic, payload, qos=0):
        logging.debug("Publish (payload: {})".format(payload))
        res = await sync_to_async(self.publish)(topic, payload, qos)
        if res.rc != client.MQTT_ERR_SUCCESS:
            return False

        return True

    # Connected callback
    def _connected(self, client_ptr, userdata, flags, rc):
        logging.debug("Connected {}".format(self.host))
        project = Project.objects.get(pk=self.id)
        topics = Topic.objects.filter(project=project)
        if len(topics) <= 0:
            return

        with concurrent.futures.ThreadPoolExecutor() as pool:
            futures = [pool.submit(
                async_to_sync(self.subscribe_topic), topic.path, topic.qos,
            ) for topic in topics]

            for f in concurrent.futures.as_completed(futures):
                logging.debug(f.result())


    # Disconnected callback
    def _disconnected(self, client_ptr, userdata, rc):
        logging.debug("disconnected {}".format(self.host))

    # Message received callback
    def _message_received(self, client_ptr, userdata, message):
        try:
            project = Project.objects.get(pk=self.id)
            topic, is_wildcard_topic, wild_card_sub_topic_path = self._get_message_topic(message, project)
            if not topic:
                logging.error("Topic not valid")
                return

            # logging.debug(f"Message received\r\n{message.payload}")
            mongodb_data = self._create_mongo_db_data(topic, message.payload, is_wildcard_topic,
                                                      wild_card_sub_topic_path)

            if mongodb_data:
                logging.debug("Has data")
                message = {
                    "topic_id": topic.pk,
                    "message": {
                        "time": datetime.datetime.utcnow(),
                        "values": mongodb_data
                    }
                }
                self.message_queue.append(message)
                self.db_thread_msg_received_event.set()
                # self.db_thread_event_loop.run_until_complete(async_mongodb.add_data_object(project, topic, message["message"]))
        except Exception as e:
            logging.error(e)

    # Topic subscribed callback
    def _subscribed(self, client_ptr, userdata, mid, granted_qos):
        logging.debug("Topic subscribed on client {}".format(self.host))
        # TODO update (UI)

    # Message published callback
    def _published(self, client_ptr, userdata, mid):
        logging.debug("Message published by client {}".format(self.host))

    def _get_message_topic(self, message, project):
        topic_query = Topic.objects.filter(project=project)
        for _topic in topic_query:
            if "#" in _topic.path:
                wildcard_index = str(_topic.path).index("#")
                topic_path = str(_topic.path)[:(wildcard_index - 1)]
                if str(message.topic).startswith(topic_path):
                    is_wildcard_topic = True
                    wild_card_sub_topic_path = str(message.topic)[wildcard_index:]
                    return _topic, is_wildcard_topic, wild_card_sub_topic_path
            elif str(message.topic).startswith(_topic.path):
                return _topic, False, None

        return None

    def _create_mongo_db_data(self, topic, data, is_wildcard_topic=False, wildcard_sub_path=None):
        try:
            processed_data = json.loads(data)
        except Exception as e:
            logging.error(e)
            processed_data = data.decode()

        mongodb_data = dict()
        data_objects = DataObject.objects.filter(topic=topic)
        for data_object in data_objects:
            object_value = self._get_data_value(data_object, processed_data)
            if not is_wildcard_topic:
                if object_value:
                    mongodb_data[str(data_object.id)] = object_value
            else:
                if data_object.path is None and len(wildcard_sub_path) > 0:
                    continue
                elif data_object.path != wildcard_sub_path:
                    continue

                if object_value:
                    mongodb_data[str(data_object.id)] = object_value

        return mongodb_data

    def _get_data_value(self, data_object, data):
        raw_data = None
        if data_object.format == data_object.FORMAT_CHOICE_JSON:
            try:
                if data_object.key in data.keys():
                    raw_data = data[str(data_object.key)]
            except Exception as e:
                logging.error(e)
                return None
        elif data_object.format == data_object.FORMAT_CHOICE_SINGLE_VARIABLE:
            raw_data = data

        if raw_data:
            try:
                if data_object.data_type == data_object.DATA_TYPE_NUMBER:
                    if isinstance(raw_data, int) or isinstance(raw_data, float):
                        return raw_data
                elif data_object.data_type == data_object.DATA_TYPE_STRING:
                    return str(raw_data)
                elif data_object.data_type == data_object.DATA_TYPE_LOCATION:
                    #TODO location object
                    pass
                elif data_object.data_type == data_object.DATA_TYPE_BOOLEAN:
                    if isinstance(raw_data, bool):
                        return raw_data
            except Exception as e:
                logging.exception(e)
                return None

        return None

    def _update_db_thread_fun(self):
        logging.debug("Start db thread")
        try:
            while True:
                self.db_thread_msg_received_event.wait()
                t_fut = list()
                for _ in range(len(self.message_queue)):
                    message = self.message_queue.pop()
                    try:
                        project = Project.objects.get(pk=self.id)
                        topic = Topic.objects.get(pk=message["topic_id"])
                    except django.db.models.ObjectDoesNotExist:
                        logging.error("Project or topic does not exist")
                        continue

                    mongodb_msg = message["message"]
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        fut = pool.submit(
                            async_to_sync(db_utils.add_data_obj), project, topic, mongodb_msg
                        )

                        res = fut.result()
                        logging.debug(res)

                self.db_thread_msg_received_event.clear()

        except KeyboardInterrupt:
            logging.debug("Keyboard interrupt, Stop thread")
            self.db_thread.stop()


class MQTTClientManager:
    client_list = list()

    def get_client_count(self):
        return len(self.client_list)

    def get_client(self, client_id):
        logging.debug(self.client_list)
        for temp_client in self.client_list:
            logging.debug(temp_client.id)
            if temp_client.id == client_id:
                return temp_client

        return None

    def refresh_clients(self):
        for _client in self.client_list:
            if not _client.is_connected():
                self.connect_client(_client.id)
                self.start_client(_client.id)

    def add_client(self, client_id, host, port=1883, userdata=None):
        logging.debug(f"Add client {client_id}, {host}")
        temp_client = MQTTClient(client_id, host, port, userdata)
        self.client_list.append(temp_client)

    def connect_client(self, client_id):
        temp_client = self.get_client(client_id)
        if temp_client:
            logging.debug(f"Connect: {temp_client.host}")
            temp_client.connect_async(host=temp_client.host, port=temp_client.port)
            return True

        return False

    def start_client(self, client_id):
        temp_client = self.get_client(client_id)
        if temp_client:
            temp_client.loop_start()
            logging.debug(f"active threads : {threading.active_count()}")
            return True

        return False

    def disconnect_client(self, client_id):
        temp_client = self.get_client(client_id)
        if temp_client:
            temp_client.disconnect_broker()
            temp_client.loop_stop()
            return True

        return False

    def delete_client(self, client_id):
        _client = self.get_client(client_id)
        if _client:
            self.disconnect_client(client_id)
            self.client_list.remove(_client)
            return True

        return False



