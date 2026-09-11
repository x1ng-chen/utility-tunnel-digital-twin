# ESP MQTT Endpoint Discovery Design

## Goal

Remove the laptop MQTT broker IP address from ESP8266 build-time secrets so both
controllers recover automatically when a phone hotspot assigns the laptop a new
address.

## Protocol

The IoTDA gateway broadcasts one compact UDP datagram every three seconds on
port `4210`:

```text
UT-MQTT-DISCOVERY/1|utility-tunnel|1884
```

The ESP trusts only an exact protocol/version and service-name match, validates
the decimal port, and uses the UDP packet sender address as the broker address.
The broker is currently unauthenticated on an isolated bench network; discovery
does not claim to add network authentication.

## ESP behavior

- Connect to the existing Wi-Fi SSID without a compiled `MQTT_HOST`.
- Load the last successful broker IPv4 address and port from EEPROM with magic,
  schema version, and CRC validation.
- Listen continuously for discovery packets while connected to Wi-Fi.
- Try the saved endpoint immediately, while continuing discovery.
- Switch to a newly discovered endpoint, disconnect the old MQTT session, and
  persist only after the new endpoint connects successfully.
- Avoid redundant EEPROM writes when the endpoint is unchanged.
- Continue the existing bounded telemetry queue and reconnection behavior.
- Keep `DEVICE_ID` build-specific for CTRL-01 and CTRL-02.

## Gateway behavior

The existing IoTDA gateway owns the discovery broadcaster. It starts only after
configuration validation, broadcasts on all usable IPv4 interfaces, advertises
the externally reachable Mosquitto port `1884`, and closes its UDP sockets on
shutdown. Discovery failures are logged but do not terminate cloud forwarding.

## Verification

- Node tests cover packet creation, interface broadcast selection, and lifecycle.
- PlatformIO builds both ESP environments.
- An ESP is flashed with no `MQTT_HOST`; after reboot it must report the current
  laptop address and `mqtt=up`.
- Changing/reconnecting the hotspot must lead to rediscovery without reflashing.

