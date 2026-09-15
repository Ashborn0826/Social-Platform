from app.auth.passwords import hash_password, verify_password


def test_hash_then_verify_correct_password():
    h = hash_password("CorrectHorse9")
    assert verify_password("CorrectHorse9", h) is True


def test_verify_rejects_wrong_password():
    h = hash_password("CorrectHorse9")
    assert verify_password("WrongPassword99", h) is False


def test_hash_is_different_each_time():
    """Salt is random; same plaintext produces different hashes."""
    h1 = hash_password("CorrectHorse9")
    h2 = hash_password("CorrectHorse9")
    assert h1 != h2
    assert verify_password("CorrectHorse9", h1)
    assert verify_password("CorrectHorse9", h2)


def test_verify_rejects_malformed_hash():
    assert verify_password("anything", "not-a-valid-bcrypt-hash") is False


def test_bcrypt_hash_length_is_60():
    h = hash_password("anything")
    assert len(h) == 60