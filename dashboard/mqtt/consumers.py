import logging

from asgiref.sync import async_to_sync, sync_to_async
from channels.consumer import AsyncConsumer, SyncConsumer
from channels.db import database_sync_to_async
from .client import MQTTClient, mqtt_clients_list
from ..models import Project, Topic


class MQTTSyncConsumer(SyncConsumer):
    def __init__(self):
        super().__init__()
        logging.debug("Init mqtt sync consumer {}".format(self))
        self.clients = list()

    def client_init(self, event):
        projects = Project.objects.all()
        if projects:
            for project in projects:
                client_exists = False
                for client in self.clients:
                    if project.id == client.id:
                        client_exists = True
                        break

                if not client_exists:
                    logging.debug("Add client")
                    async_to_sync(self.channel_layer.send)(
                        "mqtt", {
                            "type": "client.add",
                            "project_id": project.id,
                        }
                    )

    def client_add(self, event):
        """
        :param event: Channels layer event
        """

        logging.debug("Add client")
        try:
            project_id = event["project_id"]
            client = MQTTClient(project_id)
            self.clients.append(client)
            # mqtt_clients_list.append(self.client)
            logging.debug("Mqtt client added")
            logging.debug("{}".format(self.clients))
            async_to_sync(self.channel_layer.send)(
                "mqtt",
                {
                    "type": "client.connect",
                    "project_id": project_id,
                }
            )
        except Exception as e:
            logging.exception(e)

    def client_connect(self, event):
        logging.debug("Connect client {}".format(event["project_id"]))
        try:
            project_id = event["project_id"]
            project = self._get_project(project_id)
            client = self._is_client_exists(project_id)
            if not client:
                raise ValueError("Client does not exist")

            if not client.connect_server(project.host, project.port):
                raise ConnectionError("Could not connect to mqtt server")
        except Exception as e:
            logging.exception(e)

    def client_disconnect(self, event):
        logging.debug("Disconnect client {}".format(event["project_id"]))
        try:
            project_id = event["project_id"]
            client = self._is_client_exists(project_id)
            if not client:
                raise ValueError("Client does not exist")

            client.disconnect_server()
        except Exception as e:
            logging.exception(e)

    def client_subscribe_topic(self, event):
        try:
            project_id = event["project_id"]
            topic_id = event["topic_id"]
            client = self._is_client_exists(project_id)
            if not client:
                raise ValueError("Client does not exist")

            topic = self._get_topic(topic_id)
            if not client.subscribe_topic(topic.path, topic.qos):
                raise ConnectionError("Topic subscription error")

            logging.debug("subscribe topic {}".format(topic.path))
        except Exception as e:
            logging.exception(e)

    def client_unsubscribe_topic(self, event):
        try:
            project_id = event["project_id"]
            topic_path = event["topic_path"]
            client = self._is_client_exists(project_id)
            if not client:
                raise ValueError("Client does not exist")

            if not client.unsubscribe_topic(topic_path):
                raise ConnectionError("Could not unsubscribe topic")
        except Exception as e:
            logging.exception(e)

    def client_publish_message(self, event):
        logging.debug("Publish message {}".format(event["msg"]))

    def client_update_db(self, event):
        project_id = event.get("project_id", None)
        topic_id = event.get("topic_id", None)
        if (not project_id) or (not topic_id):
            logging.error("Project or topic id invalid")
            return

        client = self._is_client_exists(project_id)
        if not client:
            logging.debug("Client does not exist")
            return

        topic = Topic.objects.get(pk=topic_id)
        if not topic:
            logging.error("Invalid topic")

        client.save_data_to_db(topic)

    def _is_client_exists(self, _id):
        logging.debug("{}".format(self.clients))
        for client in self.clients:
            if client.id == _id:
                return client

        return None

    def _get_project(self, _id):
        try:
            project = Project.objects.get(pk=_id)
            if project is not None:
                return project
            else:
                raise ValueError("Inavalid project ID")
        except Exception as e:
            logging.exception(e)
            # TODO send error message to websocket interface
            return None

    def _get_topic(self, _id):
        try:
            topic = Topic.objects.get(pk=_id)
            if not topic:
                raise ValueError("Topic not valid")

            return topic
        except Exception as e:
            logging.exception(e)
            return None


class MQTTConsumer(AsyncConsumer):
    """
    Async mqtt consumer. Not used in current deployment (31/01/2023)
    """
    def __init__(self):
        logging.debug("Init mqtt async consumer".format(self))
        self.clients = list()

    async def client_init(self, event):
        projects = await database_sync_to_async(self.db_get_projects)()
        async for project in projects:
            if len(mqtt_clients_list) <= 0:
                logging.debug("Add project")
                await self.channel_layer.send(
                    "mqtt", {
                        "type": "client.add",
                        "project_id": project.pk,
                    }
                )
            else:
                for client in self.clients:
                    if client.id == project.pk:
                        logging.debug("Project in clients")
                        await self.channel_layer.send(
                            "mqtt", {
                                "type": "client.connect",
                                "project_id": project.pk,
                            }
                        )
                        break
                    else:
                        logging.debug("Client not initialised")
                        await self.channel_layer.send(
                            "mqtt", {
                                "type": "client.add",
                                "project_id": project.pk,
                            }
                        )

        logging.debug("Init complete")

    async def client_add(self, event):
        """
        Add MQTT client
        :param event: channels layer event
        :return: Index of client in client list, None on error
        TODO Raise and handle exceptions
        """

        logging.debug("Add Client")
        project_id = event.get("project_id", None)
        if not project_id:
            logging.error("Project id invalid!!")
            return

        project = await database_sync_to_async(self.db_get_project)(project_id)
        if not self._check_object_validity(project):
            logging.error("Invalid project")
            return

        client = self.get_client(project_id=project.id)
        if self._check_object_validity(client):
            logging.debug("Client already exists")
            return

        client = MQTTClient(project_id=project.id)
        mqtt_clients_list.append(client)

        try:
            logging.debug("Client added")
            await self.channel_layer.send(
                "mqtt",
                {
                    "type": "client.connect",
                    "project_id": project.id,
                }
            )
        except Exception as e:
            logging.debug(e)

    async def client_connect(self, event):
        """
        Connect to MQTT server \n
        :param event: Channels layer event\n
        :return: \n
        TODO Handle exceptions
        """

        project_id = event.get("project_id", None)
        if not project_id:
            logging.error("Project id invalid!!")

        logging.debug("Connect client (project {})".format(project_id))
        project = await database_sync_to_async(self.db_get_project)(project_id)
        if not self._check_object_validity(project):
            logging.error("Project not valid!!")
            return

        client = self.get_client(project.id)
        if not self._check_object_validity(client):
            logging.error("Client not valid!!")
            return

        if client.is_connected():
            return

        await sync_to_async(client.connect_server)(project.host, project.port)

    async def mqtt_client_disconnect(self, event):
        client = self.get_client(event["client"])
        if not self._check_object_validity(client):
            return False

        if client.is_connected():
            await sync_to_async(client.disconnect_server)()

        return True

    async def client_subscribe_topic(self, event):
        topic_id = event.get("topic_id", None)
        project_id = event.get("project_id", None)
        if (not topic_id) or (not project_id):
            logging.error("Topic or project id invalid")
            return

        topic = await database_sync_to_async(self.db_get_topic)(topic_id)
        if not topic:
            logging.error("Topic invalid!!")
            return

        logging.debug("Subscribe (Topic {})".format(topic.path))
        client = self.get_client(project_id)
        if not self._check_object_validity(client):
            return

        await sync_to_async(client.subscribe_topic)(topic.path, topic.qos)

    async def client_unsubscribe_topic(self, event):
        logging.debug("Unsubscribe topic")
        project_id = event.get("project_id", None)
        topic_id = event.get("topic_id", None)
        if (not project_id) or (not topic_id):
            logging.error("Project or topic id invalid!!")
            return

        topic = await sync_to_async(self.db_get_topic)(topic_id)
        if not topic:
            logging.error("Topic not valid!!")
            return

        client = self.get_client(project_id)
        if not self._check_object_validity(client):
            return

        await sync_to_async(client.unsubscribe_topic)(topic)


    async def client_save_db(self, event):
        project_id = event.get("project_id", None)
        if not project_id:
            logging.error("Project id not valid!!")
            return

        client = self.get_client(project_id)
        if not client:
            logging.error("Client not valid!!")
            return

        await sync_to_async(client.update_db)()

    def _check_object_validity(self, obj):
        if obj is None:
            return False

        return True

    def get_client(self, project_id):
        for mqtt_client in mqtt_clients_list:
            if mqtt_client.id == project_id:
                return mqtt_client

        return None

    def db_get_project(self, project_id):
        return Project.objects.get(pk=project_id)

    def db_get_projects(self):
        return Project.objects.all()

    def db_get_topic(self, topic_id):
        return Topic.objects.get(pk=topic_id)
