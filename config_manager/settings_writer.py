"""Write modified key settings back to game config files.

Reverses the parsing done by ``settings_parser`` — takes a dict of the 7 key
settings and patches the original config file content in-place, then writes
it back to disk.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .settings_parser import (
    RESOLUTION,
    SCREEN_MODE,
    VSYNC,
    FRAME_LIMIT,
    DYNAMIC_RESOLUTION,
    UPSCALING,
    FRAME_GENERATION,
    _parse_ini_kv,
    FORZA_PRESET_SIGNATURES,
)
QUICK_PRESET = "quick_preset"


# ── Helpers ──────────────────────────────────────────────────────────

def _safe_write(path: str, content: str) -> None:
    """Write *content* to *path*, creating parent directories if needed."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def forza_auxiliary_paths(config_files: List[Dict[str, Any]]) -> List[str]:
    """Return Forza files that persist settings outside UserConfigSelections."""
    paths: List[str] = []
    for config_file in config_files:
        config_path = Path(str(config_file.get("expanded_path", "")))
        if (
            config_path.name == "UserConfigSelections"
            and config_path.parent.name == "ForzaUserConfigSelections"
        ):
            paths.append(str(config_path.parent.parent.parent / "fullscreen_choice"))
    return paths


def _replace_ini_value(content: str, key: str, new_value: str) -> str:
    """Replace the value of *key*=... in INI-style content."""
    pattern = re.compile(rf"^(\s*{re.escape(key)}\s*=\s*)(.*)$", re.MULTILINE)
    if pattern.search(content):
        return pattern.sub(rf"\g<1>{new_value}", content)
    return content


def _replace_valve_kv_value(content: str, key: str, new_value: str) -> str:
    """Replace a Valve KV ``"key" "value"`` entry."""
    pattern = re.compile(
        rf'^(\s*"{re.escape(key)}"\s+")([^"]*)(")$', re.MULTILINE
    )
    if pattern.search(content):
        return pattern.sub(rf"\g<1>{new_value}\g<3>", content)
    return content


def _replace_xml_attr(content: str, tag: str, attr: str, new_value: str) -> str:
    """Replace an XML attribute ``<tag attr="old">`` → ``<tag attr="new">``."""
    pattern = re.compile(
        rf'(<{re.escape(tag)}\b[^>]*\b{re.escape(attr)}=")([^"]*)(")',
    )
    if pattern.search(content):
        return pattern.sub(rf"\g<1>{new_value}\g<3>", content)
    return content


def _replace_xml_option(content: str, option_id: str, new_value: str) -> str:
    """Replace ``<option id="..." value="old">`` → ``value="new"``."""
    pattern = re.compile(
        rf'(<option\s+id="{re.escape(option_id)}"\s+value=")([^"]*)(")',
    )
    if pattern.search(content):
        return pattern.sub(rf"\g<1>{new_value}\g<3>", content)
    return content


# ── Cyberpunk 2077 Writer ────────────────────────────────────────────

def _write_cyberpunk(
    content: str, settings: Dict[str, Optional[str]]
) -> str:
    """Patch Cyberpunk 2077 UserSettings.json with new settings."""
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return content

    groups = data.get("data", [])

    def _set_option(opt_name: str, value: Any, group_prefix: str = "") -> None:
        for group in groups:
            gname = group.get("group_name", "")
            if group_prefix and not gname.startswith(group_prefix):
                continue
            for opt in group.get("options", []):
                if opt["name"] == opt_name:
                    opt["value"] = value
                    return

    # Resolution
    val = settings.get(RESOLUTION)
    if val and "x" in val:
        _set_option("Resolution", val, "/video/display")

    # Screen Mode
    val = settings.get(SCREEN_MODE)
    if val is not None:
        mode_map = {"Fullscreen": 0, "Borderless Windowed": 1, "Windowed": 2}
        if val in mode_map:
            _set_option("WindowMode", mode_map[val], "/video/display")

    # VSync
    val = settings.get(VSYNC)
    if val is not None:
        vs_val = "UI-Settings-Video-QualitySetting-On" if val == "On" else "UI-Settings-Video-QualitySetting-Off"
        _set_option("VSync", vs_val, "/video/display")

    # Frame Limit
    val = settings.get(FRAME_LIMIT)
    if val is not None:
        if val == "Unlimited" or val == "Off":
            _set_option("MaximumFPS_OnOff", False)
        else:
            _set_option("MaximumFPS_OnOff", True)
            try:
                fps = int(val.replace(" FPS", ""))
                _set_option("MaximumFPS", fps)
            except ValueError:
                pass

    # Dynamic Resolution
    val = settings.get(DYNAMIC_RESOLUTION)
    if val is not None:
        _set_option("DynamicResolutionScaling", val.startswith("On"))

    # Upscaling
    val = settings.get(UPSCALING)
    if val is not None:
        if val == "Off":
            _set_option("ResolutionScaling", "Off")
        elif "DLSS" in val:
            _set_option("ResolutionScaling", "DLSS")
        elif "FSR" in val:
            _set_option("ResolutionScaling", "FSR2")
        elif "XeSS" in val:
            _set_option("ResolutionScaling", "XeSS")

    # Frame Generation
    val = settings.get(FRAME_GENERATION)
    if val is not None:
        if val == "Off":
            _set_option("FrameGeneration", False)
        else:
            _set_option("FrameGeneration", True)


    # Quick Preset ? write QuickPresets field under /graphics/presets
    val = settings.get(QUICK_PRESET)
    if val is not None and val not in ("N/A", "—"):
        _set_option("QuickPresets", val, "/graphics/presets")

    return json.dumps(data, indent=4, ensure_ascii=False)


# ── Unreal Engine INI Writer ────────────────────────────────────────

def _write_unreal_ini(
    content: str, settings: Dict[str, Optional[str]]
) -> str:
    """Patch Unreal Engine GameUserSettings.ini with new settings."""
    result = content

    # Resolution
    val = settings.get(RESOLUTION)
    if val and "x" in val:
        w, h = val.split("x", 1)
        result = _replace_ini_value(result, "ResolutionSizeX", w.strip())
        result = _replace_ini_value(result, "ResolutionSizeY", h.strip())
        result = _replace_ini_value(result, "LastUserConfirmedResolutionSizeX", w.strip())
        result = _replace_ini_value(result, "LastUserConfirmedResolutionSizeY", h.strip())

    # Screen Mode
    val = settings.get(SCREEN_MODE)
    if val is not None:
        mode_map = {"Fullscreen": "0", "Borderless Windowed": "1", "Windowed": "2"}
        m = mode_map.get(val, "0")
        result = _replace_ini_value(result, "FullscreenMode", m)
        result = _replace_ini_value(result, "LastConfirmedFullscreenMode", m)
        result = _replace_ini_value(result, "PreferredFullscreenMode", m)

    # VSync
    val = settings.get(VSYNC)
    if val is not None:
        result = _replace_ini_value(result, "bUseVSync", "True" if val == "On" else "False")

    # Frame Limit
    val = settings.get(FRAME_LIMIT)
    if val is not None:
        if val == "Unlimited":
            result = _replace_ini_value(result, "FrameRateLimit", "0.000000")
        else:
            try:
                fps = float(val.replace(" FPS", ""))
                result = _replace_ini_value(result, "FrameRateLimit", f"{fps:.6f}")
            except ValueError:
                pass

    # Dynamic Resolution
    val = settings.get(DYNAMIC_RESOLUTION)
    if val is not None:
        result = _replace_ini_value(
            result, "bUseDynamicResolution", "True" if val == "On" else "False"
        )

    # Upscaling
    val = settings.get(UPSCALING)
    if val is not None:
        if val == "Off":
            result = _replace_ini_value(result, "ResolutionScalingMethod", "")
        elif "DLSS" in val:
            result = _replace_ini_value(result, "ResolutionScalingMethod", "DLSS")
        elif "FSR" in val:
            result = _replace_ini_value(result, "ResolutionScalingMethod", "FSR")
        elif "XeSS" in val:
            result = _replace_ini_value(result, "ResolutionScalingMethod", "XeSS")

    # Frame Generation
    val = settings.get(FRAME_GENERATION)
    if val is not None:
        if val == "Off":
            result = _replace_ini_value(result, "DLSSFrameGenerationMode", "Off")
            result = _replace_ini_value(result, "FSRFrameGenerationMode", "Off")
        elif "DLSS" in val:
            result = _replace_ini_value(result, "DLSSFrameGenerationMode", "On")
        elif "FSR" in val:
            result = _replace_ini_value(result, "FSRFrameGenerationMode", "On")

    # Quick Preset — GPUConfigPreset: -1=Custom, 0=Low, 1=Medium, 2=High, 3=Ultra
    val = settings.get(QUICK_PRESET)
    if val is not None and val not in ("N/A", "—"):
        preset_to_int = {"Low": "0", "Medium": "1", "High": "2", "Ultra": "3", "Custom": "-1"}
        gcp_val = preset_to_int.get(val, "-1")
        result = _replace_ini_value(result, "GPUConfigPreset", gcp_val)

    return result



def _write_forza_xml(
    content: str, settings: Dict[str, Optional[str]]
) -> str:
    """Patch Forza Horizon XML config with new settings."""
    result = content

    # Resolution
    val = settings.get(RESOLUTION)
    if val and "x" in val:
        w, h = val.split("x", 1)
        result = _replace_xml_attr(result, "ResolutionWidth", "value", w.strip())
        result = _replace_xml_attr(result, "ResolutionHeight", "value", h.strip())

    # Overall preset writes the captured base-game quality signature. RT variants
    # remain read-only because their ray-tracing level is a separate dimension.
    preset = settings.get(QUICK_PRESET)
    if preset in FORZA_PRESET_SIGNATURES:
        for option_id, option_value in FORZA_PRESET_SIGNATURES[preset].items():
            result = _replace_xml_option(result, option_id, option_value)

    # Screen Mode
    val = settings.get(SCREEN_MODE)
    if val is not None:
        if val == "Borderless Windowed" and re.search(r'<UserConfig\b[^>]*\bVersion="52"', content):
            return result
        result = _replace_xml_attr(
            result, "Fullscreen", "value", "1" if val == "Fullscreen" else "0"
        )

    # VSync
    val = settings.get(VSYNC)
    if val is not None:
        result = _replace_xml_option(result, "VSync", "1" if val == "On" else "0")
        result = _replace_xml_attr(result, "PresentInterval", "value", "1" if val == "On" else "0")

    # Frame Limit
    val = settings.get(FRAME_LIMIT)
    if val is not None:
        fr_map = {"30 FPS": "0", "40 FPS": "1", "60 FPS": "2", "120 FPS": "3", "Unlimited": "4"}
        if re.search(r'<UserConfig\b[^>]*\bVersion="52"', content):
            fr_map = {"20 FPS": "1", "30 FPS": "2", "60 FPS": "3", "Unlimited": "4"}
        fv = fr_map.get(val, "4")
        result = _replace_xml_option(result, "FrameRate", fv)

    # Dynamic Resolution
    val = settings.get(DYNAMIC_RESOLUTION)
    if val is not None:
        result = _replace_xml_option(
            result, "UseDynamicOptimization", "1" if val == "On" else "0"
        )

    # Upscaling
    val = settings.get(UPSCALING)
    if val is not None:
        if val == "Off":
            result = _replace_xml_option(result, "XeSSMode", "0")
            result = _replace_xml_option(result, "DLSSMode", "0")
            result = _replace_xml_option(result, "FSR3Mode", "0")
        elif "XeSS" in val:
            xess_map = {"XeSS Ultra Quality Plus": "1", "XeSS Ultra Quality": "2", "XeSS Quality": "3", "XeSS Balanced": "4", "XeSS Performance": "5", "XeSS Ultra Performance": "6"}
            result = _replace_xml_option(result, "XeSSMode", xess_map.get(val, "1"))
            result = _replace_xml_option(result, "DLSSMode", "0")
            result = _replace_xml_option(result, "FSR3Mode", "0")
        elif "DLSS" in val:
            result = _replace_xml_option(result, "DLSSMode", "1")
            result = _replace_xml_option(result, "XeSSMode", "0")
            result = _replace_xml_option(result, "FSR3Mode", "0")
        elif "FSR" in val:
            fsr_map = {"FSR Quality": "1", "FSR Balance": "2", "FSR Performance": "3", "FSR Ultra Performance": "4"}
            result = _replace_xml_option(result, "FSR3Mode", fsr_map.get(val, "1"))
            result = _replace_xml_option(result, "XeSSMode", "0")
            result = _replace_xml_option(result, "DLSSMode", "0")

    # Frame Generation
    val = settings.get(FRAME_GENERATION)
    if val is not None:
        if val == "Off":
            result = _replace_xml_option(result, "DLSSGMode", "0")
        else:
            result = _replace_xml_option(result, "DLSSGMode", "1")

    return result


def _write_f1_xml(content: str, settings: Dict[str, Optional[str]]) -> str:
    """Patch F1 25 hardware settings XML without changing unrelated nodes."""
    result = content

    resolution = settings.get(RESOLUTION)
    if resolution and "x" in resolution:
        width, height = resolution.split("x", 1)
        result = _replace_xml_attr(result, "resolution", "width", width.strip())
        result = _replace_xml_attr(result, "resolution", "height", height.strip())

    screen_mode = settings.get(SCREEN_MODE)
    if screen_mode is not None:
        mode_map = {"Windowed": "0", "Fullscreen": "1", "Borderless Windowed": "2"}
        if screen_mode in mode_map:
            result = _replace_xml_attr(result, "resolution", "displayMode", mode_map[screen_mode])

    vsync = settings.get(VSYNC)
    if vsync is not None:
        result = _replace_xml_attr(result, "resolution", "vsync", "true" if vsync == "On" else "false")

    frame_limit = settings.get(FRAME_LIMIT)
    if frame_limit is not None:
        if frame_limit == "Unlimited":
            result = _replace_xml_attr(result, "resolution", "frameRateLimiterEnabled", "false")
        else:
            try:
                fps = int(frame_limit.replace(" FPS", ""))
            except ValueError:
                fps = None
            if fps is not None:
                result = _replace_xml_attr(result, "resolution", "frameRateLimiterEnabled", "true")
                result = _replace_xml_attr(result, "resolution", "frameRateLimiterValue", str(fps))

    upscaling = settings.get(UPSCALING)
    if upscaling is not None:
        quality = upscaling.rsplit("(", 1)[-1].rstrip(") ") if "(" in upscaling else ""
        quality_map = {"Quality": "0", "Balanced": "1", "Performance": "2", "Ultra Quality": "4", "Ultra Performance": "3"}
        quality_value = quality_map.get(quality)
        if "FSR" in upscaling:
            result = _replace_xml_attr(result, "antialiasing", "dlss", "false")
            result = _replace_xml_attr(result, "antialiasing", "fsr3", "1")
            result = _replace_xml_attr(result, "antialiasing", "xess", "false")
        elif "XeSS" in upscaling:
            result = _replace_xml_attr(result, "antialiasing", "dlss", "false")
            result = _replace_xml_attr(result, "antialiasing", "fsr3", "0")
            result = _replace_xml_attr(result, "antialiasing", "xess", "true")
        elif upscaling == "Off":
            result = _replace_xml_attr(result, "antialiasing", "dlss", "false")
            result = _replace_xml_attr(result, "antialiasing", "fsr3", "0")
            result = _replace_xml_attr(result, "antialiasing", "xess", "false")
        if quality_value is not None:
            result = _replace_xml_attr(result, "aa_quality", "value", quality_value)

    return result


# ── Registry JSON Writer ────────────────────────────────────────────

def _write_registry_json(
    content: str, settings: Dict[str, Optional[str]]
) -> str:
    """Patch registry-based JSON config (HZD, Shadow of TR)."""
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return content

    gfx = data.get("Graphics", data)

    # Resolution
    val = settings.get(RESOLUTION)
    if val and "x" in val:
        w, h = val.split("x", 1)
        for k in ("FullscreenWidth", "WindowWidth"):
            if k in gfx:
                gfx[k] = int(w.strip())
        for k in ("FullscreenHeight", "WindowHeight"):
            if k in gfx:
                gfx[k] = int(h.strip())

    # Screen Mode
    val = settings.get(SCREEN_MODE)
    if val is not None and "Fullscreen" in gfx:
        if val == "Windowed":
            gfx["Fullscreen"] = 0
        else:
            gfx["Fullscreen"] = 1
            if "ExclusiveFullscreen" in gfx:
                gfx["ExclusiveFullscreen"] = 1 if val == "Exclusive Fullscreen" else 0

    # VSync
    val = settings.get(VSYNC)
    if val is not None and "VSync" in gfx:
        gfx["VSync"] = 1 if val == "On" else 0

    # Frame Limit
    val = settings.get(FRAME_LIMIT)
    if val is not None and "DynamicResolutionTargetFPS" in gfx:
        if val == "Unlimited":
            gfx["DynamicResolutionTargetFPS"] = 0
        else:
            try:
                gfx["DynamicResolutionTargetFPS"] = int(val.replace(" FPS", ""))
            except ValueError:
                pass

    # Dynamic Resolution
    val = settings.get(DYNAMIC_RESOLUTION)
    if val is not None and "DynamicResolutionTargetFPS" in gfx:
        if val == "Off":
            gfx["DynamicResolutionTargetFPS"] = 0

    # Upscaling
    val = settings.get(UPSCALING)
    if val is not None and "UpscaleMethod" in gfx:
        method_map = {"Off": 0, "DLSS": 1, "FSR": 2, "CAS": 3, "XeSS": 4}
        for k, v in method_map.items():
            if k in val:
                gfx["UpscaleMethod"] = v
                break

    # Frame Generation
    val = settings.get(FRAME_GENERATION)
    if val is not None:
        if "FrameGen" in gfx:
            gfx["FrameGen"] = 0 if val == "Off" else 1
        if "DLSSG" in gfx:
            gfx["DLSSG"] = 0 if val == "Off" else 1

    return json.dumps(data, indent=2, ensure_ascii=False)


# ── CS2 Writer ──────────────────────────────────────────────────────

def _write_cs2_video(
    content: str, settings: Dict[str, Optional[str]]
) -> str:
    """Patch CS2 cs2_video.txt with new settings."""
    result = content

    # Resolution
    val = settings.get(RESOLUTION)
    if val and "x" in val:
        w, h = val.split("x", 1)
        result = _replace_valve_kv_value(result, "setting.defaultres", w.strip())
        result = _replace_valve_kv_value(result, "setting.defaultresheight", h.strip())

    # Screen Mode
    val = settings.get(SCREEN_MODE)
    if val is not None:
        if val == "Fullscreen":
            result = _replace_valve_kv_value(result, "setting.fullscreen", "1")
            result = _replace_valve_kv_value(result, "setting.nowindowborder", "0")
        elif val == "Borderless Windowed":
            result = _replace_valve_kv_value(result, "setting.fullscreen", "0")
            result = _replace_valve_kv_value(result, "setting.nowindowborder", "1")
        else:
            result = _replace_valve_kv_value(result, "setting.fullscreen", "0")
            result = _replace_valve_kv_value(result, "setting.nowindowborder", "0")

    # VSync
    val = settings.get(VSYNC)
    if val is not None:
        result = _replace_valve_kv_value(
            result, "setting.mat_vsync_mode", "1" if val == "On" else "0"
        )

    return result


# ── Main Dispatcher ─────────────────────────────────────────────────

def _detect_parser_type(game_name: str, config_files: List[Dict[str, Any]]) -> str:
    """Detect which parser type a game uses, returning a type string.

    Returns one of: ``"cyberpunk"``, ``"unreal_ini"``, ``"forza_xml"``,
    ``"registry_json"``, ``"cs2"``, ``"unknown"``.
    """
    name_lower = game_name.lower()

    if "cyberpunk" in name_lower:
        return "cyberpunk"
    if "counter-strike" in name_lower or "cs2" in name_lower:
        return "cs2"
    if "forza" in name_lower:
        return "forza_xml"
    if "f1" in name_lower and "25" in name_lower:
        return "f1_xml"

    readable = [c for c in config_files if c.get("content") and c.get("found")]

    for cfg in readable:
        if cfg.get("type") == "registry":
            return "registry_json"

    for cfg in readable:
        content = cfg.get("content", "")
        if "ResolutionSizeX" in content or "FullscreenMode" in content:
            return "unreal_ini"

    # Fallback: try to detect from file extension / content
    for cfg in readable:
        path = cfg.get("expanded_path", "")
        if path.endswith(".ini") or path.endswith(".cfg"):
            return "unreal_ini"
        if path.endswith(".xml"):
            return "forza_xml"
        if path.endswith(".json"):
            try:
                data = json.loads(cfg.get("content", ""))
                if "data" in data and isinstance(data.get("data"), list):
                    return "cyberpunk"
            except Exception:
                pass

    return "unknown"


def write_settings(
    game_name: str,
    config_files: List[Dict[str, Any]],
    settings: Dict[str, Optional[str]],
) -> List[Dict[str, str]]:
    """Write modified settings back to config files on disk.

    Parameters
    ----------
    game_name:
        The name of the game.
    config_files:
        The list of config file dicts (with ``expanded_path``, ``content``,
        ``found``, etc.) — same format as what the exporter produces.
    settings:
        Dict of the 7 key settings with their new values.
        Only settings with non-None values will be written.

    Returns
    -------
    list
        A list of dicts ``{"path": ..., "status": "ok"|"skipped"|"error", "detail": ...}``
        reporting what was written.
    """
    # Filter out None values — only write explicitly-set settings
    to_write = {k: v for k, v in settings.items() if v is not None}
    if not to_write:
        return []

    parser_type = _detect_parser_type(game_name, config_files)
    results: List[Dict[str, str]] = []

    readable = [c for c in config_files if c.get("content") and c.get("found")]

    if parser_type == "cyberpunk":
        for cfg in readable:
            path = cfg["expanded_path"]
            if "UserSettings" in path:
                try:
                    new_content = _write_cyberpunk(cfg["content"], to_write)
                    _safe_write(path, new_content)
                    results.append({"path": path, "status": "ok", "detail": "Cyberpunk settings written"})
                except Exception as e:
                    results.append({"path": path, "status": "error", "detail": str(e)})
                break
        else:
            results.append({"path": "", "status": "skipped", "detail": "No UserSettings.json found"})

    elif parser_type == "unreal_ini":
        for cfg in readable:
            path = cfg["expanded_path"]
            content = cfg["content"]
            if "ResolutionSizeX" in content or "FullscreenMode" in content or "GameUserSettings" in path:
                try:
                    new_content = _write_unreal_ini(content, to_write)
                    _safe_write(path, new_content)
                    results.append({"path": path, "status": "ok", "detail": "Unreal INI settings written"})
                except Exception as e:
                    results.append({"path": path, "status": "error", "detail": str(e)})
                break
        else:
            results.append({"path": "", "status": "skipped", "detail": "No GameUserSettings.ini found"})

    elif parser_type == "forza_xml":
        for cfg in readable:
            path = cfg["expanded_path"]
            if "UserConfigSelections" in path or "ConfigSelections" in path or path.endswith(".xml"):
                try:
                    new_content = _write_forza_xml(cfg["content"], to_write)
                    _safe_write(path, new_content)
                    results.append({"path": path, "status": "ok", "detail": "Forza XML settings written"})
                    if SCREEN_MODE in to_write:
                        fullscreen_value = bytes([1 if to_write[SCREEN_MODE] == "Fullscreen" else 0])
                        for auxiliary_path in forza_auxiliary_paths(config_files):
                            with open(auxiliary_path, "wb") as auxiliary_file:
                                auxiliary_file.write(fullscreen_value)
                            results.append({"path": auxiliary_path, "status": "ok", "detail": "Forza fullscreen choice written"})
                except Exception as e:
                    results.append({"path": path, "status": "error", "detail": str(e)})
                break

    elif parser_type == "f1_xml":
        for cfg in readable:
            path = cfg["expanded_path"]
            if path.endswith(".xml") or "hardware_settings_config" in path:
                try:
                    new_content = _write_f1_xml(cfg["content"], to_write)
                    _safe_write(path, new_content)
                    results.append({"path": path, "status": "ok", "detail": "F1 25 XML settings written"})
                except Exception as e:
                    results.append({"path": path, "status": "error", "detail": str(e)})
                break
        else:
            results.append({"path": "", "status": "skipped", "detail": "No F1 hardware settings XML found"})

    elif parser_type == "registry_json":
        for cfg in readable:
            if cfg.get("type") == "registry":
                try:
                    new_content = _write_registry_json(cfg["content"], to_write)
                    # Registry entries need special handling — write back to the
                    # registry, not a file.  For now, store the JSON and report.
                    path = cfg["expanded_path"]
                    _write_registry_values(path, new_content)
                    results.append({"path": path, "status": "ok", "detail": "Registry settings written"})
                except Exception as e:
                    results.append({"path": cfg.get("expanded_path", ""), "status": "error", "detail": str(e)})
                break

    elif parser_type == "cs2":
        for cfg in readable:
            path = cfg["expanded_path"]
            if "cs2_video" in path.lower():
                try:
                    new_content = _write_cs2_video(cfg["content"], to_write)
                    _safe_write(path, new_content)
                    results.append({"path": path, "status": "ok", "detail": "CS2 video settings written"})
                except Exception as e:
                    results.append({"path": path, "status": "error", "detail": str(e)})
                break

    else:
        results.append({"path": "", "status": "skipped", "detail": f"Unknown parser type for '{game_name}'"})

    return results


def _write_registry_values(reg_path: str, json_content: str) -> None:
    """Write settings back to the Windows registry.

    *reg_path* is the expanded registry path (e.g.
    ``HKEY_CURRENT_USER\\Software\\...``).  *json_content* is the full
    JSON string representing the registry key's values.
    """
    if os.name != "nt":
        raise OSError("Registry writes are only supported on Windows")

    import winreg

    try:
        data = json.loads(json_content)
    except (json.JSONDecodeError, ValueError) as e:
        raise ValueError(f"Invalid registry JSON: {e}") from e

    # Parse the registry path
    hive_map = {
        "HKEY_CURRENT_USER": winreg.HKEY_CURRENT_USER,
        "HKCU": winreg.HKEY_CURRENT_USER,
        "HKEY_LOCAL_MACHINE": winreg.HKEY_LOCAL_MACHINE,
        "HKLM": winreg.HKEY_LOCAL_MACHINE,
    }

    parts = reg_path.replace("/", "\\").split("\\")
    hive_name = parts[0].upper()
    hive = hive_map.get(hive_name)
    if hive is None:
        raise ValueError(f"Unknown registry hive: {hive_name}")

    subkey = "\\".join(parts[1:])

    # Flatten the data if it has a top-level "Graphics" key
    values = data.get("Graphics", data)

    with winreg.OpenKey(hive, subkey, 0, winreg.KEY_WRITE) as key:
        for name, value in values.items():
            if isinstance(value, int):
                winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, value)
            elif isinstance(value, str):
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
