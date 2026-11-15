"""Constants for the Aiper Pool Cleaner integration.

All values here were reconstructed by static reverse-engineering of the
Aiper iOS app (bundle id ``com.aiper.link``). See PROTOCOL.md for the
evidence behind each value. Items marked ``# NEEDS CAPTURE`` could not be
confirmed from the binary alone and should be verified with one live
traffic capture (see tools/capture_guide.md) before relying on them.
"""

from __future__ import annotations

DOMAIN = "aiper"

# --- Regional API hosts -----------------------------------------------------
# Source: newCountry-prod.json inside the app bundle. The app picks the host
# from the user's selected country/region.
REGION_AMERICA = "america"
REGION_EUROPE = "europe"
REGION_ASIA = "asia"

API_HOSTS: dict[str, str] = {
    REGION_AMERICA: "https://apiamerica.aiper.com/",
    REGION_EUROPE: "https://apieurope.aiper.com/",
    REGION_ASIA: "https://apiasia.aiper.com/",
}

DEFAULT_REGION = REGION_AMERICA

# --- REST endpoints (relative to the regional host) -------------------------
# Source: string table of the app binary (NetWork/Apis/Api.swift).
EP_LOGIN = "loginAccount"
EP_REGISTER = "register"
EP_TOKEN_REFRESH = "users/getTokenByRefreshToken"
EP_CURRENT_USER = "users/current"
EP_GET_FAMILY_ALL = "family/v1/getFamilyAllInfo"
EP_GET_EQUIPMENT = "equipment/getEquipment"
EP_GET_EQUIPMENT_INFO = "equipment/getEquipmentInfo"
EP_CHECK_ONLINE = "equipment/checkEquipmentOnlineStatus"
EP_GET_OPENID_TOKEN = "users/getOpenIdToken"          # returns AWS IoT model
EP_VERIFICATION_TOKEN = "users/verificationToken"      # keeps IoT creds alive
EP_SWIMMING_BY_SN = "swimming/getSwimmingBySn"         # per-session robot data
EP_SWIMMING_START_STOP = "swimming/startOrStop"        # NEEDS CAPTURE (payload)

# --- HTTP headers the app sends --------------------------------------------
# Source: Api.swift references to headers Device-Id / Accept-Language /
# appVersion / timestamp / language / zoneId.
HEADER_DEVICE_ID = "Device-Id"
HEADER_LANGUAGE = "language"
HEADER_APP_VERSION = "appVersion"
HEADER_TIMESTAMP = "timestamp"
HEADER_ZONE_ID = "zoneId"

# A recent app version string; the server tolerates a range of values but
# wants a plausible one. Override in options if the API starts rejecting it.
DEFAULT_APP_VERSION = "3.0.0"
CLIENT_SOURCE = "2"   # 2 = iOS in the app's enum (NEEDS CAPTURE to confirm)

# --- Request body envelope keys --------------------------------------------
# Source: crypto/envelope keys observed near AINetworkCryptoUtils.swift:
# encrypted JSON goes in ``content`` and the RSA-wrapped AES key in ``aesKey``.
ENV_CONTENT = "content"
ENV_AESKEY = "aesKey"

# App RSA *public* key (used to wrap the per-request AES key). This is a
# public key embedded in the shipping binary, safe to include. Base64 DER
# (X.509 SubjectPublicKeyInfo, 1024-bit).
APP_RSA_PUBLIC_KEY_B64 = (
    "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCIKoKPqwq1f60hm/2lpHDF/DT4"
    "J9YaptuTq78nsxdgnSBAvkIZ3E8dqbEBT/VETjJ9Yr28QtHX13E8QGByYxLzYPl"
    "dHNXChgOWfSemTEC3TxPvlaSuM9eFUuhqSeGbgoKG7JJNlgjvsPO2cHEhPXJE4q"
    "WtKEZVOZBxEeCgAaLZxwIDAQAB"
)

# --- AWS IoT MQTT topics ----------------------------------------------------
# Source: IoTManager strings. {sn} = device serial number (deviceSn).
TOPIC_SHADOW_UPDATE = "$aws/things/{sn}/shadow/update"
TOPIC_SHADOW_UPDATE_ACCEPTED = "$aws/things/{sn}/shadow/update/accepted"
TOPIC_APP_CLOUD_UP = "aiper/things/{sn}/app/cloud/upChan"      # app -> cloud
TOPIC_CLOUD_APP_DOWN = "aiper/things/{sn}/cloud/app/downChan"  # cloud -> app
TOPIC_APP_REPORT = "aiper/things/{sn}/app/report"
TOPIC_SHADOW_REPORT = "aiper/things/{sn}/shadow/report"

# --- Config entry / options keys -------------------------------------------
CONF_REGION = "region"
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_DEVICE_ID = "device_id"
CONF_APP_VERSION = "app_version"
CONF_USE_MQTT = "use_mqtt"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 60  # seconds

PLATFORMS = ["vacuum", "sensor", "binary_sensor"]

# --- Device work-status mapping --------------------------------------------
# Source: shadow keys workStatus / cleanMode / errorCode / battery / online.
# The numeric values below are the best mapping inferable from the binary;
# confirm against your own device with the capture tool.
WORK_STATUS_IDLE = 0
WORK_STATUS_CLEANING = 1
WORK_STATUS_CHARGING = 2
WORK_STATUS_PAUSED = 3
WORK_STATUS_RETURNING = 4
WORK_STATUS_ERROR = 5
