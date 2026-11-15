# Finishing the integration with one traffic capture

Two things can't be recovered from the app binary alone: (a) the exact AES
mode, only if login is rejected, and (b) the binary command frames for
start/stop/recall. A single capture of the real app nails both. ~20 minutes.

You need: the Aiper app on a phone, a computer on the same network, and
[mitmproxy](https://mitmproxy.org/).

## A. Capture the REST login (confirms the crypto)

1. `pip install mitmproxy` and run `mitmweb`.
2. On the phone, set the Wi-Fi HTTP proxy to your computer's IP : 8080, then
   open `http://mitm.it` and install + trust the mitmproxy CA (Settings →
   General → About → Certificate Trust Settings must enable it).
3. In the Aiper app, log out and log back in.
4. In mitmweb find the `POST .../loginAccount` to `apiamerica/europe/asia.aiper.com`.
   - If the request body is `{"content":"...","aesKey":"..."}` → the envelope
     in `crypto.py` is right. You don't need to change anything unless HA
     login fails.
   - If HA login *does* fail, decrypt the captured `content` yourself: the
     AES key is `RSA_private(aesKey)` — but you don't have the private key, so
     instead just try the three variants in `crypto.py`:
     `AES_MODE="CBC"/"ECB"` and `AES_IV_MODE="ZERO_IV"/"PREFIX"`. One of the
     four combinations will authenticate. (CBC + ZERO_IV is the default.)

## B. Capture a command (fills in `build_command`)

MQTT over AWS IoT is a WebSocket, so use mitmproxy's WebSocket view (mitmweb
shows WS frames) **or** the app's own debug logs if available.

1. With the capture still running and the robot online, press **Start** in the
   app once. Then **Stop**. Then **Recall / Return**.
2. Find the WebSocket messages published to
   `aiper/things/<your-sn>/cloud/app/downChan` (or a `$aws/things/<sn>/shadow/update`
   write). Copy the payload bytes of each (mitmweb shows hex).
3. Open `custom_components/aiper/mqtt.py` → `build_command` and fill the table:

   ```python
   def build_command(command, params):
       TABLE = {
           "start":  bytes.fromhex("....your captured start bytes...."),
           "stop":   bytes.fromhex("....."),
           "pause":  bytes.fromhex("....."),
           "recall": bytes.fromhex("....."),
       }
       return TABLE.get(command)
   ```

   If instead the capture shows a JSON shadow write like
   `{"state":{"desired":{"workStatus":1}}}`, return that JSON encoded to bytes
   and publish to the shadow topic — the function already documents this case.

4. Restart Home Assistant. The vacuum Start/Stop/Return buttons now work.

### If the WebSocket is certificate-pinned
AWS IoT WebSocket uses standard TLS to `*.iot.<region>.amazonaws.com`; it is
normally interceptable with the mitmproxy CA trusted. If a specific firmware
pins it, capture the BLE path instead (nRF Connect / a BLE sniffer) — the same
command frames are sent over the Nordic UART characteristic, and
`build_command` output is identical for both transports.
