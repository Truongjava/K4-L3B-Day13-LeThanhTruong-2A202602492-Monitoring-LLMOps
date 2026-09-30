from app.pii import scrub_text


def test_scrub_email() -> None:
    out = scrub_text("Email me at student@vinuni.edu.vn")
    assert "student@" not in out
    assert "REDACTED_EMAIL" in out


def test_scrub_common_vietnamese_phone_formats() -> None:
    phone_numbers = (
        "0901234567",
        "090 123 4567",
        "090.123.4567",
        "090-123-4567",
        "+84 90 123 4567",
    )

    for phone_number in phone_numbers:
        out = scrub_text(f"Contact: {phone_number}")
        assert phone_number not in out
        assert "REDACTED_PHONE_VN" in out


def test_scrub_cccd() -> None:
    out = scrub_text("CCCD của tôi là 001203012345 nhé")
    assert "001203012345" not in out
    assert "REDACTED_CCCD" in out


def test_scrub_credit_card() -> None:
    for card in ("4111 1111 1111 1111", "4111111111111111"):
        out = scrub_text(f"Thẻ: {card}")
        assert card not in out
        assert "REDACTED_CREDIT_CARD" in out


def test_scrub_passport() -> None:
    out = scrub_text("Passport B1234567 của tôi")
    assert "B1234567" not in out
    assert "REDACTED_PASSPORT" in out


def test_scrub_address_keywords() -> None:
    out = scrub_text("Tôi ở 123 đường Láng")
    assert "đường Láng" not in out
    assert "REDACTED_ADDRESS_VN" in out
