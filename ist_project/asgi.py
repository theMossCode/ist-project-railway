"""
ASGI config for IST project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.1/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ist_project.settings')

from channels.routing import ChannelNameRouter, ProtocolTypeRouter
from dashboard.mqtt.consumers import MQTTConsumer

application = ProtocolTypeRouter(
    {
        "channel": ChannelNameRouter({
            "mqtt": MQTTConsumer.as_asgi()
        }),
        "http": get_asgi_application()
    }
)


