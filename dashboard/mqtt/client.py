import asyncio
import logging
import json
import threading
import concurrent.futures

from paho.mqtt import client
from ..models import Project, Topic, DataObject
from ..mongodb import db_utils as mongodb_utils
from asgiref.sync import async_to_sync, sync_to_async
from channels.layers import get_channel_layer

"""
List to store active MQTT client objects
"""
mqtt_clients_list = list()
# channel_layer = get_channel_layer()


class MQTTClient(client.Client):
    """
    MQTT Client class, new object created each time a project is created.
    """
    def __init__(self, project_id):
        super().__init__()
        self.id = project_id
        self.on_connect = self._connected
        self.on_disconnect = self._disconnected
        self.on_message = self._message_received
        self.on_subscribe = self._subscribed
        self.on_publish = self._published
        self.message_queue = list()

        # Start db save thread
        self.db_thread_msg_received_event = threading.Event()
        self.db_thread = threading.Thread(target=self.update_db_thread_fun)
        self.db_thread.daemon = True
        self.db_thread.start()

    # Start asynchronous connection
    # Also calls loops start
    def connect_server(self, host, port):
        """
        Connect to client server asynchronously, also calls loops start
        :param host: host string
        :param port: port (default 1883)
        """
        logging.debug("Connect {}".format(host))
        self.connect_async(host=host, port=port)
        self.loop_start()
        return True

    async def disconnect_server(self, reason=None):
        """
        Disconnect server \n
        :param reason: disconnect reason
        """
        self.disconnect()

    def subscribe_topic(self, topic, qos=2):
        """
        Subscribe to topic \n
        :param topic: topic string
        :param qos: qos(int)
        :return: True if subscribe request was sent successfully
        """
        res = self.subscribe(topic=topic, qos=qos)
        if res[0] == client.MQTT_ERR_SUCCESS:
            return True

        return False

    def unsubscribe_topic(self, topic):
        res = self.unsubscribe(topic)
        if res[0] == client.MQTT_ERR_SUCCESS:
            logging.debug("Unsubscribe topic {}".format(topic))
            return True

        return False

    # Publish to topic
    def publish_to_topic(self, topic, payload, qos=0):
        logging.debug("Publish (payload: {})".format(payload))
        res = self.publish(topic, payload, qos)
        if res.rc != client.MQTT_ERR_SUCCESS:
            return False

        return True

    def update_db_thread_fun(self):
        logging.debug("Start db thread")
        try:
            while True:
                self.db_thread_msg_received_event.wait()
                futures = list()
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    for _ in range(len(self.message_queue)):
                        message = self.message_queue.pop()
                        project = Project.objects.get(pk=self.id)
                        topic = Topic.objects.get(pk=message["topic_id"])
                        mongodb_msg = message["message"]
                        if (not project) or (not topic):
                            logging.error("project or topic not valid")
                            continue

                        # Don't know why async to sync is needed, but its the only wait it works for now
                        save_thread = threading.Thread(target=async_to_sync(mongodb_utils.add_data_obj),
                                                       args=[project, topic, mongodb_msg])
                        save_thread.start()

        except KeyboardInterrupt:
            logging.debug("Keyboard interrupt, Stop thread")
            self.db_thread.stop()

    # Connected callback
    def _connected(self, client_ptr, userdata, flags, rc):
        project = Project.objects.get(pk=self.id)
        if project is not None:
            project.connected = True
            project.save()
            topics = Topic.objects.filter(project=project)

            for topic in topics:
                async_to_sync(get_channel_layer().send)(
                    "mqtt", {
                        "type": "client.subscribe.topic",
                        "project_id": project.id,
                        "topic_id": topic.id
                    }
                )
            logging.debug("Connected {}: Status: {}".format(project.name, project.connected))
        else:
            logging.debug("No project found")

    # Disconnected callback
    def _disconnected(self, client_ptr, userdata, rc):
        logging.debug("disconnected {}".format(self.id))
        project = Project.objects.get(pk=self.id)
        project.is_connected = False
        project.save()

    # Message received callback
    def _message_received(self, client_ptr, userdata, message):
        try:
            project = Project.objects.get(pk=self.id)
            topic, is_wildcard_topic, wild_card_sub_topic_path = self._get_message_topic(message, project)
            if not topic:
                logging.error("Not valid topic")
                return

            # logging.debug("message received on client: {}, topic: {}\r\n<msg> {}".format(
            #     project.name, str(message.topic), str(message.payload))
            # )

            mongodb_data = self._create_mongo_db_data(topic, message.payload, is_wildcard_topic,
                                                      wild_card_sub_topic_path)

            message = {
                "topic_id": topic.pk,
                "message": mongodb_data
            }

            self.message_queue.append(message)
            self.db_thread_msg_received_event.set()

        except Exception as e:
            logging.error(e)

    # Topic subscribed callback
    def _subscribed(self, client_ptr, userdata, mid, granted_qos):
        logging.debug("Topic subscribed on client {}".format(self.id))
        # TODO update (UI)

    # Message published callback
    def _published(self, client_ptr, userdata, mid):
        logging.debug("Message published by client {}".format(self.id))

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

        return None, False, None

    def _create_mongo_db_data(self, topic, data, is_wildcard_topic=False, wildcard_sub_path=None):
        try:
            processed_data = json.loads(data)
        except Exception as e:
            logging.error(e)
            processed_data = data.decode()

        mongodb_data = dict()
        dataobjects = DataObject.objects.filter(topic=topic)
        for dataobject in dataobjects:
            object_value = self._get_data_value(dataobject, processed_data)
            if not is_wildcard_topic:
                if object_value:
                    mongodb_data[str(dataobject.id)] = object_value
            else:
                if dataobject.path is None and len(wildcard_sub_path) > 0:
                    continue
                elif dataobject.path != wildcard_sub_path:
                    continue

                if object_value:
                    mongodb_data[str(dataobject.id)] = object_value

        return mongodb_data

    def _get_data_value(self, dataobject, data):
        raw_data = None
        if dataobject.format == dataobject.FORMAT_CHOICE_JSON:
            try:
                if dataobject.key in data.keys():
                    raw_data = data[str(dataobject.key)]
            except Exception as e:
                logging.error(e)
                return None
        elif dataobject.format == dataobject.FORMAT_CHOICE_SINGLE_VARIABLE:
            raw_data = data

        if raw_data:
            try:
                if dataobject.data_type == dataobject.DATA_TYPE_NUMBER:
                    if isinstance(raw_data, int) or isinstance(raw_data, float):
                        return raw_data
                elif dataobject.data_type == dataobject.DATA_TYPE_STRING:
                    return str(raw_data)
                elif dataobject.data_type == dataobject.DATA_TYPE_LOCATION:
                    #TODO location object
                    pass
                elif dataobject.data_type == dataobject.DATA_TYPE_BOOLEAN:
                    if isinstance(raw_data, bool):
                        return raw_data
            except Exception as e:
                logging.exception(e)
                return None

        return None

