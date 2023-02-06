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
from channels.layers import get_channel_layer

channel_layer = get_channel_layer()

class MessageParserMixin:
    def get_topic_info_from_message(self, message, project):
        topics = Topic.objects.filter(project=project)
        topic_info_list = list()
        for topic in topics:
            if "#" in topic.path:
                i = topic.path.index("#")
                obj_path = message.topic[i:]
                if str(message.topic).startswith(topic.path[:-1]):
                    topic_info = {
                        "obj_path": obj_path,
                        "topic": topic
                    }
                    topic_info_list.append(topic_info)

            elif message.topic == topic.path:
                topic_info = {
                    "topic": topic,
                }
                topic_info_list.append(topic_info)

        return topic_info_list

    def create_mongodb_data_object(self, topic, raw_data, obj_path=None):
        try:
            processed_data = json.loads(raw_data)
        except json.JSONDecodeError:
            processed_data = raw_data.decode()

        data_objects = DataObject.objects.filter(topic=topic)
        mongodb_data_obj = dict()
        for data_object in data_objects:
            value = self.get_dataobject_value_from_data(data_object, processed_data)
            if not obj_path:
                if value:
                    mongodb_data_obj[f"{data_object.pk}"] = value
            else:
                if data_object.path != obj_path:
                    continue

                if value:
                    mongodb_data_obj[f"{data_object.pk}"] = value

        return mongodb_data_obj


    def get_dataobject_value_from_data(self, data_object, data):
        if data_object.format == data_object.FORMAT_CHOICE_JSON:
            try:
                value = data[f"{data_object.key}"]
            except KeyError:
                logging.debug(f"Key error {data_object.key} not in {data}")
                return None
        elif data_object.format == data_object.FORMAT_CHOICE_SINGLE_VARIABLE:
            value = data

        if value:
            if data_object.data_type == data_object.DATA_TYPE_NUMBER:
                try:
                    value = float(value)
                    return value
                except TypeError:
                    logging.debug(f"{value} not a number")
            elif data_object.data_type == data_object.DATA_TYPE_STRING:
                return str(value)
            elif data_object.data_type == data_object.DATA_TYPE_LOCATION:
                #TODO location object
                pass
            elif data_object.data_type == data_object.DATA_TYPE_BOOLEAN:
                if isinstance(value, bool):
                    return value

        return None


class MQTTClient(MessageParserMixin, client.Client):
    """
    MQTT Client class, new object created each time a project is created.
    """
    def __init__(self, project_id, host, port, userdata=None):
        super().__init__(client_id=str(project_id), userdata=userdata)
        self.id = project_id
        self.host = host
        self.port = port
        self.connected = False

        #callbacks
        self.on_connect = self._connected
        self.on_disconnect = self._disconnected
        self.on_message = self._message_received
        self.on_subscribe = self._subscribed
        self.on_publish = self._published

        # DB save thread pool
        self.msg_rec_threadpool = concurrent.futures.ThreadPoolExecutor()

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
        await sync_to_async(self.disconnect)()

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
        self.connected = True
        if len(topics) <= 0:
            return

        try:
            async_to_sync(channel_layer.group_send)(
                f"project_{self.id}", {
                    "type": "broker.connection.updated",
                    "connection": 1,
                }
            )
        except RuntimeError as e:
            logging.debug("Channel layers error")

        with concurrent.futures.ThreadPoolExecutor() as pool:
            futures = [pool.submit(
                async_to_sync(self.subscribe_topic), topic.path, topic.qos,
            ) for topic in topics]

    # Disconnected callback
    def _disconnected(self, client_ptr, userdata, rc):
        logging.debug("disconnected {}".format(self.host))
        try:
            async_to_sync(channel_layer.group_send)(
                f"project_{self.id}", {
                    "type": "broker.connection.updated",
                    "connection": 0,
                }
            )
        except RuntimeError:
            logging.debug("Channel layers error")

        self.connected = False

    # Message received callback
    def _message_received(self, client_ptr, userdata, message):
        fut = self.msg_rec_threadpool.submit(self.__process_message, message)

    def __process_message(self, message):
        now = datetime.datetime.utcnow()
        try:
            project = Project.objects.get(pk=self.id)
        except django.db.models.ObjectDoesNotExist:
            logging.debug("Project not found")
            return

        topics_info = self.get_topic_info_from_message(message, project)
        for topic_info in topics_info:
            try:
                topic = topic_info["topic"]
            except KeyError:
                logging.debug("Key error!")
                continue

            obj_path = topic_info.get("obj_path", None)
            mongodb_obj = self.create_mongodb_data_object(topic, message.payload, obj_path)
            if mongodb_obj:
                db_utils.add_data_obj(project, topic, {"time": now, "values": mongodb_obj})

    def __process_message_loop(self):
        logging.debug("message thread")
        try:
            while 1:
                for fut in self.msg_parse_futures:
                    res = async_to_sync(fut.result())
                    self.msg_parse_futures.remove(fut)
        except KeyboardInterrupt:
            return

    # Topic subscribed callback
    def _subscribed(self, client_ptr, userdata, mid, granted_qos):
        logging.debug("Topic subscribed on client {}".format(self.host))
        # TODO update (UI)

    # Message published callback
    def _published(self, client_ptr, userdata, mid):
        logging.debug("Message published by client {}".format(self.host))


class MQTTClientManager:
    """
    MQTT Client manager
    """
    client_list = list()

    def get_client_count(self):
        return len(self.client_list)

    def get_client(self, client_id):
        for temp_client in self.client_list:
            # logging.debug(temp_client.id)
            if temp_client.id == client_id:
                return temp_client

        return None

    def refresh_clients(self):
        for _client in self.client_list:
            if not _client.connected:
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
            return True

        return False

    def disconnect_client(self, client_id):
        temp_client = self.get_client(client_id)
        if temp_client:
            async_to_sync(temp_client.disconnect_broker)()
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



