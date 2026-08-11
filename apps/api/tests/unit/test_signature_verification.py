"""Signature verification is pure computation, so it needs no services.

These are the security-critical tests in this slice: every one of them
describes a way an attacker gets in if the check is wrong.
"""

import hashlib
import hmac

from hotelagent.adapters.channel.cloud_api import verify_signature, verify_subscription

SECRET = "an-app-secret"
BODY = b'{"entry":[{"changes":[]}]}'


def _sign(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_a_correctly_signed_body_is_accepted() -> None:
    assert verify_signature(raw_body=BODY, header=_sign(BODY), app_secret=SECRET) is True


def test_a_tampered_body_is_rejected() -> None:
    """The signature covers the body. Change one byte and it must not match."""
    header = _sign(BODY)
    tampered = BODY.replace(b"entry", b"entrY")

    assert verify_signature(raw_body=tampered, header=header, app_secret=SECRET) is False


def test_a_signature_from_the_wrong_secret_is_rejected() -> None:
    assert (
        verify_signature(raw_body=BODY, header=_sign(BODY, "not-our-secret"), app_secret=SECRET)
        is False
    )


def test_a_missing_signature_header_is_rejected() -> None:
    assert verify_signature(raw_body=BODY, header=None, app_secret=SECRET) is False


def test_a_malformed_signature_header_is_rejected() -> None:
    """No "sha256=" prefix, and a bare digest, are both refused."""
    assert verify_signature(raw_body=BODY, header="garbage", app_secret=SECRET) is False
    raw_digest = _sign(BODY).removeprefix("sha256=")
    assert verify_signature(raw_body=BODY, header=raw_digest, app_secret=SECRET) is False


def test_an_empty_secret_fails_closed() -> None:
    """Unconfigured must never mean "accept everything" — that would leave the
    endpoint wide open on any deployment missing the variable."""
    assert verify_signature(raw_body=BODY, header=_sign(BODY, ""), app_secret="") is False


def test_subscription_handshake_echoes_the_challenge() -> None:
    result = verify_subscription(
        mode="subscribe", token="tok", challenge="12345", verify_token="tok"
    )
    assert result == "12345"


def test_subscription_handshake_rejects_a_wrong_token() -> None:
    assert (
        verify_subscription(mode="subscribe", token="nope", challenge="12345", verify_token="tok")
        is None
    )


def test_subscription_handshake_rejects_an_empty_configured_token() -> None:
    assert (
        verify_subscription(mode="subscribe", token="", challenge="12345", verify_token="") is None
    )
