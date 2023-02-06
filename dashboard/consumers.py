import json
import logging

from channels.generic.websocket import WebsocketConsumer
from asgiref.sync import async_to_sync


class ProjectAjaxConsumer(WebsocketConsumer):
    def connect(self):
        self.user = self.scope["user"]
        self.project_id = self.scope["url_route"]["kwargs"]["project_id"]
        self.group_name = f"project_{self.project_id}"
        async_to_sync(self.channel_layer.group_add)(
            self.group_name, self.channel_name
        )
        self.accept()
        logging.debug("Websocket connection established")

    def disconnect(self, code):
        async_to_sync(self.channel_layer.group_discard)(
            self.group_name, self.channel_name
        )
        logging.debug("Websocket disconnected")

    def broker_connection_updated(self, event):
        logging.debug("Connection status changed!!")
        connection_status = event["connection"]
        if connection_status == 0:
            resp_html = '<div class="uk-inline" id="disconnected-indicator" hx-swap-oob="true">'\
                        '<span class="uk-label uk-label-danger">Disconnected</span>' \
                        '</div>'
            self.send(text_data=resp_html)
        else:
            resp_html = '<div class="uk-inline" id="disconnected-indicator" hx-swap-oob="true">'\
                        '<span class="uk-label uk-label-success">Connected</span>' \
                        '</div>'
            self.send(text_data=resp_html)
