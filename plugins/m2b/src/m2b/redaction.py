"""Credentials do not leave a session's text or a commit subject, as far as a pattern finds them.

What m2b reads of the owner's work outside the store passes through ``redact`` before it reaches a
model, a note or the archive: the prompts the core reads from Claude Code's transcripts
(``sessions``), and the prompts, answers and commit subjects of the worklog add-on. The worklog
imports this module from the core, so that the patterns exist once. It works on patterns: a value
after a word such as password or token, the value of an assignment whose name holds such a word
(``PGPASSWORD=``, ``SECRET_KEY:``, ``AccountKey=``), the password in a URL and after ``-u`` or
``--user``, a credential after ``Bearer`` or ``Basic``, an AWS access key id, and long tokens of
mixed letters and digits. It misses what matches none of them, so a text can still carry a secret in
words of its own, or one of several words, of which only the first goes.
"""

from __future__ import annotations

import re

REDACTED = "[removed]"

# Not \b before the keyword: DB_PASSWORD and client_secret have a letter or "_" in front.
_KEYWORD = r"(?i)(?<![a-z])(secret|client[ _-]?id|password|passwort|kennwort|passwd|pwd|pw|token|api[ _-]?key)"
# Up to four words between the keyword and its value: "the password for the db is hunter2".
_BETWEEN = r"((?:\s+[\w.-]+){0,4}?[\"']?\s*(?:[:=]|\b(?:is|ist|lautet)\b\s*[:=]?)\s*)"
_SECRET = re.compile(_KEYWORD + r"\b" + _BETWEEN + r"(\S+)")
# The scheme as HTTP writes it, followed by a value shaped like a credential, not by a word.
_SCHEME = re.compile(r"\b(Bearer|Basic)\s+(?=[\w.~+/=-]*[\d+/=])[\w.~+/=-]{6,}")
_LONG_TOKEN = re.compile(r"\b(?=[A-Za-z0-9_\-]*[A-Za-z])(?=[A-Za-z0-9_\-]*\d)[A-Za-z0-9_\-]{24,}\b")
# A base64 key holds "/" and "+" too, and upper and lower case letters and digits. It never starts
# inside a path or a word and never ends before a file extension; one with "/" whose parts include
# a word in lower case only is a relative path (`apps/Web3Portal/src`), not a key.
_BASE64_CANDIDATE = re.compile(
    r"(?<![\w/.~+-])(?=[\w+/=-]*[A-Z])(?=[\w+/=-]*[a-z])(?=[\w+/=-]*\d)[A-Za-z0-9][\w+/=-]{23,}(?![\w/+]|\.\w)"
)
_LOWER_WORD = re.compile(r"[a-z]+")
# ``scheme://user:password@host``: the user stays, as it says whose access it was. The scheme's
# length is bounded, so a long run of word characters is not read again from each of its parts.
# A password with "@" in it goes whole: the host starts after the last "@" before a "/".
_URL_PASSWORD = re.compile(r"\b([a-z][a-z0-9+.-]{1,30}://[^\s/:@]*:)[^\s/]+(?=@)", re.I)
# ``curl -u name:password``, ``-uname:password``, ``--user name:password`` and ``--user=...``.
# Without the colon there is no password in it: ``git push -u origin`` and ``sort -u`` stay. Two
# numbers are a user and a group id, as ``docker run -u 1000:1000`` writes them.
_USER_OPTION = re.compile(r"(?<![\w-])((?:-u\s*|--user(?:\s+|=))(?!\d+:\d+(?:\s|\Z))[^\s:]+:)\S+")
# AWS access key ids, long-term and temporary: twenty characters, too short for the long token.
_AWS_KEY_ID = re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")
# The name of an assignment as an environment, a config file or a connection string writes it,
# with its ":" or "=". Whether the name is a credential's is decided on the name alone (below),
# which keeps this pattern to one pass over a long run of word characters; the value is read
# apart, so a name that is none does not swallow the assignment after it
# ("AccountName=acme;AccountKey=..."). The value stands on the name's line: a key with nothing
# after it, as YAML writes a section, does not take the next line's key for its value.
_ASSIGNED_NAME = re.compile(r"(?<![\w-])([\w-]+)[\"']?[ \t]*[:=][ \t]*")
_VALUE = re.compile(r"\S+")
# The words a name holds when its value is a credential: PGPASSWORD, SECRET_KEY, AccountKey,
# aws_secret_access_key. After the word the name ends, or goes on past "_" or "-" or with digits,
# so "secretary: Dana" and "tokenizer=bert" stay; "pass" counts only where no letter stands before
# it, so "bypass=1" stays.
_CREDENTIAL_NAME = re.compile(
    r"(?i)(?:passwor[dt]|passwd|passphrase|kennwort|pwd|secret|token|credentials?"
    r"|(?:api|access|account|private|secret|shared|signing|auth)[_-]?key"
    r"|(?<![a-z])pass)(?=[_-]|\d*\Z)"
)


def redact(text: str) -> str:
    """``text`` without the credentials a pattern finds; each is replaced by ``[removed]``."""
    # The forms with a fixed place for the secret go first: "pw" after ``-u admin:`` is a password
    # there, and read as the keyword it would take the next word for its value.
    text = _URL_PASSWORD.sub(lambda m: f"{m.group(1)}{REDACTED}", text)
    text = _USER_OPTION.sub(lambda m: f"{m.group(1)}{REDACTED}", text)
    text = _AWS_KEY_ID.sub(REDACTED, text)
    text = _SCHEME.sub(lambda m: f"{m.group(1)} {REDACTED}", text)
    text = _without_assigned_credentials(text)
    text = _SECRET.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", text)
    return _LONG_TOKEN.sub(REDACTED, _BASE64_CANDIDATE.sub(_base64_key, text))


def _without_assigned_credentials(text: str) -> str:
    """``text`` with the value of each assignment to a credential's name replaced; the name stays."""
    parts, kept_to = [], 0
    for name in _ASSIGNED_NAME.finditer(text):
        if name.start() < kept_to or not _CREDENTIAL_NAME.search(name.group(1)):
            continue
        value = _VALUE.match(text, name.end())
        inner = _ASSIGNED_NAME.match(text, name.end())
        # "credentials: password: hunter2": the inner assignment is the one with the secret.
        if value is None or (inner is not None and _CREDENTIAL_NAME.search(inner.group(1))):
            continue
        parts += [text[kept_to : name.end()], REDACTED]
        kept_to = value.end()
    return "".join([*parts, text[kept_to:]])


def _base64_key(match: re.Match[str]) -> str:
    token = match.group(0)
    is_path = "/" in token and any(_LOWER_WORD.fullmatch(part) for part in token.split("/"))
    return token if is_path else REDACTED
