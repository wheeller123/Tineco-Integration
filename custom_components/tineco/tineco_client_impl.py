"""
Tineco IoT API Client Implementation.
"""
import json
import logging
import requests
import hashlib
import time
import uuid
from typing import Dict, Optional, Tuple

_LOGGER = logging.getLogger(__name__)


class TinecoNewDeviceException(Exception):
    """Exception raised when new device verification is required."""

    def __init__(self, verify_id):
        self.verify_id = verify_id


class TinecoClient:
    """Tineco API client base implementation."""

    AUTH_APPKEY = "1538105560006"
    APP_SECRET = "fb7045ebb8ae5297bca45cbf5a5597ab"

    # IoT / AuthCode constants
    AUTH_APPKEY_AUTHCODE = "1538103661113"
    APP_SECRET_AUTHCODE = "197472fcef3935ebc330657266992b99"

    # Region to timezone mapping
    REGION_TIMEZONE_MAP = {
        "IE": "Europe/London",
        "UK": "Europe/London",
        "PL": "Europe/Warsaw",
        "DE": "Europe/Berlin",
        "FR": "Europe/Paris",
        "ES": "Europe/Madrid",
        "IT": "Europe/Rome",
        "US": "America/New_York",
    }

    def __init__(self, device_id: str = None, region: str = "IE", language: str = "EN_US"):
        self.region = region
        self.language = language

        if device_id:
            self.DEVICE_ID = device_id
        else:
            self.DEVICE_ID = "57938f751acc6897088c718770edcd00"

        self.APP_VERSION = "1.7.0"
        self.STORE = "google_play"
        self.AUTH_TIMEZONE = self.REGION_TIMEZONE_MAP.get(region, "Europe/London")

        self.access_token = ""
        self.uid = ""
        self.auth_code = ""
        self.iot_token = ""
        self.iot_resource = ""
        self.device_list = []

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "okhttp/3.12.0",
            "Connection": "Keep-Alive"
        })
        self.IOT_API_BASE = "https://api-ngiot.dc-eu.ww.ecouser.net/api/iot/endpoint/control"
        self.IOT_LOGIN_ENDPOINT = "https://api-base.dc-eu.ww.ecouser.net/api/users/user.do"

    def _is_china_region(self) -> bool:
        """Return True if the configured region is mainland China."""
        return self.region.upper() == "CN"

    @staticmethod
    def generate_valid_device_id():
        """Generates a random device ID in MD5 format (32 hex chars)."""
        random_uuid = uuid.uuid4().hex
        return hashlib.md5(random_uuid.encode('utf-8')).hexdigest()

    def _md5_hash(self, text: str) -> str:
        return hashlib.md5(text.encode('utf-8')).hexdigest()

    def _process_login_success(self, data_json):
        d = data_json.get("data", data_json)
        self.access_token = d.get("accessToken", "")
        self.uid = d.get("uid", "")
        _LOGGER.info(f"Login successful! UID: {self.uid}")
        return True, self.access_token, self.uid

    def login(self, email: str, password: str, request_code: bool = False) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Login method.
        request_code=True -> Sends email if 10001 error occurs (Interactive mode).
        request_code=False -> Just logs error (Background mode).
        """
        try:
            timestamp = int(time.time() * 1000)
            password_md5 = self._md5_hash(password)

            sign_params = [
                f"authTimespan={timestamp}",
                f"authTimeZone={self.AUTH_TIMEZONE}",
                f"country={self.region}",
                f"lang={self.language}",
                "appCode=global_e",
                f"appVersion={self.APP_VERSION}",
                f"deviceId={self.DEVICE_ID}",
                f"channel={self.STORE}",
                "deviceType=1",
                "uid=",
                "accessToken=",
                f"account={email}",
                f"password={password_md5}"
            ]
            sign_params.sort()
            auth_string = self.AUTH_APPKEY + "".join(sign_params) + self.APP_SECRET
            auth_sign = self._md5_hash(auth_string)

            base_url = (f"https://qas-gl-{self.region.lower()}-api.tineco.com/v1/private/"
                        f"{self.region}/{self.language}/{self.DEVICE_ID}/global_e/"
                        f"{self.APP_VERSION}/{self.STORE}/1/user/login")

            query_params = {
                "authAppkey": self.AUTH_APPKEY, "authSign": auth_sign,
                "authTimeZone": self.AUTH_TIMEZONE, "authTimespan": timestamp,
                "account": email, "password": password_md5,
                "uid": "", "accessToken": ""
            }

            encoded_params = []
            for k, v in query_params.items():
                val_str = str(v)
                val_encoded = (val_str.replace("%", "%25").replace(" ", "%20")
                               .replace("+", "%2B").replace("/", "%2F").replace("&", "%26"))
                encoded_params.append(f"{k}={val_encoded}")

            full_url = f"{base_url}?{'&'.join(encoded_params)}"

            response = self.session.get(full_url, timeout=10)

            if response.status_code == 200:
                data = response.json()
                code = str(data.get("code"))

                if code == "0000":
                    return self._process_login_success(data)

                elif code == "10001":
                    _LOGGER.warning(f"Got 10001 (New Device). Interactive mode: {request_code}")

                    if request_code:
                        if self._is_china_region():
                            verify_id = self.send_sms_verify_code(email)
                        else:
                            verify_id = self.send_email_verify_code(email)
                        if verify_id:
                            # This exception must be caught by config_flow
                            raise TinecoNewDeviceException(verify_id)
                        return False, None, None
                    else:
                        _LOGGER.error("New device verification required but running in background. Ignoring.")
                        return False, None, None
                else:
                    _LOGGER.error(f"Login failed. Code: {code}, Msg: {data.get('msg')}")
                    return False, None, None
            else:
                _LOGGER.error(f"HTTP Error: {response.status_code}")
                return False, None, None

        except TinecoNewDeviceException:
            raise
        except Exception as e:
            _LOGGER.exception(f"Unexpected error in login: {e}")
            return False, None, None

    def send_email_verify_code(self, email: str) -> Optional[str]:
        """Requests code and returns verifyId"""
        endpoint = "/user/sendEmailVerifyCode"
        timestamp = int(time.time() * 1000)
        request_id = uuid.uuid4().hex

        sign_params = [
            f"authTimespan={timestamp}", f"authTimeZone={self.AUTH_TIMEZONE}",
            f"country={self.region}", f"lang={self.language}",
            "appCode=global_e", f"appVersion={self.APP_VERSION}",
            f"deviceId={self.DEVICE_ID}", f"channel={self.STORE}",
            "deviceType=1", f"requestId={request_id}",
            f"email={email}", "verifyType=EMAIL_NEW_DEVICE"
        ]
        sign_params.sort()
        auth_string = self.AUTH_APPKEY + "".join(sign_params) + self.APP_SECRET
        auth_sign = self._md5_hash(auth_string)

        base_url = (f"https://qas-gl-{self.region.lower()}-api.tineco.com/v1/private/"
                    f"{self.region}/{self.language}/{self.DEVICE_ID}/global_e/"
                    f"{self.APP_VERSION}/{self.STORE}/1{endpoint}")

        query_params = {
            "authAppkey": self.AUTH_APPKEY, "authSign": auth_sign,
            "authTimeZone": self.AUTH_TIMEZONE, "authTimespan": timestamp,
            "requestId": request_id, "email": email, "verifyType": "EMAIL_NEW_DEVICE"
        }

        encoded_params = []
        for k, v in query_params.items():
            val_str = str(v)
            val_encoded = (val_str.replace("%", "%25").replace(" ", "%20")
                           .replace("+", "%2B").replace("/", "%2F").replace("&", "%26"))
            encoded_params.append(f"{k}={val_encoded}")

        full_url = f"{base_url}?{'&'.join(encoded_params)}"

        try:
            resp = self.session.get(full_url)
            js = resp.json()
            if str(js.get("code")) == "0000":
                v_id = js.get("data", {}).get("verifyId")
                _LOGGER.debug(f"Code sent. VerifyID: {v_id}")
                return v_id
            else:
                _LOGGER.error(f"Failed to send code: {js}")
                return None
        except Exception as e:
            _LOGGER.error(f"Network error in send_email_verify_code: {e}")
            return None

    def send_sms_verify_code(self, phone: str, area_code: str = "+86") -> Optional[str]:
        """Request an SMS verification code for CN region; returns verifyId on success."""
        endpoint = "/user/sendSmsVerifyCode"
        timestamp = int(time.time() * 1000)
        request_id = uuid.uuid4().hex

        sign_params = [
            f"authTimespan={timestamp}", f"authTimeZone={self.AUTH_TIMEZONE}",
            f"country={self.region}", f"lang={self.language}",
            "appCode=global_e", f"appVersion={self.APP_VERSION}",
            f"deviceId={self.DEVICE_ID}", f"channel={self.STORE}",
            "deviceType=1", f"requestId={request_id}",
            f"mobile={phone}", f"mobileAreaNo={area_code}",
            "verifyType=SMS_QUICK_LOGIN"
        ]
        sign_params.sort()
        auth_string = self.AUTH_APPKEY + "".join(sign_params) + self.APP_SECRET
        auth_sign = self._md5_hash(auth_string)

        base_url = (f"https://qas-gl-{self.region.lower()}-api.tineco.com/v1/private/"
                    f"{self.region}/{self.language}/{self.DEVICE_ID}/global_e/"
                    f"{self.APP_VERSION}/{self.STORE}/1{endpoint}")

        query_params = {
            "authAppkey": self.AUTH_APPKEY, "authSign": auth_sign,
            "authTimeZone": self.AUTH_TIMEZONE, "authTimespan": timestamp,
            "requestId": request_id, "mobile": phone,
            "mobileAreaNo": area_code, "verifyType": "SMS_QUICK_LOGIN"
        }

        encoded_params = []
        for k, v in query_params.items():
            val_str = str(v)
            val_encoded = (val_str.replace("%", "%25").replace(" ", "%20")
                           .replace("+", "%2B").replace("/", "%2F").replace("&", "%26"))
            encoded_params.append(f"{k}={val_encoded}")

        full_url = f"{base_url}?{'&'.join(encoded_params)}"

        try:
            resp = self.session.get(full_url)
            js = resp.json()
            if str(js.get("code")) == "0000":
                v_id = js.get("data", {}).get("verifyId")
                _LOGGER.debug(f"SMS code sent. VerifyID: {v_id}")
                return v_id
            else:
                _LOGGER.error(f"Failed to send SMS code: {js}")
                return None
        except Exception as e:
            _LOGGER.error(f"Network error in send_sms_verify_code: {e}")
            return None

    def quick_login_by_email(self, email: str, verify_id: str, verify_code: str) -> Tuple[
        bool, Optional[str], Optional[str]]:
        """Finalize login with OTP."""
        endpoint = "/user/quickLoginByEmail"
        timestamp = int(time.time() * 1000)
        request_id = uuid.uuid4().hex

        sign_params = [
            f"authTimespan={timestamp}", f"authTimeZone={self.AUTH_TIMEZONE}",
            f"country={self.region}", f"lang={self.language}",
            "appCode=global_e", f"appVersion={self.APP_VERSION}",
            f"deviceId={self.DEVICE_ID}", f"channel={self.STORE}",
            "deviceType=1", f"requestId={request_id}",
            f"email={email}", f"verifyId={verify_id}", f"verifyCode={verify_code}"
        ]
        sign_params.sort()
        auth_string = self.AUTH_APPKEY + "".join(sign_params) + self.APP_SECRET
        auth_sign = self._md5_hash(auth_string)

        base_url = (f"https://qas-gl-{self.region.lower()}-api.tineco.com/v1/private/"
                    f"{self.region}/{self.language}/{self.DEVICE_ID}/global_e/"
                    f"{self.APP_VERSION}/{self.STORE}/1{endpoint}")

        query_params = {
            "authAppkey": self.AUTH_APPKEY, "authSign": auth_sign,
            "authTimeZone": self.AUTH_TIMEZONE, "authTimespan": timestamp,
            "requestId": request_id, "email": email,
            "verifyId": verify_id, "verifyCode": verify_code
        }

        encoded_params = []
        for k, v in query_params.items():
            if v is None:
                v = ""
            val_str = str(v)
            val_encoded = (val_str.replace("%", "%25").replace(" ", "%20")
                           .replace("+", "%2B").replace("/", "%2F").replace("&", "%26"))
            encoded_params.append(f"{k}={val_encoded}")

        full_url = f"{base_url}?{'&'.join(encoded_params)}"

        try:
            resp = self.session.get(full_url)
            js = resp.json()
            if str(js.get("code")) == "0000":
                return self._process_login_success(js)
            else:
                _LOGGER.error(f"OTP verification failed. Msg: {js.get('msg')}")
                return False, None, None
        except Exception as e:
            _LOGGER.error(f"Network error in quick_login_by_email: {e}")
            return False, None, None

    def quick_login_by_mobile(self, phone: str, verify_id: str, verify_code: str,
                              area_code: str = "+86") -> Tuple[bool, Optional[str], Optional[str]]:
        """Finalize SMS-based OTP login for CN region."""
        endpoint = "/user/quickLoginByMobile"
        timestamp = int(time.time() * 1000)
        request_id = uuid.uuid4().hex

        sign_params = [
            f"authTimespan={timestamp}", f"authTimeZone={self.AUTH_TIMEZONE}",
            f"country={self.region}", f"lang={self.language}",
            "appCode=global_e", f"appVersion={self.APP_VERSION}",
            f"deviceId={self.DEVICE_ID}", f"channel={self.STORE}",
            "deviceType=1", f"requestId={request_id}",
            f"mobile={phone}", f"mobileAreaNo={area_code}",
            f"verifyId={verify_id}", f"verifyCode={verify_code}"
        ]
        sign_params.sort()
        auth_string = self.AUTH_APPKEY + "".join(sign_params) + self.APP_SECRET
        auth_sign = self._md5_hash(auth_string)

        base_url = (f"https://qas-gl-{self.region.lower()}-api.tineco.com/v1/private/"
                    f"{self.region}/{self.language}/{self.DEVICE_ID}/global_e/"
                    f"{self.APP_VERSION}/{self.STORE}/1{endpoint}")

        query_params = {
            "authAppkey": self.AUTH_APPKEY, "authSign": auth_sign,
            "authTimeZone": self.AUTH_TIMEZONE, "authTimespan": timestamp,
            "requestId": request_id, "mobile": phone,
            "mobileAreaNo": area_code, "verifyId": verify_id,
            "verifyCode": verify_code
        }

        encoded_params = []
        for k, v in query_params.items():
            if v is None:
                v = ""
            val_str = str(v)
            val_encoded = (val_str.replace("%", "%25").replace(" ", "%20")
                           .replace("+", "%2B").replace("/", "%2F").replace("&", "%26"))
            encoded_params.append(f"{k}={val_encoded}")

        full_url = f"{base_url}?{'&'.join(encoded_params)}"

        try:
            resp = self.session.get(full_url)
            js = resp.json()
            if str(js.get("code")) == "0000":
                return self._process_login_success(js)
            else:
                _LOGGER.error(f"Mobile OTP verification failed. Msg: {js.get('msg')}")
                return False, None, None
        except Exception as e:
            _LOGGER.error(f"Network error in quick_login_by_mobile: {e}")
            return False, None, None

    def quick_login_by_account(self, account: str, verify_id: str,
                               verify_code: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """Dispatch OTP completion to mobile or email method based on region."""
        if self._is_china_region():
            return self.quick_login_by_mobile(account, verify_id, verify_code)
        else:
            return self.quick_login_by_email(account, verify_id, verify_code)

    def _get_auth_code(self) -> bool:
        """Get authCode from /global/auth/getAuthCode endpoint"""
        if not self.uid or not self.access_token:
            _LOGGER.error("Tineco: REST login required before getting authCode")
            return False

        try:
            url = (f"https://qas-gl-{self.region.lower()}-openapi.tineco.com/v1/"
                   f"global/auth/getAuthCode")

            timestamp = int(time.time() * 1000)

            params_list = [
                f"authTimespan={timestamp}",
                "appCode=global_e",
                f"appVersion={self.APP_VERSION}",
                "openId=global",
                f"uid={self.uid}",
                f"accessToken={self.access_token}",
                f"deviceId={self.DEVICE_ID}"
            ]

            params_list.sort()
            auth_string = self.AUTH_APPKEY_AUTHCODE + "".join(params_list) + self.APP_SECRET_AUTHCODE
            auth_sign = self._md5_hash(auth_string)

            query_params = {
                "authAppkey": self.AUTH_APPKEY_AUTHCODE,
                "authSign": auth_sign,
                "uid": self.uid,
                "accessToken": self.access_token,
                "deviceId": self.DEVICE_ID,
                "appCode": "global_e",
                "appVersion": self.APP_VERSION,
                "authTimespan": timestamp
            }

            _LOGGER.debug("Tineco: requesting authCode from %s", url)
            response = self.session.get(url, params=query_params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                code = data.get("code")

                if code == "0000" or code == 0:
                    auth_code_data = data.get("data", data)
                    if isinstance(auth_code_data, dict):
                        self.auth_code = auth_code_data.get("authCode", "")
                    else:
                        self.auth_code = auth_code_data if isinstance(auth_code_data, str) else ""

                    if not self.auth_code:
                        _LOGGER.error("Tineco: authCode not found in response: %s", data)
                        return False

                    _LOGGER.debug("Tineco: authCode obtained successfully")
                    return True
                else:
                    _LOGGER.error("Tineco: failed to get authCode — code=%s msg=%s", code, data.get('msg'))
                    return False
            else:
                _LOGGER.error("Tineco: _get_auth_code HTTP error %s", response.status_code)
                return False

        except Exception as e:
            _LOGGER.error("Tineco: exception in _get_auth_code: %s", e)
            return False

    def _iot_login(self) -> bool:
        """Login to IoT service to get token and resource for device list API"""
        if not self.uid or not self.auth_code:
            _LOGGER.error("Tineco: REST login and authCode required before IoT login")
            return False

        try:
            import uuid
            device_uuid = str(uuid.uuid4())

            payload = {
                "todo": "loginByItToken",
                "userId": self.uid,
                "token": self.auth_code,
                "realm": "ecouser.net",
                "edition": "default",
                "resource": device_uuid,
                "last": "",
                "country": self.region,
                "org": "TEKWW"
            }

            _LOGGER.debug("Tineco: performing IoT login to %s", self.IOT_LOGIN_ENDPOINT)
            response = self.session.post(self.IOT_LOGIN_ENDPOINT, json=payload, timeout=10)

            if response.status_code == 200:
                data = response.json()
                result = data.get("result", "")

                if result == "ok":
                    self.iot_token = data.get("token", "")
                    self.iot_resource = data.get("resource", device_uuid)

                    if "userId" in data:
                        self.uid = data.get("userId")

                    _LOGGER.debug("Tineco: IoT login successful, resource=%s", self.iot_resource)
                    return True
                else:
                    error = data.get("error", "Unknown error")
                    _LOGGER.error("Tineco: IoT login failed — result=%s error=%s", result, error)
                    return False
            else:
                _LOGGER.error("Tineco: IoT login HTTP error %s", response.status_code)
                return False

        except Exception as e:
            _LOGGER.error("Tineco: exception in _iot_login: %s", e)
            return False

    def get_devices(self) -> Optional[Dict]:
        """Get list of devices for the logged-in user"""
        if not self.access_token or not self.uid:
            _LOGGER.error("Tineco: get_devices called before login")
            return None

        if not self.auth_code:
            _LOGGER.debug("Tineco: fetching authCode for device access")
            if not self._get_auth_code():
                _LOGGER.error("Tineco: failed to obtain authCode — cannot fetch device list")
                return None

        if not self.iot_token:
            _LOGGER.debug("Tineco: performing IoT login for device credentials")
            if not self._iot_login():
                _LOGGER.error("Tineco: IoT login failed — cannot fetch device list")
                return None

        try:
            url = (f"https://qas-gl-{self.region.lower()}-openapi.tineco.com/v1/"
                   f"global/device/getDeviceListV2")

            timestamp = int(time.time() * 1000)

            params_list = [
                f"authTimespan={timestamp}",
                f"lang={self.language}",
                "appCode=global_e",
                f"appVersion={self.APP_VERSION}",
                f"deviceId={self.DEVICE_ID}",
                "openId=global",
                f"uid={self.uid}",
                f"accessToken={self.access_token}",
                f"resource={self.iot_resource}",
                f"token={self.iot_token}",
                f"userId={self.uid}",
                "deviceType=1",
                "refresh=false"
            ]

            params_list.sort()
            auth_string = self.AUTH_APPKEY_AUTHCODE + "".join(params_list) + self.APP_SECRET_AUTHCODE
            auth_sign = self._md5_hash(auth_string)

            query_params = {
                "authAppkey": self.AUTH_APPKEY_AUTHCODE,
                "authSign": auth_sign,
                "uid": self.uid,
                "accessToken": self.access_token,
                "appCode": "global_e",
                "appVersion": self.APP_VERSION,
                "deviceId": self.DEVICE_ID,
                "authTimespan": timestamp,
                "resource": self.iot_resource,
                "token": self.iot_token,
                "userId": self.uid,
                "lang": self.language,
                "deviceType": "1",
                "refresh": "false"
            }

            _LOGGER.debug("Tineco: fetching device list from %s", url)
            response = self.session.get(url, params=query_params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data.get("code") == "0000" or data.get("code") == 0:
                    payload = data.get("payload", data.get("data", data))
                    if isinstance(payload, dict):
                        self.device_list = payload.get("deviceList", payload.get("userDeviceList", []))
                    else:
                        self.device_list = payload if isinstance(payload, list) else []

                    _LOGGER.debug("Tineco: found %d device(s)", len(self.device_list))
                    return data
                else:
                    _LOGGER.error("Tineco: device list API error — code=%s msg=%s",
                                  data.get("code"), data.get('msg', data.get('message')))
                    return None
            else:
                _LOGGER.error("Tineco: get_devices HTTP error %s", response.status_code)
                return None

        except Exception as e:
            _LOGGER.error("Tineco: exception in get_devices: %s", e)
            return None

    def get_device_status(self, device_id: str, device_class: str = "",
                          device_resource: str = "", session_id: str = "") -> Optional[Dict]:
        """Get device status from IoT API"""
        if not self.access_token:
            _LOGGER.error("Tineco: get_device_status called before login")
            return None

        try:
            import random
            import string

            if not session_id:
                chars = string.ascii_letters + string.digits
                session_id = ''.join(random.choice(chars) for _ in range(16))

            params = {
                "ct": "q",
                "eid": device_id,
                "fmt": "j",
                "apn": "QueryMode",
                "si": session_id
            }

            if device_class:
                params["et"] = device_class
            if device_resource:
                params["er"] = device_resource

            headers = {
                "Authorization": f"Bearer {self.iot_token if self.iot_token else self.access_token}",
                "X-ECO-REQUEST-ID": session_id
            }

            _LOGGER.debug("Tineco: querying device status for %s", device_id)
            response = self.session.post(self.IOT_API_BASE, params=params, headers=headers, timeout=10)

            ngiot_ret = response.headers.get("X-NGIOT-RET", "")

            if response.status_code == 200:
                if ngiot_ret == "ok":
                    if response.text:
                        try:
                            return response.json()
                        except Exception:
                            return {"status": "ok", "session_id": session_id}
                    else:
                        return {"status": "ok", "session_id": session_id}
                else:
                    if response.text:
                        try:
                            data = response.json()
                            if isinstance(data, dict) and (
                                    "code" in data and data.get("code") == "0000" or "payload" in data):
                                return data
                        except Exception:
                            pass
                    return None
            else:
                _LOGGER.error("Tineco: get_device_status HTTP error %s", response.status_code)
                return None

        except Exception as e:
            _LOGGER.error("Tineco: exception in get_device_status: %s", e)
            return None

    def _send_iot_query(self, device_id: str, action: str,
                        device_class: str = "", device_resource: str = "",
                        session_id: str = "") -> Optional[Dict]:
        """Internal method to send IoT query actions"""
        if not self.access_token:
            _LOGGER.error("Tineco: _send_iot_query called before login")
            return None

        try:
            import random
            import string

            if not session_id:
                chars = string.ascii_letters + string.digits
                session_id = ''.join(random.choice(chars) for _ in range(16))

            params = {
                "ct": "q",
                "eid": device_id,
                "fmt": "j",
                "apn": action,
                "si": session_id
            }

            if device_class:
                params["et"] = device_class
            if device_resource:
                params["er"] = device_resource

            headers = {
                "Authorization": f"Bearer {self.iot_token if self.iot_token else self.access_token}",
                "X-ECO-REQUEST-ID": session_id
            }

            _LOGGER.debug("Tineco: IoT query device=%s action=%s", device_id, action)
            response = self.session.post(self.IOT_API_BASE, params=params, headers=headers, timeout=10)

            if response.status_code == 200:
                ngiot_ret = response.headers.get("X-NGIOT-RET", "")

                if ngiot_ret == "ok":
                    if response.text:
                        try:
                            return response.json()
                        except Exception:
                            return {"status": "ok", "action": action}
                    else:
                        return {"status": "ok", "action": action}
                else:
                    _LOGGER.debug("Tineco: IoT query action=%s returned ngiot_ret=%s", action, ngiot_ret)
                    return None
            else:
                _LOGGER.error("Tineco: _send_iot_query HTTP error %s for action=%s", response.status_code, action)
                return None

        except Exception as e:
            _LOGGER.error("Tineco: exception in _send_iot_query action=%s: %s", action, e)
            return None

    def get_controller_info(self, device_id: str, device_class: str = "",
                            device_resource: str = "") -> Optional[Dict]:
        """Get controller information (GCI - Get Controller Info)"""
        return self._send_iot_query(device_id, "gci", device_class, device_resource)

    def get_api_version(self, device_id: str, device_class: str = "",
                        device_resource: str = "") -> Optional[Dict]:
        """Get API version (GAV - Get API Version)"""
        return self._send_iot_query(device_id, "gav", device_class, device_resource)

    def get_config_file(self, device_id: str, device_class: str = "",
                        device_resource: str = "") -> Optional[Dict]:
        """Get configuration file (GCF - Get Config File)"""
        return self._send_iot_query(device_id, "gcf", device_class, device_resource)

    def get_device_config_point(self, device_id: str, device_class: str = "",
                                device_resource: str = "") -> Optional[Dict]:
        """Get config point (CFP - Config File Point)"""
        return self._send_iot_query(device_id, "cfp", device_class, device_resource)

    def query_device_mode(self, device_id: str, device_class: str = "",
                          device_resource: str = "") -> Optional[Dict]:
        """Query device operating mode (QueryMode)"""
        return self._send_iot_query(device_id, "QueryMode", device_class, device_resource)

    def get_complete_device_info(self, device_id: str, device_class: str = "",
                                 device_resource: str = "") -> Dict:
        """Get complete device information by querying all available endpoints"""
        _LOGGER.debug("Tineco: retrieving complete device info for %s", device_id)

        info = {}

        try:
            gci = self.get_controller_info(device_id, device_class, device_resource)
            if gci:
                info['gci'] = gci

            gav = self.get_api_version(device_id, device_class, device_resource)
            if gav:
                info['gav'] = gav

            gcf = self.get_config_file(device_id, device_class, device_resource)
            if gcf:
                info['gcf'] = gcf

            cfp = self.get_device_config_point(device_id, device_class, device_resource)
            if cfp:
                info['cfp'] = cfp

            query_mode = self.query_device_mode(device_id, device_class, device_resource)
            if query_mode:
                info['query_mode'] = query_mode

            _LOGGER.debug("Tineco: retrieved %d info source(s) for %s", len(info), device_id)
            return info

        except Exception as e:
            _LOGGER.error("Tineco: exception in get_complete_device_info: %s", e)
            return info

    def control_device(self, device_id: str, command: Dict,
                       device_sn: str = "", device_class: str = "", session_id: str = "", action: str = "cfp") -> \
            Optional[Dict]:
        """Send control command to device via IoT API"""
        if not self.access_token:
            _LOGGER.error("Tineco: control_device called before login")
            return None

        try:
            import random
            import string

            if not session_id:
                chars = string.ascii_letters + string.digits
                session_id = ''.join(random.choice(chars) for _ in range(16))

            params = {
                "ct": "q",
                "eid": device_id,
                "fmt": "j",
                "apn": action,
                "si": session_id
            }

            if device_class:
                params["et"] = device_class
            if device_sn:
                params["er"] = device_sn

            headers = {
                "Authorization": f"Bearer {self.iot_token if self.iot_token else self.access_token}",
                "X-ECO-REQUEST-ID": session_id
            }

            _LOGGER.debug("Tineco: control_device device=%s action=%s command=%s", device_id, action, command)

            response = self.session.post(self.IOT_API_BASE, params=params, headers=headers, json=command, timeout=10)

            _LOGGER.debug("Tineco: control_device response: %s", response.text)

            if response.status_code == 200:
                ngiot_ret = response.headers.get("X-NGIOT-RET", "")

                if ngiot_ret == "ok":
                    if response.text and response.text.strip():
                        try:
                            return response.json()
                        except json.JSONDecodeError:
                            return {"status": "ok", "note": "empty json response"}
                    else:
                        return {"status": "ok", "note": "no response body"}
                else:
                    if response.text:
                        try:
                            data = response.json()
                            return data
                        except Exception:
                            pass
                    return {"status": "unknown", "ngiot_ret": ngiot_ret}
            else:
                _LOGGER.error("Tineco: control_device HTTP error %s", response.status_code)
                return None

        except Exception as e:
            _LOGGER.error("Tineco: exception in control_device: %s", e)
            return None


def print_json(data, indent=2):
    """Pretty print JSON data"""
    try:
        if isinstance(data, dict):
            print(json.dumps(data, indent=indent))
        else:
            print(data)
    except Exception:
        print(data)


def main():
    """Interactive device query tool"""
    print("=" * 80)
    print("Tineco Device Information Retrieval")
    print("=" * 80)
    print()

    client = TinecoClient()

    # Step 1: Authentication
    print("[STEP 1] Authentication")
    print("-" * 80)

    email = input("Enter email: ").strip()
    password = input("Enter password: ").strip()

    success, token, user_id = client.login(email, password)

    if not success:
        print("[ERROR] Login failed!")
        return 1

    print("[OK] Login successful!")
    print(f"    User ID: {user_id}")
    print()

    # Step 2: Get devices
    print("[STEP 2] Get Devices")
    print("-" * 80)

    devices = client.get_devices()

    if not devices or not client.device_list:
        print("[ERROR] No devices found!")
        return 1

    print(f"[OK] Found {len(client.device_list)} device(s)")

    for i, device in enumerate(client.device_list, 1):
        name = device.get('nick') or device.get('deviceName', 'Unknown')
        device_id = device.get('did') or device.get('deviceId')
        print(f"    {i}. {name} ({device_id})")

    print()

    # Step 3: Select device
    print("[STEP 3] Select Device")
    print("-" * 80)

    if len(client.device_list) == 1:
        device = client.device_list[0]
        print(f"[->] Using device: {device.get('nick') or device.get('deviceName')}")
    else:
        idx = int(input(f"Enter device number (1-{len(client.device_list)}): ")) - 1
        device = client.device_list[idx]

    device_id = device.get('did') or device.get('deviceId')
    device_class = device.get('className', '')
    device_resource = device.get('resource', '')
    device_name = device.get('nick') or device.get('deviceName', 'Unknown')

    print(f"[OK] Selected: {device_name}")
    print(f"    ID: {device_id}")
    print(f"    Class: {device_class}")
    print(f"    Resource: {device_resource}")
    print()

    # Step 4: Query all device information
    print("[STEP 4] Query Device Information")
    print("-" * 80)
    print()

    print("[GCI] Get Controller Info")
    print("    Retrieves: Firmware version, hardware info, device capabilities")
    gci = client.get_controller_info(device_id, device_class, device_resource)
    if gci:
        print("[OK] Success:")
        print_json(gci, indent=6)
    else:
        print("[ERROR] Failed to retrieve")
    print()

    print("[GAV] Get API Version")
    print("    Retrieves: Device API version support")
    gav = client.get_api_version(device_id, device_class, device_resource)
    if gav:
        print("[OK] Success:")
        print_json(gav, indent=6)
    else:
        print("[ERROR] Failed to retrieve")
    print()

    print("[GCF] Get Config File")
    print("    Retrieves: Device configuration settings")
    gcf = client.get_config_file(device_id, device_class, device_resource)
    if gcf:
        print("[OK] Success:")
        print_json(gcf, indent=6)
    else:
        print("[ERROR] Failed to retrieve")
    print()

    print("[CFP] Get Config Point")
    print("    Retrieves: Specific configuration point data")
    cfp = client.get_device_config_point(device_id, device_class, device_resource)
    if cfp:
        print("[OK] Success:")
        print_json(cfp, indent=6)
    else:
        print("[ERROR] Failed to retrieve")
    print()

    print("[QueryMode] Get Device Modes")
    print("    Retrieves: Current and available device modes")
    modes = client.query_device_mode(device_id, device_class, device_resource)
    if modes:
        print("[OK] Success:")
        print_json(modes, indent=6)
    else:
        print("[ERROR] Failed to retrieve")
    print()

    # Step 5: Complete Device Information
    print("[STEP 5] Complete Device Information")
    print("-" * 80)
    print()

    print("Retrieving complete device information (all queries at once)...")
    complete_info = client.get_complete_device_info(device_id, device_class, device_resource)

    print(f"\n[OK] Retrieved information from {len(complete_info)} endpoints:")
    for key, value in complete_info.items():
        if value:
            size = len(json.dumps(value))
            print(f"    [OK] {key.upper():15} - {size:,} bytes")
        else:
            print(f"    [ERROR] {key.upper():15} - Failed")

    print()
    print("=" * 80)
    print("Device information retrieval complete!")
    print("=" * 80)

    return 0


if __name__ == "__main__":
    import sys

    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[!] Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
