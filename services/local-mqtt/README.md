# Local MQTT bench broker

This Mosquitto configuration is only for the isolated phone-hotspot bench test. It intentionally permits anonymous clients so the first ESP8266-to-broker link can be verified without storing another credential on the module.

The root `docker-compose.local.yml` maps this broker to host port `1884`, so it can be started together with the local PostgreSQL service.

Do not expose port 1883 to the public Internet. Production traffic must use authenticated MQTTS through the IoTDA gateway.
