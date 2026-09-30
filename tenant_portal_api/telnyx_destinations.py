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

    Defaults to US + CA when unset (trial-safe). Production should set::

        TELNYX_OUTBOUND_DESTINATIONS=all          -> the full country list
        TELNYX_OUTBOUND_DESTINATIONS=US,CA,PK     -> exactly these
    """
    raw = (os.environ.get("TELNYX_OUTBOUND_DESTINATIONS") or "").strip()
    if not raw:
        return ["US", "CA"]
    if raw.lower() == "all":
        return list(TELNYX_DEFAULT_OUTBOUND_DESTINATION_COUNTRIES)
    codes = [c.strip().upper() for c in raw.split(",") if c.strip()]
    return codes or ["US", "CA"]


# Longest-prefix first. NANP (+1) maps to US|CA jointly (area-code precision needs phonenumbers).
_E164_PREFIX_TO_COUNTRIES: tuple[tuple[str, frozenset[str]], ...] = tuple(
    sorted(
        (
            ("1", frozenset({"US", "CA", "PR", "VI", "GU", "AS", "MP", "BM", "BB", "BS", "JM", "TT", "AG", "AI", "DM", "GD", "KN", "LC", "VC", "KY", "TC", "VG"})),
            ("7", frozenset({"RU", "KZ"})),
            ("20", frozenset({"EG"})),
            ("27", frozenset({"ZA"})),
            ("30", frozenset({"GR"})),
            ("31", frozenset({"NL"})),
            ("32", frozenset({"BE"})),
            ("33", frozenset({"FR"})),
            ("34", frozenset({"ES"})),
            ("36", frozenset({"HU"})),
            ("39", frozenset({"IT"})),
            ("40", frozenset({"RO"})),
            ("41", frozenset({"CH"})),
            ("43", frozenset({"AT"})),
            ("44", frozenset({"GB"})),
            ("45", frozenset({"DK"})),
            ("46", frozenset({"SE"})),
            ("47", frozenset({"NO"})),
            ("48", frozenset({"PL"})),
            ("49", frozenset({"DE"})),
            ("51", frozenset({"PE"})),
            ("52", frozenset({"MX"})),
            ("53", frozenset({"CU"})),
            ("54", frozenset({"AR"})),
            ("55", frozenset({"BR"})),
            ("56", frozenset({"CL"})),
            ("57", frozenset({"CO"})),
            ("58", frozenset({"VE"})),
            ("60", frozenset({"MY"})),
            ("61", frozenset({"AU"})),
            ("62", frozenset({"ID"})),
            ("63", frozenset({"PH"})),
            ("64", frozenset({"NZ"})),
            ("65", frozenset({"SG"})),
            ("66", frozenset({"TH"})),
            ("81", frozenset({"JP"})),
            ("82", frozenset({"KR"})),
            ("84", frozenset({"VN"})),
            ("86", frozenset({"CN"})),
            ("90", frozenset({"TR"})),
            ("91", frozenset({"IN"})),
            ("92", frozenset({"PK"})),
            ("93", frozenset({"AF"})),
            ("94", frozenset({"LK"})),
            ("95", frozenset({"MM"})),
            ("98", frozenset({"IR"})),
            ("211", frozenset({"SS"})),
            ("212", frozenset({"MA"})),
            ("213", frozenset({"DZ"})),
            ("216", frozenset({"TN"})),
            ("218", frozenset({"LY"})),
            ("220", frozenset({"GM"})),
            ("221", frozenset({"SN"})),
            ("223", frozenset({"ML"})),
            ("224", frozenset({"GN"})),
            ("225", frozenset({"CI"})),
            ("226", frozenset({"BF"})),
            ("227", frozenset({"NE"})),
            ("228", frozenset({"TG"})),
            ("229", frozenset({"BJ"})),
            ("230", frozenset({"MU"})),
            ("231", frozenset({"LR"})),
            ("232", frozenset({"SL"})),
            ("233", frozenset({"GH"})),
            ("234", frozenset({"NG"})),
            ("235", frozenset({"TD"})),
            ("236", frozenset({"CF"})),
            ("237", frozenset({"CM"})),
            ("238", frozenset({"CV"})),
            ("239", frozenset({"ST"})),
            ("240", frozenset({"GQ"})),
            ("241", frozenset({"GA"})),
            ("242", frozenset({"CG"})),
            ("243", frozenset({"CD"})),
            ("244", frozenset({"AO"})),
            ("245", frozenset({"GW"})),
            ("248", frozenset({"SC"})),
            ("249", frozenset({"SD"})),
            ("250", frozenset({"RW"})),
            ("251", frozenset({"ET"})),
            ("252", frozenset({"SO"})),
            ("253", frozenset({"DJ"})),
            ("254", frozenset({"KE"})),
            ("255", frozenset({"TZ"})),
            ("256", frozenset({"UG"})),
            ("257", frozenset({"BI"})),
            ("258", frozenset({"MZ"})),
            ("260", frozenset({"ZM"})),
            ("261", frozenset({"MG"})),
            ("262", frozenset({"RE", "YT"})),
            ("263", frozenset({"ZW"})),
            ("264", frozenset({"NA"})),
            ("265", frozenset({"MW"})),
            ("266", frozenset({"LS"})),
            ("267", frozenset({"BW"})),
            ("268", frozenset({"SZ"})),
            ("269", frozenset({"KM"})),
            ("290", frozenset({"SH"})),
            ("291", frozenset({"ER"})),
            ("297", frozenset({"AW"})),
            ("298", frozenset({"FO"})),
            ("299", frozenset({"GL"})),
            ("350", frozenset({"GI"})),
            ("351", frozenset({"PT"})),
            ("352", frozenset({"LU"})),
            ("353", frozenset({"IE"})),
            ("354", frozenset({"IS"})),
            ("355", frozenset({"AL"})),
            ("356", frozenset({"MT"})),
            ("357", frozenset({"CY"})),
            ("358", frozenset({"FI"})),
            ("359", frozenset({"BG"})),
            ("370", frozenset({"LT"})),
            ("371", frozenset({"LV"})),
            ("372", frozenset({"EE"})),
            ("373", frozenset({"MD"})),
            ("374", frozenset({"AM"})),
            ("375", frozenset({"BY"})),
            ("376", frozenset({"AD"})),
            ("377", frozenset({"MC"})),
            ("378", frozenset({"SM"})),
            ("380", frozenset({"UA"})),
            ("381", frozenset({"RS"})),
            ("382", frozenset({"ME"})),
            ("383", frozenset({"XK"})),
            ("385", frozenset({"HR"})),
            ("386", frozenset({"SI"})),
            ("387", frozenset({"BA"})),
            ("389", frozenset({"MK"})),
            ("420", frozenset({"CZ"})),
            ("421", frozenset({"SK"})),
            ("423", frozenset({"LI"})),
            ("500", frozenset({"FK"})),
            ("501", frozenset({"BZ"})),
            ("502", frozenset({"GT"})),
            ("503", frozenset({"SV"})),
            ("504", frozenset({"HN"})),
            ("505", frozenset({"NI"})),
            ("506", frozenset({"CR"})),
            ("507", frozenset({"PA"})),
            ("508", frozenset({"PM"})),
            ("509", frozenset({"HT"})),
            ("590", frozenset({"GP"})),
            ("591", frozenset({"BO"})),
            ("592", frozenset({"GY"})),
            ("593", frozenset({"EC"})),
            ("594", frozenset({"GF"})),
            ("595", frozenset({"PY"})),
            ("596", frozenset({"MQ"})),
            ("597", frozenset({"SR"})),
            ("598", frozenset({"UY"})),
            ("599", frozenset({"CW", "BQ"})),
            ("670", frozenset({"TL"})),
            ("672", frozenset({"NF"})),
            ("673", frozenset({"BN"})),
            ("674", frozenset({"NR"})),
            ("675", frozenset({"PG"})),
            ("676", frozenset({"TO"})),
            ("677", frozenset({"SB"})),
            ("678", frozenset({"VU"})),
            ("679", frozenset({"FJ"})),
            ("680", frozenset({"PW"})),
            ("681", frozenset({"WF"})),
            ("682", frozenset({"CK"})),
            ("683", frozenset({"NU"})),
            ("685", frozenset({"WS"})),
            ("686", frozenset({"KI"})),
            ("687", frozenset({"NC"})),
            ("688", frozenset({"TV"})),
            ("689", frozenset({"PF"})),
            ("690", frozenset({"TK"})),
            ("691", frozenset({"FM"})),
            ("692", frozenset({"MH"})),
            ("850", frozenset({"KP"})),
            ("852", frozenset({"HK"})),
            ("853", frozenset({"MO"})),
            ("855", frozenset({"KH"})),
            ("856", frozenset({"LA"})),
            ("880", frozenset({"BD"})),
            ("886", frozenset({"TW"})),
            ("960", frozenset({"MV"})),
            ("961", frozenset({"LB"})),
            ("962", frozenset({"JO"})),
            ("963", frozenset({"SY"})),
            ("964", frozenset({"IQ"})),
            ("965", frozenset({"KW"})),
            ("966", frozenset({"SA"})),
            ("967", frozenset({"YE"})),
            ("968", frozenset({"OM"})),
            ("970", frozenset({"PS"})),
            ("971", frozenset({"AE"})),
            ("972", frozenset({"IL"})),
            ("973", frozenset({"BH"})),
            ("974", frozenset({"QA"})),
            ("975", frozenset({"BT"})),
            ("976", frozenset({"MN"})),
            ("977", frozenset({"NP"})),
            ("992", frozenset({"TJ"})),
            ("993", frozenset({"TM"})),
            ("994", frozenset({"AZ"})),
            ("995", frozenset({"GE"})),
            ("996", frozenset({"KG"})),
            ("998", frozenset({"UZ"})),
        ),
        key=lambda item: len(item[0]),
        reverse=True,
    )
)


def e164_destination_countries(e164: str) -> frozenset[str]:
    """Best-effort ISO country set for an E.164 number (NANP → US/CA family)."""
    digits = "".join(ch for ch in str(e164 or "") if ch.isdigit())
    if not digits:
        return frozenset()
    for prefix, countries in _E164_PREFIX_TO_COUNTRIES:
        if digits.startswith(prefix):
            return countries
    return frozenset()


def assert_outbound_destination_allowed(e164: str, allowed_destinations: list[str] | None) -> str | None:
    """Return matched destination ISO code, or raise if not allowed.

    Empty allowlist skips the platform gate (Telnyx OVP still enforces). Unknown calling
    codes fail closed so we never silently dial unsupported destinations.
    """
    from tenant_portal_api.telephony_errors import TelephonyError, TelephonyErrorCode

    allowed = {
        str(item).strip().upper()
        for item in (allowed_destinations or [])
        if str(item).strip()
    }
    if not allowed:
        return None

    countries = e164_destination_countries(e164)
    if not countries:
        raise TelephonyError(
            status=400,
            code=TelephonyErrorCode.OUTBOUND_DESTINATION_DISABLED,
            message=(
                f"Cannot determine destination country for {e164}. "
                "Use a full E.164 number in a supported country."
            ),
            detail={"to_number": e164, "allowed_destinations": sorted(allowed)},
        )
    overlap = countries & allowed
    if not overlap:
        raise TelephonyError(
            status=403,
            code=TelephonyErrorCode.OUTBOUND_DESTINATION_DISABLED,
            message=(
                f"Outbound calls to this destination are not enabled "
                f"(number country candidates: {', '.join(sorted(countries))}). "
                "Widen TELNYX_OUTBOUND_DESTINATIONS and the Telnyx outbound voice profile."
            ),
            detail={
                "to_number": e164,
                "destination_candidates": sorted(countries),
                "allowed_destinations": sorted(allowed),
            },
        )
    # Prefer a stable primary when multiple candidates (e.g. NANP).
    for preferred in ("US", "CA", "PK", "GB"):
        if preferred in overlap:
            return preferred
    return sorted(overlap)[0]
