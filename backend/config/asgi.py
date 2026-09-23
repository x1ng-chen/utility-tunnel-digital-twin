import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter

# This calls django.setup(), so it must precede any consumer/model import.
django_asgi_app = get_asgi_application()

from django.urls import re_path
from operations.consumers import EventsConsumer

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': URLRouter([
        re_path(r'^ws/events/$', EventsConsumer.as_asgi()),
    ]),
})
