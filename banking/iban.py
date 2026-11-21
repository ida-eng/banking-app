"""IBAN helpers: normalisation, ISO 13616 mod-97 validation and generation.

Pure Python with no Django imports, so it can be tested on its own.
"""
import random
import re
import string

# Expected IBAN length for SEPA countries and the Western Balkans.
IBAN_LENGTHS = {
    "AL": 28, "AD": 24, "AT": 20, "BE": 16, "BG": 22, "CH": 21, "CY": 28, "CZ": 24,
    "DE": 22, "DK": 18, "EE": 20, "ES": 24, "FI": 18, "FR": 27, "GB": 22, "GR": 27,
    "HR": 21, "HU": 28, "IE": 22, "IS": 26, "IT": 27, "LI": 21, "LT": 20, "LU": 20,
    "LV": 21, "MC": 27, "ME": 22, "MK": 19, "MT": 31, "NL": 18, "NO": 15, "PL": 28,
    "PT": 25, "RO": 24, "RS": 22, "SE": 24, "SI": 19, "SK": 24, "SM": 27, "XK": 20,
}


class IBANError(ValueError):
    pass


def normalize(value: str) -> str:
    """Remove spaces and dashes and upper-case: ' al47 2121-1009 ' -> 'AL4721211009'."""
    return re.sub(r"[\s-]+", "", str(value or "")).upper()


def _mod97(text: str) -> int:
    digits = "".join(str(int(ch, 36)) for ch in text)
    remainder = 0
    for i in range(0, len(digits), 9):
        remainder = int(str(remainder) + digits[i:i + 9]) % 97
    return remainder


def validate(value: str) -> str:
    """Return the normalised IBAN or raise IBANError with a human-readable reason."""
    iban = normalize(value)
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]+", iban):
        raise IBANError("An IBAN starts with a 2-letter country code and 2 check digits.")
    country = iban[:2]
    expected = IBAN_LENGTHS.get(country)
    if expected is None:
        raise IBANError(f"Transfers to {country} are not supported.")
    if len(iban) != expected:
        raise IBANError(f"A {country} IBAN has {expected} characters, this one has {len(iban)}.")
    if _mod97(iban[4:] + iban[:4]) != 1:
        raise IBANError("The check digits don't match. Please check the IBAN for typos.")
    return iban


def is_valid(value: str) -> bool:
    try:
        validate(value)
        return True
    except IBANError:
        return False


def make(country: str, bban: str) -> str:
    """Build a valid IBAN from a country code and BBAN by computing the check digits."""
    country, bban = country.upper(), normalize(bban)
    check = 98 - _mod97(bban + country + "00")
    return f"{country}{check:02d}{bban}"


def generate_albanian(rng: random.Random | None = None) -> str:
    """Random, checksum-valid Albanian IBAN for demo accounts (fictional bank code 999)."""
    rng = rng or random.SystemRandom()
    branch = "".join(rng.choice(string.digits) for _ in range(4))
    account = "".join(rng.choice(string.digits) for _ in range(16))
    bank_branch = "999" + branch
    # Albanian BBAN: 8-digit bank/branch code (last digit is a control digit) + 16-char account
    control = str(sum(int(d) * w for d, w in zip(bank_branch, (9, 7, 3, 1, 9, 7, 3))) % 10)
    return make("AL", bank_branch + control + account)


def pretty(iban: str) -> str:
    """Group in blocks of four for display: AL47 2121 1009 0000 ..."""
    iban = normalize(iban)
    return " ".join(iban[i:i + 4] for i in range(0, len(iban), 4))
