"""PCGamingWiki API client.

Uses the MediaWiki API exposed by PCGamingWiki to look up the configuration
file paths for a given game title.
"""

from __future__ import annotations

import glob as _glob_module
import re
import os
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import json

import unicodedata

try:
    import requests  # type: ignore
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

try:
    from bs4 import BeautifulSoup  # type: ignore
except ImportError:  # pragma: no cover
    BeautifulSoup = None  # type: ignore

_BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BUNDLED_CACHE_FILE = os.path.join(_BASE_DIR, "cache", "wiki_cache.json")
_USER_DATA_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~/.local/share")),
    "GameTuner",
)
_CACHE_DIR = _USER_DATA_DIR
_CACHE_FILE = os.path.join(_CACHE_DIR, "wiki_cache.json")
_CONSENT_FILE = os.path.join(_CACHE_DIR, "wiki_download_consent.json")

# PCGamingWiki Cargo API endpoint
_API_URL = "https://www.pcgamingwiki.com/w/api.php"
_WIKI_BASE = "https://www.pcgamingwiki.com/wiki/"

# Map common path tokens to OS-specific directories
_PATH_TOKENS: dict = {
    "%USERPROFILE%": os.path.expanduser("~"),
    "%APPDATA%": os.environ.get("APPDATA", os.path.expanduser("~/.config")),
    "%LOCALAPPDATA%": os.environ.get("LOCALAPPDATA", os.path.expanduser("~/.local/share")),
    "%PUBLIC%": os.environ.get("PUBLIC", os.path.expanduser("~")),
    "$HOME": os.path.expanduser("~"),
    "$XDG_CONFIG_HOME": os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
    "$XDG_DATA_HOME": os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
}


def _get_documents_path() -> str:
    """Return the real My Documents folder path, respecting OneDrive redirection.

    On Windows, My Documents may be redirected to OneDrive (e.g.
    ``C:\\Users\\<user>\\OneDrive\\文件``).  Reading the path via the
    Windows Shell API (``SHGetFolderPath`` / ``SHGetKnownFolderPath``) always
    returns the current effective location.

    Falls back to ``~/Documents`` on non-Windows or if the API is unavailable.
    """
    if os.name == "nt":
        try:
            import ctypes
            import ctypes.wintypes

            # CSIDL_PERSONAL = 0x0005 → My Documents
            buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
            ctypes.windll.shell32.SHGetFolderPathW(None, 0x0005, None, 0, buf)
            path = buf.value
            if path and os.path.isdir(path):
                return path
        except Exception:
            pass
    return os.path.join(os.path.expanduser("~"), "Documents")


def _get_steam_path() -> str:
    """Return the Steam installation path from the Windows registry, or ``""``."""
    if os.name != "nt":
        return ""
    try:
        import winreg  # type: ignore

        candidates = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Valve\Steam", "SteamPath"),
        ]
        for hive, key_path, value_name in candidates:
            try:
                with winreg.OpenKey(hive, key_path) as key:
                    value, _ = winreg.QueryValueEx(key, value_name)
                    if value:
                        # SteamPath may use forward slashes; normalise to OS separator
                        return os.path.normpath(value)
            except (FileNotFoundError, OSError):
                continue
    except ImportError:
        pass
    return ""


# Map PCGamingWiki template tags to OS-specific paths.
# NOTE: All keys use the canonical upper-case P form ({{P|…}}).  The expansion
# function normalises lower-case {{p|…}} occurrences before lookup.
_WIKI_TAG_MAP: dict = {
    "{{P|userprofile}}": os.path.expanduser("~"),
    "{{P|userappdata}}": os.environ.get("APPDATA", os.path.expanduser("~/.config")),
    "{{P|appdata}}": os.environ.get("APPDATA", os.path.expanduser("~/.config")),
    "{{P|localappdata}}": os.environ.get("LOCALAPPDATA", os.path.expanduser("~/.local/share")),
    "{{P|programdata}}": os.environ.get("PROGRAMDATA", "/usr/share"),
    "{{P|documents}}": _get_documents_path(),
    "{{P|uid}}": "*",  # Represents SteamID3; expanded to glob wildcard
    "{{P|game}}": "",  # Represents the game folder name
    "{{P|osxhome}}": os.path.expanduser("~"),
    "{{P|linuxhome}}": os.path.expanduser("~"),
    "{{P|xdgconfig}}": os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
    "{{P|xdgdata}}": os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
    "{{P|steam}}": _get_steam_path(),
    # Compound tokens: some Wiki pages write {{P|base/subdir}} as a shorthand.
    "{{P|userprofile/documents}}": _get_documents_path(),
    "{{P|userprofile/appdata}}": os.environ.get("APPDATA", os.path.expanduser("~/.config")),
    "{{P|userprofile/localappdata}}": os.environ.get("LOCALAPPDATA", os.path.expanduser("~/.local/share")),
    "{{P|userprofile/appdata/locallow}}": os.path.join(os.path.expanduser("~"), "AppData", "LocalLow") if os.name == "nt" else os.path.expanduser("~/.local/share"),
    "{{P|userprofile\\documents}}": _get_documents_path(),
    "{{P|userprofile\\appdata\\locallow}}": os.path.join(os.path.expanduser("~"), "AppData", "LocalLow") if os.name == "nt" else os.path.expanduser("~/.local/share"),
}

# Registry path token prefixes – these are not filesystem paths
_REGISTRY_TOKENS: tuple = ("{{p|hkcu}}", "{{p|hklm}}", "{{p|hkcr}}", "{{p|hku}}", "{{p|hkcc}}")

# Mapping from wiki registry tokens to Windows registry root key names
_REGISTRY_TOKEN_MAP: dict = {
    "{{p|hkcu}}": "HKEY_CURRENT_USER",
    "{{p|hklm}}": "HKEY_LOCAL_MACHINE",
    "{{p|hkcr}}": "HKEY_CLASSES_ROOT",
    "{{p|hku}}": "HKEY_USERS",
    "{{p|hkcc}}": "HKEY_CURRENT_CONFIG",
}


def _expand_registry_token(raw: str) -> Optional[str]:
    """Expand a wiki registry path like ``{{p|hkcu}}\\Software\\...`` to
    ``HKEY_CURRENT_USER\\Software\\...``.  Returns *None* if the token
    is not recognized."""
    raw_lower = raw.lower()
    for tok, root in _REGISTRY_TOKEN_MAP.items():
        if raw_lower.startswith(tok):
            return root + raw[len(tok):]
    return None


def _remove_duplicate_path_segments(path: str) -> str:
    """Remove consecutive duplicate segments from *path*.

    For example ``C:\\AppData\\Roaming\\Roaming\\App`` becomes
    ``C:\\AppData\\Roaming\\App``.  This fixes paths where a token such as
    ``{{P|appdata}}`` (which already includes the ``Roaming`` directory on
    Windows) is followed by a redundant ``\\Roaming\\`` suffix.
    """
    sep = os.sep
    # Normalise all slashes to the OS separator before splitting
    normalised = path.replace("/", sep)
    # Preserve a leading separator (UNC paths, Unix absolute paths)
    leading = normalised[: len(normalised) - len(normalised.lstrip(sep))]
    parts = normalised.split(sep)
    deduped: List[str] = []
    for part in parts:
        if deduped and part and part == deduped[-1]:
            continue  # skip consecutive duplicate segment
        deduped.append(part)
    return leading + sep.join(p for p in deduped if p)


def _resolve_uid_glob(path: str) -> Optional[str]:
    """Resolve a wildcard *path* produced by ``{{p|uid}}`` expansion.

    If *path* contains no ``*`` it is returned unchanged.  Otherwise
    :func:`glob.glob` is used to find matching filesystem entries and the
    one with the most recent modification time is returned.  Returns
    ``None`` when the glob matches nothing.
    """
    matches = _resolve_uid_glob_all(path)
    return matches[0] if matches else None


def _resolve_uid_glob_all(path: str) -> List[str]:
    """Return all paths matching a Steam ``{{P|uid}}`` wildcard."""
    if "*" not in path:
        return [path]
    matches = _glob_module.glob(path)
    try:
        return sorted(matches, key=os.path.getmtime, reverse=True)
    except OSError:
        return sorted(matches)


# Config locations for Steam titles PCGamingWiki does not document, keyed by
# lowercased game title. Kept separate from the wiki lookup so it works fully
# offline and regardless of wiki coverage.
_KNOWN_LOCAL_RAW_PATHS: Dict[str, List[str]] = {
    # Ships the same Unreal Engine project ("b1") as the base game, but keeps
    # its saved config under its own install folder instead of %LOCALAPPDATA%.
    "black myth: wukong benchmark tool": [r"{{P|game}}\b1\Saved\Config\Windows"],
}


def _merge_known_local_paths(result: Dict[str, Any], game_title: str, install_path: str) -> None:
    """Augment *result* in place with paths PCGamingWiki does not document."""
    if not install_path:
        return
    for raw in _KNOWN_LOCAL_RAW_PATHS.get(game_title.strip().lower(), []):
        if raw not in result["raw_paths"]:
            result["raw_paths"].append(raw)
        expanded = _expand_path_tokens(raw, install_path=install_path)
        if expanded not in result["expanded_paths"]:
            result["expanded_paths"].append(expanded)


def _expand_path_tokens(path: str, install_path: str = "") -> str:
    """Expand PCGamingWiki path tokens and Wiki template tags to absolute OS paths.

    Processing order:

    0. Strip wiki markup artefacts (e.g. ``''(version info)''``).
    1. Normalise ``{{p|…}}`` (lower-case *p*) to canonical ``{{P|…}}`` form.
    2. Expand Wiki template tags from :data:`_WIKI_TAG_MAP`.
       The ``{{P|game}}`` token is replaced with *install_path* if provided.
    3. Expand standard Windows environment variables via
       :func:`os.path.expandvars`.
    4. Expand remaining special tokens defined in :data:`_PATH_TOKENS`.
    5. Normalise the result with :func:`os.path.normpath`.
    6. Remove consecutive duplicate path segments (fixes double-``Roaming``
       that arises when a token already includes ``Roaming`` and the raw path
       appends ``\\Roaming\\`` again).
    7. Convert separators to ``/`` so output is stable across platforms.
    """
    # 0. Strip wiki markup artefacts like ''(version info)'' from paths
    path = re.sub(r"\s*''[^']*''", "", path)

    # 1. Normalise {{p|...}} or {{P|...}} → {{P|<lowercase content with / sep>}}
    #    so tag lookups in _WIKI_TAG_MAP are case-insensitive and separator-agnostic.
    #    This handles both {{P|userprofile/Documents}} and {{p|userprofile\Documents}}.
    path = re.sub(
        r"\{\{[Pp]\|([^{}]+)\}\}",
        lambda m: "{{P|" + m.group(1).lower().replace("\\", "/") + "}}",
        path,
    )

    # 2. Expand Wiki template tags
    #    Handle {{P|game}} specially — use install_path if provided.
    if install_path:
        path = path.replace("{{P|game}}", install_path)
    for tag, replacement in _WIKI_TAG_MAP.items():
        path = path.replace(tag, replacement)

    # 3. Expand standard Windows environment variables (e.g. %APPDATA%)
    path = os.path.expandvars(path)

    # 4. Expand remaining special tokens
    for token, replacement in _PATH_TOKENS.items():
        path = path.replace(token, replacement)

    # 5. Normalise slashes/dots
    path = os.path.normpath(path)

    # 6. Remove consecutive duplicate segments (e.g. Roaming\Roaming)
    path = _remove_duplicate_path_segments(path)

    # 7. Use forward slashes for deterministic cross-platform output.
    path = path.replace("\\", "/")

    return path


def _is_registry_path(path: str) -> bool:
    """Return ``True`` if *path* is a Windows registry path, not a filesystem path."""
    path_lower = path.lower()
    return any(path_lower.startswith(tok) for tok in _REGISTRY_TOKENS)


def _find_template_blocks(wikitext: str, template_name: str) -> List[str]:
    """Return all ``{{template_name|…}}`` blocks from *wikitext*, handling nesting.

    Uses brace-counting so nested ``{{P|…}}`` tokens inside a block are not
    mistaken for the closing ``}}`` of the outer template.
    """
    blocks: List[str] = []
    search_lower = ("{{" + template_name).lower()
    wt_lower = wikitext.lower()
    pos = 0
    while True:
        idx = wt_lower.find(search_lower, pos)
        if idx == -1:
            break
        # Verify the match is followed by '|' or '}}' (i.e. it's the full name)
        after = idx + len(search_lower)
        if after >= len(wikitext) or wikitext[after] not in ("|", "}"):
            pos = idx + 1
            continue
        # Walk forward counting '{{' / '}}' to find the matching close
        depth = 0
        i = idx
        while i < len(wikitext):
            if wikitext[i : i + 2] == "{{":
                depth += 1
                i += 2
            elif wikitext[i : i + 2] == "}}":
                depth -= 1
                i += 2
                if depth == 0:
                    break
            else:
                i += 1
        blocks.append(wikitext[idx:i])
        pos = i
    return blocks


def _split_by_pipe(content: str) -> List[str]:
    """Split *content* on ``|`` while respecting ``{{…}}`` nesting."""
    parts: List[str] = []
    depth = 0
    buf: List[str] = []
    i = 0
    while i < len(content):
        if content[i : i + 2] == "{{":
            depth += 1
            buf.append("{{")
            i += 2
        elif content[i : i + 2] == "}}":
            depth -= 1
            buf.append("}}")
            i += 2
        elif content[i] == "|" and depth == 0:
            parts.append("".join(buf))
            buf = []
            i += 1
        else:
            buf.append(content[i])
            i += 1
    if buf:
        parts.append("".join(buf))
    return parts


def _parse_gamedata_config(
    wikitext: str, os_filter: str = "Windows", install_path: str = ""
) -> Tuple[List[str], List[str]]:
    """Parse ``{{Game data/config|OS|path|…}}`` blocks from *wikitext*.

    Parameters
    ----------
    wikitext:
        Raw wikitext fetched from PCGamingWiki.
    os_filter:
        Only extract paths from blocks whose OS argument contains this string
        (case-insensitive).  Defaults to ``"Windows"``.

    Returns
    -------
    tuple[list[str], list[str]]
        ``(raw_paths, expanded_paths)``.  Registry paths (``{{P|hkcu}}`` etc.)
        are included in *raw_paths* for diagnostics but excluded from
        *expanded_paths*.
    """
    raw_paths: List[str] = []
    expanded_paths: List[str] = []
    for block in _find_template_blocks(wikitext, "Game data/config"):
        # Strip outer {{ and }} then split on | (respecting nested templates)
        if not (block.startswith("{{") and block.endswith("}}")):
            continue  # guard against malformed blocks
        inner = block[2:-2]
        parts = _split_by_pipe(inner)
        # parts[0] == "Game data/config", parts[1] == OS, parts[2:] == paths
        if len(parts) < 3:
            continue
        os_name = parts[1].strip()
        if os_filter:
            os_lower = os_name.lower()
            filter_lower = os_filter.lower()
            # Accept "Windows", "Steam", "Epic Games Launcher",
            # "Microsoft Store", "GOG.com" as Windows-compatible platforms.
            _WINDOWS_COMPATIBLE = {
                "windows", "steam", "epic games launcher",
                "microsoft store", "gog.com", "gog",
            }
            if filter_lower == "windows":
                if os_lower not in _WINDOWS_COMPATIBLE and filter_lower not in os_lower:
                    continue
            elif filter_lower not in os_lower:
                continue
        for raw in parts[2:]:
            raw = raw.strip()
            if not raw:
                continue
            raw_paths.append(raw)
            if _is_registry_path(raw):
                reg = _expand_registry_token(raw)
                if reg is not None:
                    expanded_paths.append(reg)
            else:
                expanded = _expand_path_tokens(raw, install_path=install_path)
                expanded_paths.extend(_resolve_uid_glob_all(expanded))
    return raw_paths, expanded_paths


class PCGamingWikiClient:
    """Client for querying PCGamingWiki for game configuration paths."""

    def __init__(
        self,
        timeout: int = 10,
        cache_path: Optional[str] = None,
        consent_path: Optional[str] = None,
    ) -> None:
        self.timeout = timeout
        self._session = requests.Session() if requests else None
        if self._session:
            self._session.headers.update(
                {"User-Agent": "GameSettingAligner/1.0 (https://github.com/ElyZeng/Game-setting-aligner)"}
            )
        self._cache: Dict[str, Any] = {}
        self._cache_path = cache_path or _CACHE_FILE
        self._consent_path = consent_path or _CONSENT_FILE
        self._download_decisions: Dict[str, Any] = {}
        self._load_cache()
        self._load_download_decisions()

    def _load_cache(self) -> None:
        """Load the offline wiki cache from disk if available."""
        paths = [self._cache_path]
        if self._cache_path == _CACHE_FILE and _BUNDLED_CACHE_FILE != _CACHE_FILE:
            paths.append(_BUNDLED_CACHE_FILE)
        for path in paths:
            if not os.path.isfile(path):
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    self._cache = loaded
                    return
            except (json.JSONDecodeError, OSError):
                continue

    def _load_download_decisions(self) -> None:
        """Load per-game download decisions from durable user storage."""
        try:
            with open(self._consent_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                self._download_decisions = loaded.get("games", loaded)
        except (json.JSONDecodeError, OSError):
            self._download_decisions = {}

    @staticmethod
    def _write_json_atomic(path: str, payload: Dict[str, Any]) -> None:
        """Write JSON without leaving a partial persistence file behind."""
        directory = os.path.dirname(path) or "."
        os.makedirs(directory, exist_ok=True)
        fd, temporary_path = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
            os.replace(temporary_path, path)
        except Exception:
            try:
                os.unlink(temporary_path)
            except OSError:
                pass
            raise

    @staticmethod
    def _normalize_title(title: str) -> str:
        """Normalize a game title for cache comparison.

        Strips trademark/copyright symbols (™ ® ©), collapses whitespace,
        and lowercases for fuzzy matching.
        """
        # Remove ™ ® © and other common symbol characters
        cleaned = re.sub(r'[\u2122\u00AE\u00A9]', '', title)
        # Normalize unicode (e.g. accented chars)
        cleaned = unicodedata.normalize('NFKD', cleaned)
        # Collapse whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned.lower()

    def _lookup_cache(self, game_title: str) -> Optional[Dict[str, Any]]:
        """Look up *game_title* in the offline cache (case-insensitive, symbol-tolerant)."""
        # Exact match first
        if game_title in self._cache:
            return self._cache[game_title]
        # Normalized fuzzy match
        normalized = self._normalize_title(game_title)
        for key, value in self._cache.items():
            if self._normalize_title(key) == normalized:
                return value
        return None

    def download_state(self, game_title: str) -> str:
        """Return ``cached``, ``no_decision``, ``declined``, or ``needs_update``."""
        cached = self._lookup_cache(game_title)
        if cached and cached.get("raw_paths"):
            return "cached"
        decision = self._download_decisions.get(self._normalize_title(game_title), {})
        value = decision.get("decision") if isinstance(decision, dict) else decision
        if value == "declined":
            return "declined"
        if value == "accepted":
            return "needs_update"
        return "no_decision"

    def set_download_decision(self, game_title: str, decision: str) -> None:
        """Persist an explicit per-game download decision."""
        if decision not in {"accepted", "declined"}:
            raise ValueError("decision must be 'accepted' or 'declined'")
        self._download_decisions[self._normalize_title(game_title)] = {
            "title": game_title,
            "decision": decision,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._write_json_atomic(
            self._consent_path,
            {"version": 1, "games": self._download_decisions},
        )

    def clear_download_decision(self, game_title: str) -> None:
        """Clear a decision so an explicit retry flow can ask again."""
        self._download_decisions.pop(self._normalize_title(game_title), None)
        self._write_json_atomic(
            self._consent_path,
            {"version": 1, "games": self._download_decisions},
        )

    def _save_cache_entry(self, game_title: str, result: Dict[str, Any]) -> None:
        self._cache[game_title] = {
            "page_title": result.get("page_title", game_title),
            "raw_paths": list(result.get("raw_paths") or []),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        self._write_json_atomic(self._cache_path, self._cache)

    def _expand_cached_raw_paths(self, raw_paths: List[str], install_path: str = "") -> List[str]:
        """Expand raw cached paths to local OS paths."""
        expanded: List[str] = []
        for raw in raw_paths:
            if _is_registry_path(raw):
                reg = _expand_registry_token(raw)
                if reg is not None:
                    expanded.append(reg)
                continue
            exp = _expand_path_tokens(raw, install_path=install_path)
            expanded.extend(_resolve_uid_glob_all(exp))
        return expanded

    def search_game(self, title: str) -> Optional[str]:
        """Return the PCGamingWiki page title for the given game, or None."""
        if self._session is None:
            return None

        params = {
            "action": "opensearch",
            "search": title,
            "limit": 1,
            "format": "json",
        }
        try:
            response = self._session.get(_API_URL, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            if data and len(data) > 1 and data[1]:
                return data[1][0]
        except Exception:
            pass
        return None

    def get_config_paths(self, game_title: str) -> List[str]:
        """Return a list of expanded config file paths for the given game title.

        Checks the offline cache first, then falls back to online queries
        (Cargo → MediaWiki wikitext → HTML scraping).
        """
        # Try offline cache first
        cached = self._lookup_cache(game_title)
        if cached and cached.get("raw_paths"):
            return self._expand_cached_raw_paths(cached["raw_paths"])

        _, expanded = self._query_cargo_raw(game_title)
        if not expanded:
            _, expanded = self._query_mediawiki_raw(game_title)
        if not expanded:
            _, expanded = self._scrape_wiki_page_raw(game_title)
        return expanded

    def get_config_info(
        self,
        game_title: str,
        install_path: str = "",
        allow_download: bool = True,
    ) -> Dict[str, Any]:
        """Return a dict with raw and expanded config paths for *game_title*.

        The returned dict has the following keys:

        ``page_title``
            The game title as queried.
        ``url``
            The expected PCGamingWiki URL for this game.
        ``raw_paths``
            List of raw path strings as returned by PCGamingWiki (may contain
            template tags such as ``{{P|userprofile}}``).
        ``expanded_paths``
            List of path strings after expanding tokens to local OS paths.
            Registry paths (e.g. ``{{P|hkcu}}\\…``) are omitted here but are
            present in ``raw_paths`` for diagnostics.
        ``error``
            ``None`` on success, or an error message string on failure.
        """
        result: Dict[str, Any] = {
            "page_title": game_title,
            "url": _WIKI_BASE + game_title.replace(" ", "_"),
            "raw_paths": [],
            "expanded_paths": [],
            "error": None,
        }
        # Try offline cache first
        cached = self._lookup_cache(game_title)
        if cached and cached.get("raw_paths"):
            result["raw_paths"] = cached["raw_paths"]
            result["expanded_paths"] = self._expand_cached_raw_paths(
                cached["raw_paths"], install_path=install_path
            )
            if cached.get("page_title"):
                result["page_title"] = cached["page_title"]
                result["url"] = _WIKI_BASE + cached["page_title"].replace(" ", "_")
            _merge_known_local_paths(result, game_title, install_path)
            return result

        state = self.download_state(game_title)
        if not allow_download and state != "needs_update":
            result["error"] = (
                "download_declined" if state == "declined" else "download_consent_required"
            )
            _merge_known_local_paths(result, game_title, install_path)
            return result

        if self._session is None:
            result["error"] = "requests library not available"
            _merge_known_local_paths(result, game_title, install_path)
            return result
        try:
            if install_path:
                raw, expanded = self._query_cargo_raw(game_title, install_path=install_path)
            else:
                raw, expanded = self._query_cargo_raw(game_title)
            if not raw:
                if install_path:
                    raw, expanded = self._query_mediawiki_raw(game_title, install_path=install_path)
                else:
                    raw, expanded = self._query_mediawiki_raw(game_title)
            if not raw:
                raw, expanded = self._scrape_wiki_page_raw(game_title, install_path=install_path)
            # Retry with cleaned title (strip ™®© etc.) if no results found
            if not raw:
                cleaned = re.sub(r'[\u2122\u00AE\u00A9]', '', game_title).strip()
                if cleaned != game_title:
                    raw, expanded = self._query_cargo_raw(cleaned, install_path=install_path)
                    if not raw:
                        raw, expanded = self._query_mediawiki_raw(cleaned, install_path=install_path)
                    if not raw:
                        raw, expanded = self._scrape_wiki_page_raw(cleaned, install_path=install_path)
            # Retry with search API to find the correct page title
            if not raw:
                searched = self.search_game(game_title)
                if searched and searched != game_title:
                    raw, expanded = self._query_cargo_raw(searched, install_path=install_path)
                    if not raw:
                        raw, expanded = self._query_mediawiki_raw(searched, install_path=install_path)
            result["raw_paths"] = raw
            result["expanded_paths"] = expanded
        except Exception as exc:  # pragma: no cover
            result["error"] = str(exc)
        if result["raw_paths"] and state == "needs_update":
            try:
                self._save_cache_entry(game_title, result)
            except OSError as exc:
                result["error"] = f"cache_write_failed: {exc}"
        _merge_known_local_paths(result, game_title, install_path)
        return result

    def _query_cargo_raw(self, game_title: str, install_path: str = "") -> Tuple[List[str], List[str]]:
        """Query PCGamingWiki Cargo tables for config paths.

        Returns a tuple ``(raw_paths, expanded_paths)``.
        """
        if self._session is None:
            return [], []

        # Escape single quotes to avoid injection into the Cargo WHERE clause.
        safe_title = game_title.replace("'", "\\'")
        params = {
            "action": "cargoquery",
            "tables": "Config_game_data",
            "fields": "Path,OS",
            "where": f"Holds='Game data' AND _pageName='{safe_title}'",
            "format": "json",
            "limit": 20,
        }
        try:
            response = self._session.get(_API_URL, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            results = data.get("cargoquery", [])
            raw_paths: List[str] = []
            expanded_paths: List[str] = []
            for result in results:
                raw_path = result.get("title", {}).get("Path", "")
                if raw_path:
                    raw_paths.append(raw_path)
                    if _is_registry_path(raw_path):
                        reg = _expand_registry_token(raw_path)
                        if reg is not None:
                            expanded_paths.append(reg)
                    else:
                        expanded = _expand_path_tokens(raw_path, install_path=install_path)
                        expanded_paths.extend(_resolve_uid_glob_all(expanded))
            return raw_paths, expanded_paths
        except Exception:
            return [], []

    def _query_mediawiki_raw(self, game_title: str, install_path: str = "") -> Tuple[List[str], List[str]]:
        """Fetch wikitext via the MediaWiki API and parse config paths.

        Uses ``action=query&prop=revisions`` to retrieve the raw wikitext for
        *game_title* and then calls :func:`_parse_gamedata_config` to extract
        paths from ``{{Game data/config|Windows|…}}`` blocks.

        This method is used as a fallback when :meth:`_query_cargo_raw` returns
        no results.

        Returns a tuple ``(raw_paths, expanded_paths)``.
        """
        if self._session is None:
            return [], []

        params = {
            "action": "query",
            "prop": "revisions",
            "rvslots": "main",
            "rvprop": "content",
            "titles": game_title,
            "format": "json",
        }
        try:
            response = self._session.get(_API_URL, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            pages = data.get("query", {}).get("pages", {})
            if not pages:
                return [], []
            page = next(iter(pages.values()))
            revisions = page.get("revisions")
            if not revisions:
                return [], []
            slot = revisions[0].get("slots", {}).get("main", {})
            wikitext = slot.get("*", "")
            if not wikitext:
                return [], []
            return _parse_gamedata_config(wikitext, install_path=install_path)
        except Exception:
            return [], []

    def _scrape_wiki_page_raw(self, game_title: str, install_path: str = "") -> Tuple[List[str], List[str]]:
        """Scrape the PCGamingWiki page for config paths as a fallback.

        Returns a tuple ``(raw_paths, expanded_paths)``.
        """
        if self._session is None or BeautifulSoup is None:
            return [], []

        url = _WIKI_BASE + game_title.replace(" ", "_")
        try:
            response = self._session.get(url, timeout=self.timeout)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
        except Exception:
            return [], []

        raw_paths: List[str] = []
        expanded_paths: List[str] = []
        # Config table rows typically contain path-like text with slashes or backslashes
        for td in soup.find_all("td", class_=re.compile(r"game-data", re.I)):
            text = td.get_text(separator=" ", strip=True)
            if re.search(r"[/\\]", text):
                raw_paths.append(text)
                expanded_paths.append(_expand_path_tokens(text, install_path=install_path))

        return raw_paths, expanded_paths
