import bcrypt

# Cost factor 12 = ~250ms per hash on modern hardware.
# Tuning: lower = faster login but weaker offline brute-force resistance.
BCRYPT_ROUNDS = 12


def hash_password(plain: str) -> str:
    """Hash a plaintext password with bcrypt (cost 12). Returns the bcrypt hash string."""
    return bcrypt.hashpw(
        plain.encode("utf-8"), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    ).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time check of plaintext against a bcrypt hash. Returns False on malformed hash."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False