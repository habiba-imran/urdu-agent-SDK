from control_plane.sentry_scrub import before_send


def test_sentry_scrub_redacts_auth_headers_and_secret_keys():
    event = {
        "request": {
            "headers": {
                "Authorization": "Bearer secret-token",
                "X-Signature": "abc",
                "Content-Type": "application/json",
            },
            "cookies": {"session": "x"},
            "data": {"hmac_secret": "raw", "agent_id": "a1"},
        },
        "extra": {"tenant_secret": "nope", "room": "r1"},
    }
    out = before_send(event, None)
    assert out is not None
    assert out["request"]["headers"]["Authorization"] == "[redacted]"
    assert out["request"]["headers"]["X-Signature"] == "[redacted]"
    assert out["request"]["headers"]["Content-Type"] == "application/json"
    assert out["request"]["cookies"] == "[redacted]"
    assert out["request"]["data"]["hmac_secret"] == "[redacted]"
    assert out["request"]["data"]["agent_id"] == "a1"
    assert out["extra"]["tenant_secret"] == "[redacted]"
    assert out["extra"]["room"] == "r1"
