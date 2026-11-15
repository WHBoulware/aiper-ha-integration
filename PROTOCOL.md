# Aiper app — reverse-engineered protocol notes

Target: `Aiper-RM-iOS.app`, bundle id `com.aiper.link` (the "Aiper" / IrriSense
app). Reconstructed by static analysis of the shipped iOS binary (string table,
embedded JSON config, framework list, Swift symbol names). No live traffic was
captured for this document; items that need a capture to confirm are marked
**NEEDS CAPTURE**.

This is interoperability documentation for controlling hardware you own from
Home Assistant. It contains no Aiper source code and no private keys.

## 1. Stack (from the framework list)

| Area | Evidence | Meaning |
|------|----------|---------|
| Networking | `Alamofire`, `Moya` | REST client |
| Auth | `AWSCore`, `AWSCognitoIdentityProvider`, `AWSMobileClient` | Cognito user/identity pools |
| Realtime | `AWSIoT`, `CocoaAsyncSocket` | MQTT over WebSocket to AWS IoT Core |
| Device payloads | `SwiftProtobuf`, `Protobuf`, `__swift5_proto` section | protobuf-framed device messages |
| BLE | `NordicDFU`, `YModemLib`, CoreBluetooth symbols | local BLE control + OTA |
| Crypto | `CryptoSwift`, `SwiftyRSA` | AES + RSA request protection |

So control is **BLE-first, cloud(IoT)-fallback** — confirmed by
`AiperTransportService.sendCommand(... route: ...)` with log lines
`[Transport] resolvedRoute bleName miss, SN fallback hit` and
`preferred=…,resolved=…,bleConnected=…,iotConnected=…`.

## 2. Regions

From `newCountry-prod.json` in the bundle, every country maps to one of three
API hosts:

- `https://apiamerica.aiper.com/`  (region `america`)
- `https://apieurope.aiper.com/`   (region `europe`)
- `https://apiasia.aiper.com/`     (region `asia`)

(There is also a China stack `api.aiper.com.cn` using `*.amazonaws.com.cn`.)

## 3. HTTP request shape

Headers (from `NetWork/Apis/Api.swift` symbols): `Device-Id`, `language`,
`Accept-Language`, `appVersion`, `timestamp`, `zoneId`, `source`. Bearer token
is carried in a `token` header (Authorization accepted as fallback).

Body encryption (`AINetworkCryptoUtils.swift`, envelope keys `content` +
`aesKey`):

1. random 16-byte AES key per request;
2. `content = base64(AES(json_body))`;
3. `aesKey = base64(RSA_pub(aes_key))` using the 1024-bit RSA **public** key
   embedded in the binary (in `const.py` as `APP_RSA_PUBLIC_KEY_B64`);
4. response decrypts with the same AES key.

**NEEDS CAPTURE:** AES mode/padding (CBC-zero-IV assumed; could be ECB or
CBC-with-prefixed-IV) and whether every endpoint is encrypted (several app
paths set `encrypt=false`/`noHeader`). `crypto.py` isolates both so one
capture flips a flag.

## 4. REST endpoints used by this integration

| Purpose | Endpoint |
|---------|----------|
| Login | `loginAccount` |
| Register | `register`, `registerByCode` |
| Refresh token | `users/getTokenByRefreshToken`, `users/token/refresh` |
| Current user | `users/current` |
| Device tree | `family/v1/getFamilyAllInfo` |
| Device list | `equipment/getEquipment`, `equipment/getEquipmentInfo` |
| Online check | `equipment/checkEquipmentOnlineStatus` |
| IoT provisioning | `users/getOpenIdToken` (→ `iotEndpoint`, `identityId`), kept alive by `users/verificationToken` |
| Session data | `swimming/getSwimmingBySn`, `swimming/startOrStop` |

Normalised device fields seen in responses: `deviceSn`, `deviceName`,
`deviceModel`/`productModel`, `bleName`, `firmwareVersion`/`mainVersion`,
`onlineStatus`, `placeId`.

Models referenced in the bundle: Scuba/Surfer **X9, X30, N30, N31, B30, S1,
S2, T1/T1 Pro, W2, X5/X5 Pro, X6, X7**, and the **RM01** robotic
irrigation/mower (the "WR" modules). The REST+shadow path is model-agnostic;
command payloads are per-family.

## 5. AWS IoT MQTT (from `IoTManager` symbols)

Connect: MQTT over WebSocket to the `iotEndpoint`, authenticated with AWS
credentials derived from the Cognito identity in the `getOpenIdToken`
response (`connectUsingWebSocket`, `identityId=`, `clientId=`).

Topics (`{sn}` = device serial):

| Direction | Topic |
|-----------|-------|
| Device shadow write | `$aws/things/{sn}/shadow/update` |
| Shadow accepted | `$aws/things/{sn}/shadow/update/accepted` |
| App → cloud | `aiper/things/{sn}/app/cloud/upChan` |
| Cloud → app | `aiper/things/{sn}/cloud/app/downChan` |
| App report | `aiper/things/{sn}/app/report` |
| Shadow report | `aiper/things/{sn}/shadow/report` |

Publish/subscribe primitives: `publishDataToIot(thingSn,data,qoS)`,
`publishDataToShadow(thingSn,content)`, `subscribeFromShadowReport`,
`subscribeFromAppReport`, `subscribeAuthRequestFromCloud`.

State keys seen in shadow/report handling: `workStatus`, `cleanMode`,
`battery`, `errorCode`, `online`, `temperature`, `direction`, `workTime`.

**NEEDS CAPTURE:** the exact byte layout of a command published to
`.../cloud/app/downChan`. It is a binary/protobuf frame
(`acceptPacket(index:payload:)`, `payloadLen=`, `AIRM01DeviceDataParser`), not
plain JSON, so it cannot be reconstructed from strings. `mqtt.build_command`
is the single place to fill this in — see `tools/capture_guide.md`.

## 6. What works today vs. after one capture

Works now (static reconstruction):
- regional login + token refresh,
- device discovery (family tree / equipment list),
- battery / online / work-status / error / firmware read-out,
- MQTT subscribe to live shadow state (JSON shadow decodes directly).

Needs one capture to finish:
- confirm AES mode if login is rejected,
- the 3–4 command frames (start / stop / pause / recall) and, if used, the
  Cognito-creds exchange details for the WebSocket.
