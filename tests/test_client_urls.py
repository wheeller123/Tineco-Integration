"""Region-conditional URL / org / timezone / language tests for TinecoClient.

These lock the CN-vs-WW host split (``-appapi.tineco.com`` vs
``-api.tineco.com``) and the IoT-login ``org`` value (``TEK`` vs ``TEKWW``)
— the two axes most likely to break silently when adding a new region.

Constructing a ``TinecoClient`` does no I/O — the DC lookup is deferred to the
first read of ``dc`` / ``IOT_API_BASE`` / ``IOT_LOGIN_ENDPOINT`` (see
``test_construction_does_no_network_io``). Tests that do read those mock
``requests.Session.get`` so they stay hermetic and offline.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from custom_components.tineco.tineco_client_impl import TinecoClient


@pytest.fixture
def offline_dc_lookup():
    """Force the DC lookup to fail so the static REGION_DC_MAP fallback is used.

    Avoids hitting the network during tests and gives deterministic dc values.
    """
    with patch("custom_components.tineco.tineco_client_impl.requests.Session.get") as m:
        m.side_effect = Exception("offline test — DC lookup blocked")
        yield m


@pytest.mark.parametrize(
    "region,expect_host,expect_org,expect_country,expect_tz,expect_lang",
    [
        # CN's IoT country is the literal string "Chinese", not the ISO code.
        # See IOTLB.java LB_China entry — CountryCode = "Chinese". Sending
        # country=CN to the IoT endpoint yields errno=1202.
        ("CN", "qas-gl-cn-appapi.tineco.com", "TEK",   "Chinese", "Asia/Shanghai",     "ZH_CN"),
        ("IE", "qas-gl-ie-api.tineco.com",    "TEKWW", "IE",      "Europe/London",     "EN_US"),
        ("GB", "qas-gl-gb-api.tineco.com",    "TEKWW", "GB",      "Europe/London",     "EN_US"),
        ("US", "qas-gl-us-api.tineco.com",    "TEKWW", "US",      "America/New_York",  "EN_US"),
        ("DE", "qas-gl-de-api.tineco.com",    "TEKWW", "DE",      "Europe/Berlin",     "EN_US"),
        ("HK", "qas-gl-hk-api.tineco.com",    "TEKWW", "HK",      "Asia/Hong_Kong",    "ZH_HK"),
        ("JP", "qas-gl-jp-api.tineco.com",    "TEKWW", "JP",      "Asia/Tokyo",        "JA_JP"),
    ],
)
def test_region_constants(region, expect_host, expect_org, expect_country, expect_tz, expect_lang, offline_dc_lookup):
    """REST host, IoT org/country, timezone, and language must match the region."""
    client = TinecoClient(region=region)

    assert client.REST_API_HOST == expect_host, (
        f"REST host mismatch for region={region}: got {client.REST_API_HOST}, "
        f"expected {expect_host}"
    )
    assert client.AUTH_TIMEZONE == expect_tz, (
        f"Timezone mismatch for region={region}: got {client.AUTH_TIMEZONE}"
    )
    assert client.language == expect_lang, (
        f"Default language mismatch for region={region}: got {client.language}"
    )
    assert client.IOT_ORG == expect_org, (
        f"IoT org mismatch for region={region}: got {client.IOT_ORG}"
    )
    assert client.IOT_COUNTRY == expect_country, (
        f"IoT country mismatch for region={region}: got {client.IOT_COUNTRY}"
    )


def test_cn_appapi_host_is_distinct_from_global_api(offline_dc_lookup):
    """Regression lock: the CN suffix must be ``-appapi.tineco.com``, not
    ``-api.tineco.com``. Confirmed against the decompiled
    ``BaseTinecoLifeApplication.java`` ``domainNameSuffixChina`` constant."""
    cn = TinecoClient(region="CN")
    ww = TinecoClient(region="IE")

    assert "appapi" in cn.REST_API_HOST
    assert "appapi" not in ww.REST_API_HOST


def test_caller_supplied_language_overrides_region_default(offline_dc_lookup):
    """The CN→ZH_CN default must not override an explicit language=EN_US.
    Reverse case: IE default of EN_US must not override an explicit ZH_CN."""
    cn_en = TinecoClient(region="CN", language="EN_US")
    ie_zh = TinecoClient(region="IE", language="ZH_CN")

    assert cn_en.language == "EN_US"
    assert ie_zh.language == "ZH_CN"


def test_dc_fallback_for_known_regions(offline_dc_lookup):
    """REGION_DC_MAP fallback used when the DC lookup fails (which is what
    our mock forces). Ensures we never silently fall back to "eu" for a
    region that lives in a different datacenter."""
    assert TinecoClient(region="CN")._resolve_iot_datacenter() == "cn"
    assert TinecoClient(region="US")._resolve_iot_datacenter() == "na"
    assert TinecoClient(region="JP")._resolve_iot_datacenter() == "as"
    # IE is not in REGION_DC_MAP so falls back to "eu" — that's intentional.
    assert TinecoClient(region="IE")._resolve_iot_datacenter() == "eu"


def test_construction_does_no_network_io():
    """Regression lock for the HA event-loop blocking-call warning.

    ``TinecoClient.__init__`` used to call ``_resolve_iot_datacenter()``, which
    does a blocking ``requests`` GET. Home Assistant constructs the client on
    the event loop, so that tripped ``homeassistant.util.loop`` detection
    (``Detected blocking call to load_verify_locations``). Construction must
    stay pure; the lookup happens lazily on first IoT-endpoint use.
    """
    with patch("custom_components.tineco.tineco_client_impl.requests.Session.get") as m:
        m.side_effect = AssertionError("DC lookup must not run during __init__")
        client = TinecoClient(region="IE")

    assert m.call_count == 0, "constructor performed HTTP I/O"
    assert client._dc is None, "datacenter should be unresolved until first use"


def test_dc_resolved_lazily_and_cached(offline_dc_lookup):
    """First IoT-endpoint read resolves the DC; later reads reuse the cache."""
    client = TinecoClient(region="US")
    assert offline_dc_lookup.call_count == 0

    assert client.IOT_API_BASE == (
        "https://api-ngiot.dc-na.ww.ecouser.net/api/iot/endpoint/control"
    )
    first_calls = offline_dc_lookup.call_count
    assert first_calls > 0, "first endpoint read should trigger the lookup"

    assert client.IOT_LOGIN_ENDPOINT == "https://api-base.dc-na.ww.ecouser.net/api/users/user.do"
    assert offline_dc_lookup.call_count == first_calls, "DC lookup was not cached"


def test_cn_endpoints_use_cn_vendor(offline_dc_lookup):
    """CN builds ``dc-cn.cn`` hosts; WW builds ``dc-<dc>.ww``."""
    assert "dc-cn.cn.ecouser.net" in TinecoClient(region="CN").IOT_LOGIN_ENDPOINT
    assert "dc-eu.ww.ecouser.net" in TinecoClient(region="IE").IOT_LOGIN_ENDPOINT
