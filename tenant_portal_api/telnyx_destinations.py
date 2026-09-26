"""Default Telnyx outbound destination country codes.

Source notes:
- Telnyx outbound voice profiles default to US/CA-only whitelisting unless
  additional destinations are added.
- Telnyx outbound voice profile API expects ISO 3166-1 alpha-2 country codes.
- This list is based on Telnyx's published international coverage list and was
  refreshed on 2026-08-05.
"""

from __future__ import annotations

import os

TELNYX_DEFAULT_OUTBOUND_DESTINATION_COUNTRIES: tuple[str, ...] = (
    "AE",
    "AG",
    "AI",
    "AL",
    "AM",
    "AO",
    "AR",
    "AT",
    "AU",
    "BA",
    "BB",
    "BD",
    "BE",
    "BF",
    "BG",
    "BJ",
    "BM",
    "BN",
    "BO",
    "BR",
    "BS",
    "BW",
    "BZ",
    "CA",
    "CH",
    "CL",
    "CM",
    "CN",
    "CO",
    "CR",
    "CW",
    "CY",
    "CZ",
    "DE",
    "DK",
    "DM",
    "DO",
    "DZ",
    "EC",
    "EE",
    "EG",
    "ES",
    "ET",
    "FI",
    "FR",
    "GB",
    "GD",
    "GE",
    "GF",
    "GH",
    "GP",
    "GR",
    "GT",
    "HK",
    "HN",
    "HR",
    "HU",
    "ID",
    "IE",
    "IL",
    "IS",
    "IT",
    "JM",
    "JO",
    "JP",
    "KE",
    "KG",
    "KH",
    "KN",
    "KR",
    "KW",
    "KY",
    "KZ",
    "LB",
    "LC",
    "LK",
    "LT",
    "LU",
    "LV",
    "MA",
    "MC",
    "MD",
    "ME",
    "MK",
    "MM",
    "MO",
    "MQ",
    "MT",
    "MU",
    "MX",
    "MY",
    "NG",
    "NI",
    "NL",
    "NO",
    "NP",
    "NZ",
    "OM",
    "PA",
    "PE",
    "PH",
    "PK",
    "PL",
    "PR",
    "PT",
    "PY",
    "QA",
    "RE",
    "RO",
    "RS",
    "SA",
    "SC",
    "SE",
    "SG",
    "SI",
    "SK",
    "SV",
    "TC",
    "TH",
    "TN",
    "TT",
    "TW",
    "TZ",
    "UA",
    "UG",
    "US",
    "UY",
    "VC",
    "VE",
    "VG",
    "VI",
    "VN",
    "YT",
    "ZA",
    "ZW",
)


def default_telnyx_outbound_destinations() -> list[str]:
    """Allowed outbound destination countries for a tenant's Telnyx voice profile.

    Defaults to US + CA, which is what a standard or trial Telnyx account can dial without
    extra enablement. Note what that excludes: **PK is not in this list**, so outbound PSTN
    to Pakistan — this product's primary market — is refused by the provider until the list
    is widened. tests/test_telephony_outbound_destinations.py asserts the full
    TELNYX_DEFAULT_OUTBOUND_DESTINATION_COUNTRIES list (including PK) and has never run
    (F-H1), so the two have disagreed silently.

    Widening is an account-level decision, not a code one — an account that has not been
    enabled for a destination will simply have the API call rejected — so it is configurable
    rather than changed underneath whoever is running this:

        TELNYX_OUTBOUND_DESTINATIONS=all          -> the full country list
        TELNYX_OUTBOUND_DESTINATIONS=US,CA,PK     -> exactly these
        unset                                     -> US, CA (unchanged)
    """
    raw = (os.environ.get("TELNYX_OUTBOUND_DESTINATIONS") or "").strip()
    if not raw:
        return ["US", "CA"]
    if raw.lower() == "all":
        return list(TELNYX_DEFAULT_OUTBOUND_DESTINATION_COUNTRIES)
    codes = [c.strip().upper() for c in raw.split(",") if c.strip()]
    return codes or ["US", "CA"]
