from typing import Final, Literal
from urllib.parse import urlsplit

AuthorityUrlError = Literal["invalid", "unofficial"]

OFFICIAL_AUTHORITY_HOSTS: Final = frozenset(
    {
        "azlp.mk",
        "finki.ukim.mk",
        "portal.mdt.gov.mk",
        "slvesnik.com.mk",
        "ukim.edu.mk",
    }
)


def authority_url_error(value: str) -> AuthorityUrlError | None:
    if (
        "\\" in value
        or not value.isprintable()
        or any(character.isspace() for character in value)
    ):
        return "invalid"
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return "invalid"
    if (
        parsed.scheme != "https"
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or not parsed.netloc.isascii()
        or parsed.query
        or parsed.fragment
    ):
        return "invalid"
    hostname = parsed.hostname.lower()
    if parsed.netloc.lower() != hostname:
        return "invalid"
    if hostname not in OFFICIAL_AUTHORITY_HOSTS:
        return "unofficial"
    return None
