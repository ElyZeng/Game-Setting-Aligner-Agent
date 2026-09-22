"""Parse key graphics settings from game config file content.

Extracts 9 standardised settings from various config formats:
1. Resolution
2. Screen Mode
3. V-Sync
4. Frame Limit
5. Dynamic Resolution
6. Upscaling Method (DLSS / FSR / XeSS)
7. Upscaling Mode (Quality / Balanced / Performance, etc.)
8. Frame Generation / Multi Frame Generation
9. Quick Preset
"""

from __future__ import annotations

import json
import os
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional


# Result key constants
RESOLUTION = "resolution"
SCREEN_MODE = "screen_mode"
VSYNC = "vsync"
FRAME_LIMIT = "frame_limit"
DYNAMIC_RESOLUTION = "dynamic_resolution"
UPSCALING = "upscaling"
UPSCALING_MODE = "upscaling_mode"
FRAME_GENERATION = "frame_generation"
QUICK_PRESET = "quick_preset"

BLACK_MYTH_SCALABILITY_KEYS = (
    "sg.ViewDistanceQuality",
    "sg.AntiAliasingQuality",
    "sg.ShadowQuality",
    "sg.GlobalIlluminationQuality",
    "sg.RayTracingQuality",
    "sg.ReflectionQuality",
    "sg.PostProcessQuality",
    "sg.TextureQuality",
    "sg.EffectsQuality",
    "sg.FoliageQuality",
    "sg.ShadingQuality",
)

ALL_KEYS = [
    RESOLUTION,
    SCREEN_MODE,
    VSYNC,
    FRAME_LIMIT,
    DYNAMIC_RESOLUTION,
    UPSCALING,
    UPSCALING_MODE,
    FRAME_GENERATION,
    QUICK_PRESET,
]

# Human-readable display names (Chinese)
DISPLAY_NAMES = {
    RESOLUTION: "解析度",
    SCREEN_MODE: "螢幕模式",
    VSYNC: "垂直同步",
    FRAME_LIMIT: "幀率限制",
    DYNAMIC_RESOLUTION: "動態解析度",
    UPSCALING: "升頻技術",
    UPSCALING_MODE: "升頻模式",
    FRAME_GENERATION: "畫格生成",
    QUICK_PRESET: "畫質預設",
}

DISPLAY_NAMES_EN = {
    RESOLUTION: "Resolution",
    SCREEN_MODE: "Screen Mode",
    VSYNC: "V-Sync",
    FRAME_LIMIT: "Frame Limit",
    DYNAMIC_RESOLUTION: "Dynamic Resolution",
    UPSCALING: "Upscaling Method",
    UPSCALING_MODE: "Upscaling Mode",
    FRAME_GENERATION: "Frame Generation",
    QUICK_PRESET: "Quick Preset",
}

# Dropdown options for each setting.  The first value is the default /
# "no change" sentinel shown when the user has not explicitly picked a
# value.  The rest are the selectable choices.
SETTING_OPTIONS: Dict[str, List[str]] = {
    RESOLUTION: [
        "—",
        "1280x720",
        "1600x900",
        "1920x1080",
        "2560x1080",
        "2560x1440",
        "3440x1440",
        "3840x2160",
    ],
    SCREEN_MODE: [
        "—",
        "Fullscreen",
        "Borderless Windowed",
        "Windowed",
    ],
    VSYNC: [
        "—",
        "On",
        "Off",
    ],
    FRAME_LIMIT: [
        "—",
        "Unlimited",
        "30 FPS",
        "60 FPS",
        "120 FPS",
        "144 FPS",
        "240 FPS",
    ],
    DYNAMIC_RESOLUTION: [
        "—",
        "On",
        "Off",
    ],
    UPSCALING: [
        "—",
        "Off",
        "DLSS",
        "FSR",
        "XeSS",
        "TSR",
        "CAS",
    ],
    UPSCALING_MODE: [
        "—",
        "Auto",
        "Native AA",
        "Ultra Quality Plus",
        "Ultra Quality",
        "Quality",
        "Balanced",
        "Performance",
        "Ultra Performance",
        "Dynamic",
    ],
    FRAME_GENERATION: [
        "—",
        "Off",
        "On",
    ],
    # Quick Preset uses per-game options; this is the generic fallback.
    QUICK_PRESET: [
        "—",
    ],
}

FORZA_SETTING_OPTIONS: Dict[str, List[str]] = {
    SCREEN_MODE: ["—", "Fullscreen", "Windowed"],
    FRAME_LIMIT: ["—", "20 FPS", "30 FPS", "60 FPS", "Unlimited"],
    UPSCALING: ["—", "Off", "DLSS", "FSR", "XeSS"],
    QUICK_PRESET: ["—", "Very Low", "Low", "Medium", "High", "Ultra", "Extreme"],
}

F1_SETTING_OPTIONS: Dict[str, List[str]] = {
    RESOLUTION: ["—", "1280x720", "1920x1080", "2560x1440", "3840x2160"],
    SCREEN_MODE: ["—", "Fullscreen", "Borderless Windowed", "Windowed"],
    VSYNC: ["—", "On", "Off"],
    FRAME_LIMIT: ["—", "30 FPS", "60 FPS", "120 FPS", "144 FPS", "Unlimited"],
    UPSCALING: ["—", "Off", "DLSS", "FSR", "XeSS"],
    FRAME_GENERATION: ["—", "Off", "AMD FSR3", "XeFG"],
    QUICK_PRESET: ["—", "Ultra Low", "Low", "Medium", "High", "Ultra High", "Ultra Max"],
}

BLACK_MYTH_UPSCALING_MODES = {
    33: "Ultra Performance",
    50: "Performance",
    66: "Balanced",
    75: "Quality",
    100: "Native AA",
}


def _black_myth_upscaling_mode(percentage: int) -> str:
    closest = min(BLACK_MYTH_UPSCALING_MODES, key=lambda value: abs(value - percentage))
    return f"{BLACK_MYTH_UPSCALING_MODES[closest]} ({percentage}%)"

FORZA_PRESET_SIGNATURES: Dict[str, Dict[str, str]] = {
    "Very Low": {"CarLOD": "0", "EnvStreamingTex": "0", "GeometryQuality": "0", "ReflectionQuality": "0", "SSRQuality": "0", "RTReflectionQuality": "0", "ShadowQuality": "0", "NightShadows": "0", "SSGIQuality": "0", "RTGIQuality": "0", "ShaderQuality": "0", "AudioQuality": "0", "DeformableSnowQuality": "0", "ParticlesSettings": "0", "VolumetricFogQuality": "0", "LensEffects": "0", "MotionBlurQuality": "0"},
    "Low": {"CarLOD": "0", "EnvStreamingTex": "0", "GeometryQuality": "1", "ReflectionQuality": "1", "SSRQuality": "1", "RTReflectionQuality": "0", "ShadowQuality": "1", "NightShadows": "0", "SSGIQuality": "0", "RTGIQuality": "0", "ShaderQuality": "1", "AudioQuality": "1", "DeformableSnowQuality": "0", "ParticlesSettings": "1", "VolumetricFogQuality": "1", "LensEffects": "1", "MotionBlurQuality": "0"},
    "Medium": {"CarLOD": "1", "EnvStreamingTex": "1", "GeometryQuality": "2", "ReflectionQuality": "2", "SSRQuality": "2", "RTReflectionQuality": "0", "ShadowQuality": "2", "NightShadows": "0", "SSGIQuality": "1", "RTGIQuality": "0", "ShaderQuality": "1", "AudioQuality": "2", "DeformableSnowQuality": "1", "ParticlesSettings": "1", "VolumetricFogQuality": "2", "LensEffects": "2", "MotionBlurQuality": "1"},
    "High": {"CarLOD": "2", "EnvStreamingTex": "2", "GeometryQuality": "3", "ReflectionQuality": "3", "SSRQuality": "3", "RTReflectionQuality": "0", "ShadowQuality": "2", "NightShadows": "0", "SSGIQuality": "1", "RTGIQuality": "0", "ShaderQuality": "2", "AudioQuality": "3", "DeformableSnowQuality": "2", "ParticlesSettings": "2", "VolumetricFogQuality": "3", "LensEffects": "3", "MotionBlurQuality": "2"},
    "Ultra": {"CarLOD": "3", "EnvStreamingTex": "3", "GeometryQuality": "4", "ReflectionQuality": "3", "SSRQuality": "4", "RTReflectionQuality": "0", "ShadowQuality": "3", "NightShadows": "1", "SSGIQuality": "2", "RTGIQuality": "0", "ShaderQuality": "3", "AudioQuality": "4", "DeformableSnowQuality": "3", "ParticlesSettings": "3", "VolumetricFogQuality": "4", "LensEffects": "4", "MotionBlurQuality": "3"},
    "Extreme": {"CarLOD": "4", "EnvStreamingTex": "4", "GeometryQuality": "5", "ReflectionQuality": "4", "SSRQuality": "5", "RTReflectionQuality": "0", "ShadowQuality": "4", "NightShadows": "2", "SSGIQuality": "2", "RTGIQuality": "0", "ShaderQuality": "4", "AudioQuality": "4", "DeformableSnowQuality": "4", "ParticlesSettings": "4", "VolumetricFogQuality": "5", "LensEffects": "4", "MotionBlurQuality": "3"},
}

F1_PRESET_SIGNATURES: Dict[str, Dict[str, str]] = {
    "Ultra Low": {
        "ssrt.quality": "0",
        "lighting.quality": "0",
        "shadows.sampling": "1",
        "weather_effects.proceduralCloudQuality": "1",
        "texture_streaming.sizeInMiB": "256",
        "particles.enabled": "false",
        "particles.high": "true",
        "shadows.skyShadowMapSize": "512",
        "vehicle_reflections.envMapScale": "0.25",
        "ground_cover.enabled": "false",
    },
    "Low": {
        "ssrt.quality": "0",
        "lighting.quality": "0",
        "shadows.sampling": "1",
        "weather_effects.proceduralCloudQuality": "1",
        "texture_streaming.sizeInMiB": "512",
        "particles.enabled": "true",
        "particles.distanceScale": "3.0",
        "particles.high": "false",
        "shadows.skyShadowMapSize": "1024",
        "vehicle_reflections.envMapScale": "0.5",
    },
    "Medium": {
        "ssrt.quality": "2",
        "lighting.quality": "1",
        "shadows.sampling": "1",
        "weather_effects.proceduralCloudQuality": "1",
        "texture_streaming.sizeInMiB": "1024",
        "particles.enabled": "true",
        "particles.distanceScale": "1.0",
        "particles.high": "false",
        "vehicle_reflections.envMapScale": "1.0",
        "ground_cover.enabled": "true",
    },
    "High": {
        "ssrt.quality": "3",
        "lighting.quality": "2",
        "shadows.sampling": "2",
        "weather_effects.proceduralCloudQuality": "1",
        "texture_streaming.sizeInMiB": "1536",
        "particles.high": "true",
        "rt_pathtrace.enabled": "false",
    },
    "Ultra High": {
        "lighting.quality": "3",
        "ssrt.quality": "4",
        "shadows.sampling": "3",
        "weather_effects.proceduralCloudQuality": "1",
        "texture_streaming.sizeInMiB": "2048",
        "rt_pathtrace.enabled": "false",
    },
    "Ultra Max": {
        "lighting.quality": "3",
        "ssrt.quality": "4",
        "shadows.sampling": "3",
        "weather_effects.proceduralCloudQuality": "1",
        "texture_streaming.sizeInMiB": "2048",
        "rt_pathtrace.enabled": "true",
    },
}


def _query_desktop_display_mode() -> tuple[Optional[str], Optional[int]]:
    if os.name != "nt":
        return None, None
    try:
        import ctypes
        from ctypes import wintypes

        class Point(ctypes.Structure):
            _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

        class DevMode(ctypes.Structure):
            _fields_ = [
                ("dmDeviceName", wintypes.WCHAR * 32),
                ("dmSpecVersion", wintypes.WORD),
                ("dmDriverVersion", wintypes.WORD),
                ("dmSize", wintypes.WORD),
                ("dmDriverExtra", wintypes.WORD),
                ("dmFields", wintypes.DWORD),
                ("dmPosition", Point),
                ("dmDisplayOrientation", wintypes.DWORD),
                ("dmDisplayFixedOutput", wintypes.DWORD),
                ("dmColor", wintypes.SHORT),
                ("dmDuplex", wintypes.SHORT),
                ("dmYResolution", wintypes.SHORT),
                ("dmTTOption", wintypes.SHORT),
                ("dmCollate", wintypes.SHORT),
                ("dmFormName", wintypes.WCHAR * 32),
                ("dmLogPixels", wintypes.WORD),
                ("dmBitsPerPel", wintypes.DWORD),
                ("dmPelsWidth", wintypes.DWORD),
                ("dmPelsHeight", wintypes.DWORD),
                ("dmDisplayFlags", wintypes.DWORD),
                ("dmDisplayFrequency", wintypes.DWORD),
                ("dmICMMethod", wintypes.DWORD),
                ("dmICMIntent", wintypes.DWORD),
                ("dmMediaType", wintypes.DWORD),
                ("dmDitherType", wintypes.DWORD),
                ("dmReserved1", wintypes.DWORD),
                ("dmReserved2", wintypes.DWORD),
                ("dmPanningWidth", wintypes.DWORD),
                ("dmPanningHeight", wintypes.DWORD),
            ]

        mode = DevMode()
        mode.dmSize = ctypes.sizeof(DevMode)
        if ctypes.windll.user32.EnumDisplaySettingsW(None, -1, ctypes.byref(mode)):
            resolution = f"{mode.dmPelsWidth}x{mode.dmPelsHeight}"
            return resolution, int(mode.dmDisplayFrequency)
    except (AttributeError, OSError, ValueError):
        pass
    return None, None


def desktop_display_mode() -> tuple[Optional[str], Optional[int]]:
    """Return the current primary desktop resolution and nominal refresh rate."""
    return _query_desktop_display_mode()


def _cyberpunk_vsync_options(refresh_rate: int) -> List[str]:
    values = []
    for divisor in range(1, 5):
        value = refresh_rate // divisor
        if value >= 30 and value not in values:
            values.append(value)
    return ["—", "Off", *(str(value) for value in values)]


def setting_options_for_game(
    game_name: str,
    key: str,
    current_value: Optional[str] = None,
    *,
    desktop_resolution: Optional[str] = None,
    refresh_rate: Optional[int] = None,
    upscaling_method: Optional[str] = None,
) -> List[str]:
    name = game_name.casefold()
    if "black myth" in name or "wukong" in name:
        if key == DYNAMIC_RESOLUTION:
            return ["—"]
        if "benchmark" in name and key == SCREEN_MODE:
            return ["—", "Borderless Windowed", "Windowed"]
        if "benchmark" in name and key == UPSCALING:
            return ["—", "TSR", "FSR", "XeSS"]
        if key == UPSCALING:
            return ["—", "TSR", "NXSR", "FSR3", "XeSS"]
        if key == UPSCALING_MODE:
            if "benchmark" in name or upscaling_method is None:
                return ["—"]
            return [
                "—",
                *(f"{name} ({percentage}%)" for percentage, name in BLACK_MYTH_UPSCALING_MODES.items()),
            ]
        if key == FRAME_GENERATION:
            if "benchmark" in name:
                return ["—", "Off", "On"] if upscaling_method in {"TSR", "FSR"} else ["—"]
            return ["—", "Off", "Auto"] if upscaling_method == "XeSS" else ["—", "Off"]
        if key == QUICK_PRESET:
            return ["—", "Custom", "Low", "Medium", "High", "Very High", "Cinematic"]
    if "street fighter" in name or "streetfighter" in name:
        if key == UPSCALING_MODE:
            return ["—"]
    if "counter-strike" in name or "cs2" in name:
        if key == UPSCALING:
            return ["—", "Off", "FSR"]
        if key == UPSCALING_MODE:
            return ["—", "Ultra Quality", "Quality", "Balanced", "Performance"] if upscaling_method == "FSR" else ["—"]
    if "horizon zero dawn" in name or "shadow of the tomb raider" in name:
        if key == UPSCALING:
            return ["—", "Off", "DLSS", "FSR", "CAS", "XeSS"]
        if key == UPSCALING_MODE:
            return ["—", "Ultra Performance", "Performance", "Balanced", "Quality", "Ultra Quality"] if upscaling_method not in {None, "Off"} else ["—"]
    if "f1" in name and "25" in name:
        if key == UPSCALING_MODE:
            modes = {
                "DLSS": ["Quality", "Balanced", "Performance", "Ultra Quality"],
                "FSR": ["Quality", "Balanced", "Performance", "Ultra Performance"],
                "XeSS": ["Quality", "Balanced", "Performance", "Ultra Quality"],
            }
            return ["—", *modes.get(upscaling_method or "", [])]
        if key in F1_SETTING_OPTIONS:
            return F1_SETTING_OPTIONS[key]
    if "forza horizon 6" in name:
        if key == UPSCALING_MODE:
            modes = {
                "DLSS": ["Preset 1"],
                "FSR": ["Quality", "Balanced", "Performance", "Ultra Performance"],
                "XeSS": ["Ultra Quality Plus", "Ultra Quality", "Quality", "Balanced", "Performance", "Ultra Performance"],
            }
            return ["—", *modes.get(upscaling_method or "", [])]
        if key in FORZA_SETTING_OPTIONS:
            return FORZA_SETTING_OPTIONS[key]
    if "cyberpunk" in game_name.casefold():
        detected_resolution, detected_refresh = desktop_display_mode()
        if key == SCREEN_MODE:
            return ["—", "Windowed", "Borderless Windowed"]
        if key == RESOLUTION:
            recommendation = desktop_resolution or detected_resolution
            return [
                f"{option} (recommended for proper scaling)" if option == recommendation else option
                for option in ["—", "1920x1080", "2560x1440"]
            ]
        if key == VSYNC:
            nominal_refresh = refresh_rate or detected_refresh
            if nominal_refresh:
                return _cyberpunk_vsync_options(nominal_refresh)
        if key == FRAME_LIMIT:
            return ["—", "Off", "30 FPS", "60 FPS", "120 FPS", "144 FPS", "240 FPS"]
        if key == UPSCALING:
            return ["—", "Off", "FSR 2.1", "FSR 3", "XeSS"]
        if key == UPSCALING_MODE:
            mode_options = {
                "FSR 2.1": ["Auto", "Quality", "Balanced", "Performance", "Ultra Performance"],
                "FSR 3": ["Auto", "Native AA", "Quality", "Balanced", "Performance", "Ultra Performance", "Dynamic"],
                "XeSS": ["Auto", "Ultra Quality Plus", "Ultra Quality", "Quality", "Balanced", "Performance", "Dynamic"],
            }
            return ["—", *mode_options.get(upscaling_method or "", [])]
        if key == QUICK_PRESET:
            return QUICK_PRESET_OPTIONS["cyberpunk"]
    return SETTING_OPTIONS.get(key, ["—"])


def is_setting_writable_for_game(game_name: str, key: str) -> bool:
    """Return whether the GUI should offer an Apply dropdown for this setting."""
    if "cyberpunk" in game_name.casefold() and key in {DYNAMIC_RESOLUTION, FRAME_GENERATION}:
        return False
    return True

# Per-game Quick Preset option lists keyed by parser-type string.
QUICK_PRESET_OPTIONS: Dict[str, List[str]] = {
    # Cyberpunk 2077 — QuickPresets field in UserSettings.json; known values from game UI
    "cyberpunk": [
        "—",
        "Low",
        "Medium",
        "High",
        "Ultra",
        "Ray Tracing Medium",
        "Ray Tracing High",
        "Ray Tracing Ultra",
        "Path Tracing",
    ],
    # Unreal Engine games using GPUConfigPreset integer (Hogwarts Legacy, etc.)
    "unreal_ini": [
        "—",
        "Low",
        "Medium",
        "High",
        "Ultra",
    ],
    # Forza Horizon XML — no single overall preset field
    "forza_xml": ["—"],
    # Registry-based games — no known preset field
    "registry_json": ["—"],
    # CS2 — no preset support
    "cs2": ["—"],
    # Unknown / generic
    "default": ["—"],
}


def _empty_result() -> Dict[str, Optional[str]]:
    return {k: None for k in ALL_KEYS}


# ── Cyberpunk 2077 (UserSettings.json) ───────────────────────────────

def _parse_cyberpunk(content: str) -> Dict[str, Optional[str]]:
    r = _empty_result()
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return r

    groups = data.get("data", [])
    options_map: Dict[str, Any] = {}
    for group in groups:
        gname = group.get("group_name", "")
        for opt in group.get("options", []):
            key = f"{gname}/{opt['name']}"
            options_map[opt["name"]] = opt
            options_map[key] = opt

    # Resolution
    res_opt = options_map.get("/video/display/Resolution")
    if res_opt:
        r[RESOLUTION] = str(res_opt.get("value", ""))

    # Screen Mode
    wm = options_map.get("WindowMode") or options_map.get("/video/display/WindowMode")
    uses_current_schema = bool(wm and isinstance(wm.get("value"), str))
    if wm:
        mode = wm.get("value", "")
        mode_map = {
            0: "Fullscreen",
            1: "Borderless Windowed",
            2: "Windowed",
            "Fullscreen": "Fullscreen",
            "BorderlessWindowed": "Borderless Windowed",
            "Windowed": "Windowed",
        }
        r[SCREEN_MODE] = mode_map.get(mode, str(mode))

    # VSync
    vs = options_map.get("VSync") or options_map.get("/video/display/VSync")
    if vs:
        val = str(vs.get("value", ""))
        if "Off" in val:
            r[VSYNC] = "Off"
        elif "On" in val:
            r[VSYNC] = "On"
        else:
            r[VSYNC] = val

    # Frame Limit
    fps_on = options_map.get("MaximumFPS_OnOff")
    fps_val = options_map.get("MaximumFPS_Value") or options_map.get("MaximumFPS")
    if fps_on is not None:
        on = fps_on.get("value", False)
        limit = fps_val.get("value", "") if fps_val else ""
        r[FRAME_LIMIT] = f"{limit}" if on else "Off"

    # Dynamic Resolution
    drs = options_map.get("DynamicResolutionScaling")
    drs_fps = options_map.get("DRS_TargetFPS")
    if uses_current_schema:
        r[DYNAMIC_RESOLUTION] = "N/A"
    elif drs is not None:
        on = drs.get("value", False)
        target = drs_fps.get("value", "") if drs_fps else ""
        r[DYNAMIC_RESOLUTION] = f"On (Target: {target} FPS)" if on else "Off"

    # Upscaling
    rs = options_map.get("ResolutionScaling")
    if rs:
        method = str(rs.get("value", "Off"))
        display_method = {"FSR2": "FSR 2.1", "FSR3": "FSR 3"}.get(method, method)
        method_opt = options_map.get(method.upper()) or options_map.get(method)
        r[UPSCALING] = display_method
        if method == "Off":
            r[UPSCALING_MODE] = "N/A"
        elif method_opt:
            mode = str(method_opt.get("value", ""))
            r[UPSCALING_MODE] = {
                "NativeAA": "Native AA",
                "UltraPerformance": "Ultra Performance",
            }.get(mode, mode)

    # Frame Generation
    fg = options_map.get("FrameGeneration")
    xess_fg = options_map.get("XESS_FrameGeneration")
    mfg = options_map.get("DLSS_MultiFrameGeneration")
    if fg is not None:
        value = fg.get("value")
        if value in (False, 0, "0", "false", "False", "Off", "off"):
            r[FRAME_GENERATION] = "Off"
        elif (
            str(value).upper() == "XESS"
            and xess_fg is not None
            and xess_fg.get("value") in (False, 0, "0", "false", "False", "Off", "off")
        ):
            r[FRAME_GENERATION] = "Off"
        elif value in (True, 1, "1", "true", "True", "On", "on") or (
            str(value).upper() == "XESS"
            and xess_fg is not None
            and xess_fg.get("value") in (True, 1, "1", "true", "True", "On", "on")
        ):
            mfg_value = mfg.get("value") if mfg is not None else None
            if mfg_value not in (None, "", 0, "0", "false", "False", "Off", "off"):
                r[FRAME_GENERATION] = f"On / MFG: {mfg_value}"
            else:
                r[FRAME_GENERATION] = "On"
        else:
            r[FRAME_GENERATION] = "N/A"

    # Quick Preset — stored under /graphics/presets/QuickPresets
    qp = options_map.get("/graphics/presets/QuickPresets") or options_map.get("QuickPresets")
    if qp is not None:
        r[QUICK_PRESET] = str(qp.get("value", "Custom"))

    return r


def _parse_black_myth(content: str, *, benchmark: bool = False) -> Dict[str, Optional[str]]:
    """Parse Black Myth: Wukong's Unreal config and UISettingData tuple."""
    r = _parse_unreal_ini(content)
    ui_values = dict(re.findall(r'\("([^"]+)",\s*"([^"]*)"\)', content))

    ini_values = _parse_ini_kv(content)
    borderless = benchmark and ui_values.get("ScreenMode") == "1"
    if borderless:
        base_width = _parse_positive_int(ini_values.get("ResolutionSizeX"))
        base_height = _parse_positive_int(ini_values.get("ResolutionSizeY"))
        window_scale = _parse_positive_int(ui_values.get("WindowFullImageQuality"))
        if base_width is not None and base_height is not None and window_scale is not None:
            confirmed_width = (base_width * window_scale + 500_000) // 1_000_000
            confirmed_height = (base_height * window_scale + 500_000) // 1_000_000
        else:
            confirmed_width = None
            confirmed_height = None
    elif benchmark:
        confirmed_width = _parse_positive_int(ini_values.get("LastUserConfirmedResolutionSizeX"))
        confirmed_height = _parse_positive_int(ini_values.get("LastUserConfirmedResolutionSizeY"))
    else:
        confirmed_width = None
        confirmed_height = None
    if benchmark and not borderless and (confirmed_width is None or confirmed_height is None):
        confirmed_width = _parse_positive_int(ini_values.get("LastUserConfirmedDesiredScreenWidth"))
        confirmed_height = _parse_positive_int(ini_values.get("LastUserConfirmedDesiredScreenHeight"))
    if confirmed_width is not None and confirmed_height is not None:
        r[RESOLUTION] = f"{confirmed_width}x{confirmed_height}"

    image_quality = ui_values.get("ImageQuality")
    screen_ratio = ui_values.get("ScreenRatio")
    if not benchmark and r[RESOLUTION] is None and image_quality and screen_ratio == "0":
        try:
            height = int(image_quality)
            standard_heights = (720, 900, 1080, 1440, 2160)
            closest_height = min(standard_heights, key=lambda value: abs(value - height))
            if abs(closest_height - height) <= 1:
                r[RESOLUTION] = f"{round(closest_height * 16 / 9)}x{closest_height}"
        except ValueError:
            pass

    screen_mode = ui_values.get("ScreenMode")
    if screen_mode is not None:
        r[SCREEN_MODE] = {
            "0": "Fullscreen",
            "1": "Borderless Windowed",
            "2": "Windowed",
        }.get(screen_mode, f"Mode {screen_mode}")

    vsync = ui_values.get("Vsync")
    if vsync is not None:
        r[VSYNC] = "On" if vsync in {"1", "true", "True"} else "Off"

    quality = ui_values.get("QualityLevel")
    if quality is not None:
        preset = {
            "0": "Custom",
            "1": "Low",
            "2": "Medium",
            "3": "High",
            "4": "Very High",
            "5": "Cinematic",
        }.get(quality, f"Quality Level {quality}")
        scalability_values = [
            ini_values[key] for key in BLACK_MYTH_SCALABILITY_KEYS
            if key in ini_values
        ]
        expected_level = str(int(quality) - 1) if quality.isdigit() and quality != "0" else None
        r[QUICK_PRESET] = (
            "Custom"
            if expected_level is not None
            and scalability_values
            and any(value != expected_level for value in scalability_values)
            else preset
        )

    super_resolution = ui_values.get("SuperResolutionSampling")
    if super_resolution is not None:
        mapping = {"3": "XeSS"} if benchmark else {
            "0": "FSR3",
            "1": "XeSS",
            "3": "TSR",
            "5": "NXSR",
        }
        r[UPSCALING] = mapping.get(super_resolution, f"Super Resolution (mode {super_resolution})")
        resolution_quality = _parse_positive_int(ini_values.get("sg.ResolutionQuality"))
        if not benchmark and resolution_quality is not None:
            r[UPSCALING_MODE] = _black_myth_upscaling_mode(resolution_quality)
        else:
            r[UPSCALING_MODE] = "N/A"

    insert_frame = ui_values.get("InsertFrame")
    if insert_frame is not None:
        if benchmark and r[UPSCALING] == "XeSS":
            r[FRAME_GENERATION] = "N/A"
        elif not benchmark and r[UPSCALING] != "XeSS":
            r[FRAME_GENERATION] = "Off"
        else:
            r[FRAME_GENERATION] = {
                "0": "Off",
                "1": "Auto",
            }.get(insert_frame, f"Mode {insert_frame}")

    r[DYNAMIC_RESOLUTION] = "N/A"

    return r


def _parse_positive_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _parse_expedition_33(content: str) -> Dict[str, Optional[str]]:
    """Parse Expedition 33's Unreal settings and scalability preset."""
    r = _parse_unreal_ini(content)
    kv = _parse_ini_kv(content)
    quality_values = {
        value
        for key, value in kv.items()
        if key.startswith("sg.")
        and key.endswith("Quality")
        and key != "sg.ResolutionQuality"
    }
    quality_map = {"0": "Low", "1": "Medium", "2": "High", "3": "Epic", "4": "Cinematic"}
    if len(quality_values) == 1:
        value = next(iter(quality_values))
        r[QUICK_PRESET] = quality_map.get(value, f"Quality Level {value}")
    elif quality_values:
        r[QUICK_PRESET] = "Custom"
    return r


# ── Unreal Engine INI (ARC Raiders, Hogwarts Legacy, etc.) ───────────

def _parse_ini_kv(content: str) -> Dict[str, str]:
    """Parse simple key=value lines from INI-like content."""
    kv: Dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("[") and not line.startswith(";"):
            key, _, val = line.partition("=")
            kv[key.strip()] = val.strip()
    return kv


def _parse_unreal_ini(content: str) -> Dict[str, Optional[str]]:
    r = _empty_result()
    kv = _parse_ini_kv(content)

    # Resolution
    rx, ry = kv.get("ResolutionSizeX"), kv.get("ResolutionSizeY")
    if rx and ry:
        r[RESOLUTION] = f"{rx}x{ry}"

    # Screen Mode
    fm = kv.get("FullscreenMode")
    mode_map = {"0": "Fullscreen", "1": "Borderless Windowed", "2": "Windowed"}
    if fm is not None:
        r[SCREEN_MODE] = mode_map.get(fm, f"Mode {fm}")

    # VSync
    vs = kv.get("bUseVSync")
    if vs is not None:
        r[VSYNC] = "On" if vs.lower() == "true" else "Off"

    # Frame Limit
    frl = kv.get("FrameRateLimit")
    if frl is not None:
        try:
            val = float(frl)
            r[FRAME_LIMIT] = "Unlimited" if val <= 0 else f"{val:.0f} FPS"
        except ValueError:
            r[FRAME_LIMIT] = frl

    # Dynamic Resolution
    dr = kv.get("bUseDynamicResolution")
    if dr is not None:
        r[DYNAMIC_RESOLUTION] = "On" if dr.lower() == "true" else "Off"

    # Upscaling
    method = kv.get("ResolutionScalingMethod", "")
    selected_upscaler = kv.get("CurrentSelectedUpscaler", "")
    dlss = kv.get("DLSSMode", "")
    fsr = kv.get("FSRMode", "")
    xess = kv.get("XeSSMode", "")
    if selected_upscaler:
        quality_mode = kv.get("CurrentSelectedUpscalerQualityMode", "")
        r[UPSCALING] = selected_upscaler
        r[UPSCALING_MODE] = quality_mode or "N/A"
    elif method:
        quality = {"DLSS": dlss, "FSR": fsr, "XeSS": xess}.get(method, "")
        r[UPSCALING] = method
        r[UPSCALING_MODE] = quality or "N/A"

    # Frame Generation
    dlss_fg = kv.get("DLSSFrameGenerationMode", "")
    fsr_fg = kv.get("FSRFrameGenerationMode", "")
    selected_fg = kv.get("CurrentSelectedFrameGenerationMode", "")
    parts = []
    if dlss_fg and dlss_fg != "Off":
        parts.append(f"DLSS FG: {dlss_fg}")
    if fsr_fg and fsr_fg != "Off":
        parts.append(f"FSR FG: {fsr_fg}")
    if selected_fg:
        r[FRAME_GENERATION] = "Off" if selected_fg in {"0", "Off", "false", "False"} else f"On (mode {selected_fg})"
    elif dlss_fg or fsr_fg:
        r[FRAME_GENERATION] = " / ".join(parts) if parts else "Off"

    # Quick Preset — GPUConfigPreset: -1=Custom, 0=Low, 1=Medium, 2=High, 3=Ultra
    gcp = kv.get("GPUConfigPreset")
    if gcp is not None:
        preset_map = {"-1": "Custom", "0": "Low", "1": "Medium", "2": "High", "3": "Ultra"}
        r[QUICK_PRESET] = preset_map.get(gcp, f"Preset {gcp}")

    return r


# ── Street Fighter 6 config.ini ─────────────────────────────────────

def _parse_sf6(content: str) -> Dict[str, Optional[str]]:
    r = _empty_result()
    kv = _parse_ini_kv(content)

    # SF6 stores the selected display mode as an index into DisplayModeN_*.
    display_mode = kv.get("FullScreenDisplayMode")
    if display_mode is not None:
        width = kv.get(f"DisplayMode{display_mode}_Width")
        height = kv.get(f"DisplayMode{display_mode}_Height")
        if width and height:
            r[RESOLUTION] = f"{width}x{height}"

    fullscreen = kv.get("FullScreenMode", "").lower()
    window_mode = kv.get("WindowMode", "").lower()
    if fullscreen in {"true", "1", "yes"}:
        r[SCREEN_MODE] = "Fullscreen"
    elif window_mode in {"borderless", "borderlesswindow", "borderless_window"}:
        r[SCREEN_MODE] = "Borderless Windowed"
    elif fullscreen or window_mode:
        r[SCREEN_MODE] = "Windowed"

    vsync = kv.get("VSync")
    if vsync is not None:
        r[VSYNC] = "On" if vsync.lower() in {"true", "1", "yes"} else "Off"

    max_framerate = kv.get("MaxFramerate")
    if max_framerate is not None:
        try:
            value = float(max_framerate)
            r[FRAME_LIMIT] = "Unlimited" if value <= 0 else f"{value:.0f} FPS"
        except ValueError:
            r[FRAME_LIMIT] = max_framerate

    preset = kv.get("GlobalSettings")
    if preset:
        r[QUICK_PRESET] = preset.replace("_", " ").title()

    upscale = kv.get("UpscaleType")
    if upscale is not None:
        r[UPSCALING] = "Off" if upscale.lower() in {"none", "off", "0"} else upscale
        r[UPSCALING_MODE] = "N/A"

    # This config has no explicit frame-generation switch.
    r[FRAME_GENERATION] = "N/A"
    return r


# ── Forza Horizon XML (UserConfigSelections) ─────────────────────────

def _parse_forza_xml(content: str) -> Dict[str, Optional[str]]:
    r = _empty_result()

    def _xml_val(tag: str) -> Optional[str]:
        m = re.search(rf'<{tag}\b[^>]*\bvalue="([^"]*)"', content)
        return m.group(1) if m else None

    def _sel_val(option_id: str) -> Optional[str]:
        m = re.search(rf'<option\s+id="{option_id}"\s+value="([^"]*)"', content)
        return m.group(1) if m else None

    # Resolution
    rw, rh = _xml_val("ResolutionWidth"), _xml_val("ResolutionHeight")
    if rw and rh:
        r[RESOLUTION] = f"{rw}x{rh}"

    # Screen Mode
    fs = _xml_val("Fullscreen")
    if fs is not None:
        r[SCREEN_MODE] = "Fullscreen" if fs == "1" else "Windowed"

    # VSync
    vs = _sel_val("VSync")
    pi = _xml_val("PresentInterval")
    if vs is not None:
        r[VSYNC] = "On" if vs != "0" else "Off"
    elif pi is not None:
        r[VSYNC] = "Off" if pi == "0" else "On"

    # Frame Limit
    fr = _sel_val("FrameRate")
    if fr is not None:
        fr_map = {"0": "30 FPS", "1": "40 FPS", "2": "60 FPS", "3": "120 FPS", "4": "Unlimited"}
        if re.search(r'<UserConfig\b[^>]*\bVersion="52"', content):
            fr_map = {"1": "20 FPS", "2": "30 FPS", "3": "60 FPS", "4": "Unlimited"}
        r[FRAME_LIMIT] = fr_map.get(fr, f"Preset {fr}")

    # Dynamic Resolution
    r[DYNAMIC_RESOLUTION] = "N/A"

    # Upscaling
    dlss_sel = _sel_val("DLSSMode")
    fsr3_sel = _sel_val("FSR3Mode")
    xess_sel = _sel_val("XeSSMode")
    if xess_sel and xess_sel != "0":
        xess_map = {"1": "Ultra Quality Plus", "2": "Ultra Quality", "3": "Quality", "4": "Balanced", "5": "Performance", "6": "Ultra Performance"}
        r[UPSCALING] = "XeSS"
        r[UPSCALING_MODE] = xess_map.get(xess_sel, f"Preset {xess_sel}")
    elif dlss_sel and dlss_sel != "0":
        r[UPSCALING] = "DLSS"
        r[UPSCALING_MODE] = f"Preset {dlss_sel}"
    elif fsr3_sel and fsr3_sel != "0":
        fsr_map = {"1": "Quality", "2": "Balanced", "3": "Performance", "4": "Ultra Performance"}
        r[UPSCALING] = "FSR"
        r[UPSCALING_MODE] = fsr_map.get(fsr3_sel, f"Preset {fsr3_sel}")
    else:
        r[UPSCALING] = "Off"
        r[UPSCALING_MODE] = "N/A"

    # Forza exposes frame generation through the selected upscaler (for
    # example FSR 3.1.5), not as an independent graphics setting.
    r[FRAME_GENERATION] = "N/A"

    # Forza has no single overall preset field. Infer Custom when the quality
    # selections are mixed; preserve a uniform numeric level without guessing
    # its game-specific display name.
    quality_ids = {
        "CarLOD", "EnvStreamingTex", "GeometryQuality", "ReflectionQuality",
        "SSRQuality", "ShadowQuality", "ShaderQuality", "DeformableSnowQuality",
        "ParticlesSettings", "VolumetricFogQuality", "LensEffects",
    }
    options = dict(re.findall(r'<option\s+id="([^"]+)"\s+value="([^"]*)"', content))
    quality_values = {
        options[option_id]
        for option_id in quality_ids
        if option_id in options
    }
    rt_presets = {
        "High + RT": {"CarLOD": "2", "EnvStreamingTex": "2", "GeometryQuality": "3", "SSRQuality": "0", "RTReflectionQuality": "1", "SSGIQuality": "0", "RTGIQuality": "1"},
        "Ultra + RT": {"CarLOD": "3", "EnvStreamingTex": "3", "GeometryQuality": "4", "SSRQuality": "0", "RTReflectionQuality": "2", "SSGIQuality": "0", "RTGIQuality": "2"},
        "Extreme + RT": {"CarLOD": "4", "EnvStreamingTex": "4", "GeometryQuality": "5", "SSRQuality": "0", "RTReflectionQuality": "3", "SSGIQuality": "0", "RTGIQuality": "3"},
    }
    preset_name = next((name for name, signature in rt_presets.items() if all(options.get(key) == value for key, value in signature.items())), None)
    if preset_name is None:
        preset_name = next((name for name, signature in FORZA_PRESET_SIGNATURES.items() if all(options.get(key) == value for key, value in signature.items())), None)
    if preset_name:
        r[QUICK_PRESET] = preset_name
    elif len(quality_values) > 1:
        r[QUICK_PRESET] = "Custom"
    elif len(quality_values) == 1:
        r[QUICK_PRESET] = f"Preset Level {next(iter(quality_values))}"
    else:
        r[QUICK_PRESET] = "N/A"

    return r


# ── F1 25 hardware_settings_config.xml ─────────────────────────────

def _parse_f1_xml(content: str) -> Dict[str, Optional[str]]:
    r = _empty_result()
    try:
        root = ET.fromstring(content)
    except (ET.ParseError, ValueError):
        return r

    def find_node(name: str) -> Optional[ET.Element]:
        return next((node for node in root.iter(name)), None)

    resolution = find_node("resolution")
    if resolution is not None:
        width = resolution.get("width")
        height = resolution.get("height")
        if width and height:
            r[RESOLUTION] = f"{width}x{height}"

        display_mode = resolution.get("displayMode")
        display_modes = {
            "0": "Windowed",
            "1": "Fullscreen",
            "2": "Borderless Windowed",
        }
        if display_mode in display_modes:
            r[SCREEN_MODE] = display_modes[display_mode]

        vsync = resolution.get("vsync")
        if vsync is not None:
            r[VSYNC] = "On" if vsync.lower() in {"true", "1", "yes"} else "Off"

        limiter_enabled = resolution.get("frameRateLimiterEnabled")
        limiter_value = resolution.get("frameRateLimiterValue")
        if limiter_enabled is not None and limiter_enabled.lower() in {"false", "0", "no"}:
            r[FRAME_LIMIT] = "Unlimited"
        elif limiter_value:
            r[FRAME_LIMIT] = f"{limiter_value} FPS"

    anti_aliasing = find_node("antialiasing")
    if anti_aliasing is not None:
        dlss = anti_aliasing.get("dlss", "false").lower() in {"true", "1", "yes"}
        fsr3 = anti_aliasing.get("fsr3", "0")
        xess = anti_aliasing.get("xess", "false").lower() in {"true", "1", "yes"}
        aa_quality = find_node("aa_quality")
        quality_value = aa_quality.get("value", "") if aa_quality is not None else ""
        quality_names = {
            "0": "Quality",
            "1": "Balanced",
            "2": "Performance",
            "4": "Ultra Quality",
        }
        fsr_quality_names = {
            "0": "Quality",
            "1": "Balanced",
            "2": "Performance",
            "3": "Ultra Performance",
        }
        if dlss:
            r[UPSCALING] = "DLSS"
            r[UPSCALING_MODE] = quality_names.get(str(quality_value), f"Mode {quality_value}")
        elif fsr3 not in {"0", "", "false", "off"}:
            quality = fsr_quality_names.get(str(quality_value))
            r[UPSCALING] = "FSR"
            r[UPSCALING_MODE] = quality or f"Mode {quality_value}"
        elif xess:
            quality = quality_names.get(str(quality_value))
            r[UPSCALING] = "XeSS"
            r[UPSCALING_MODE] = quality or f"Mode {quality_value}"
        else:
            r[UPSCALING] = "Off"
            r[UPSCALING_MODE] = "N/A"

    frame_gen = find_node("frame_gen")
    multi_frame_gen = find_node("multi_frame_gen")
    frame_gen_value = frame_gen.get("mode", "0") if frame_gen is not None else "0"
    multi_frame_value = multi_frame_gen.get("value", "0") if multi_frame_gen is not None else "0"
    frame_generation_names = {"3": "AMD FSR3", "4": "XeFG"}
    if frame_gen_value in {"0", "", "off"} and multi_frame_value in {"0", "", "off"}:
        r[FRAME_GENERATION] = "Off"
    else:
        r[FRAME_GENERATION] = frame_generation_names.get(frame_gen_value, "N/A")

    dynamic = find_node("dynamicresolution_enabled")
    if dynamic is not None:
        enabled = dynamic.get("value", "false").lower() in {"true", "1", "yes"}
        target = find_node("dynamicresolution_target_fps")
        target_value = target.get("value", "") if target is not None else ""
        if enabled and target_value:
            target_label = (
                "AUTO"
                if str(target_value).upper() in {"0", "AUTO"}
                else f"{target_value} FPS"
            )
            r[DYNAMIC_RESOLUTION] = f"On (Target: {target_label})"
        else:
            r[DYNAMIC_RESOLUTION] = "On" if enabled else "Off"

    # F1 25 presets are component signatures; match proven signatures before
    # treating mixed component levels as Custom.
    quality_values = []
    quality_options: Dict[str, str] = {}
    for node_name, attribute in (
        ("lighting", "quality"),
        ("ssrt", "quality"),
        ("shadows", "sampling"),
        ("weather_effects", "proceduralCloudQuality"),
        ("texture_streaming", "sizeInMiB"),
        ("particles", "enabled"),
        ("particles", "distanceScale"),
        ("particles", "high"),
        ("shadows", "skyShadowMapSize"),
        ("vehicle_reflections", "envMapScale"),
        ("ground_cover", "enabled"),
        ("rt_pathtrace", "enabled"),
    ):
        node = find_node(node_name)
        if node is not None and node.get(attribute) is not None:
            value = node.get(attribute)
            if value.lower() in {"true", "false"}:
                value = value.lower()
            quality_values.append(value)
            quality_options[f"{node_name}.{attribute}"] = value
    frame_generation_active = not (
        frame_gen_value in {"0", "", "off"}
        and multi_frame_value in {"0", "", "off"}
    )
    preset_name = next(
        (
            name for name, signature in F1_PRESET_SIGNATURES.items()
            if all(quality_options.get(key) == value for key, value in signature.items())
        ),
        None,
    )
    if preset_name and frame_generation_active:
        r[QUICK_PRESET] = f"Custom ({preset_name})"
    elif preset_name:
        r[QUICK_PRESET] = preset_name
    elif len(set(quality_values)) > 1:
        r[QUICK_PRESET] = "Custom"
    elif quality_values:
        r[QUICK_PRESET] = f"Preset Level {quality_values[0]}"
    else:
        r[QUICK_PRESET] = "N/A"
    return r


# ── Registry JSON (HZD, Shadow of TR) ───────────────────────────────

def _parse_registry_json(content: str, game_hint: str = "") -> Dict[str, Optional[str]]:
    r = _empty_result()
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return r

    gfx = data.get("Graphics", data)

    # Resolution
    fw = gfx.get("FullscreenWidth", gfx.get("WindowWidth"))
    fh = gfx.get("FullscreenHeight", gfx.get("WindowHeight"))
    if fw is not None and fh is not None:
        r[RESOLUTION] = f"{fw}x{fh}"

    # Screen Mode
    fs = gfx.get("Fullscreen")
    efs = gfx.get("ExclusiveFullscreen")
    if fs is not None:
        if fs == 1:
            r[SCREEN_MODE] = "Exclusive Fullscreen" if efs == 1 else "Borderless Fullscreen"
        else:
            r[SCREEN_MODE] = "Windowed"

    # VSync
    vs = gfx.get("VSync")
    if vs is not None:
        r[VSYNC] = "On" if vs != 0 else "Off"

    # Frame Limit
    drt = gfx.get("DynamicResolutionTargetFPS")
    fhr = gfx.get("ForceHalfRefreshRate")
    if drt is not None:
        r[FRAME_LIMIT] = f"{drt} FPS" if drt > 0 else "Unlimited"
    elif fhr is not None:
        r[FRAME_LIMIT] = "Half Refresh Rate" if fhr else "Unlimited"

    # Dynamic Resolution
    if drt is not None:
        r[DYNAMIC_RESOLUTION] = f"On (Target: {drt} FPS)" if drt > 0 else "Off"
    else:
        rm = gfx.get("ResolutionModifier")
        if rm is not None:
            pct = rm / 10 if rm > 100 else rm
            r[DYNAMIC_RESOLUTION] = f"{pct:.0f}%" if pct != 100 else "Off (100%)"

    # Upscaling
    um = gfx.get("UpscaleMethod")
    uq = gfx.get("UpscaleQuality")
    dlss = gfx.get("DLSS")
    xess = gfx.get("XESS")
    cas = gfx.get("CAS")
    if um is not None:
        method_map = {0: "Off", 1: "DLSS", 2: "FSR", 3: "CAS", 4: "XeSS"}
        quality_map = {0: "Ultra Performance", 1: "Performance", 2: "Balanced", 3: "Quality", 4: "Ultra Quality"}
        m = method_map.get(um, f"Method {um}")
        q = quality_map.get(uq, "") if uq is not None else ""
        r[UPSCALING] = m
        r[UPSCALING_MODE] = q if m != "Off" and q else "N/A"
    elif dlss is not None or xess is not None:
        if xess and xess != 0:
            r[UPSCALING] = "XeSS"
        elif dlss and dlss != 0:
            r[UPSCALING] = "DLSS"
        elif cas and cas != 0:
            r[UPSCALING] = "CAS"
        else:
            r[UPSCALING] = "Off"
        r[UPSCALING_MODE] = "N/A"

    # Frame Generation
    fg = gfx.get("FrameGen")
    dlssg = gfx.get("DLSSG")
    parts = []
    if fg and fg != 0:
        parts.append("Frame Gen: On")
    if dlssg and dlssg != 0:
        parts.append("DLSS-G: On")
    if fg is None and dlssg is None:
        r[FRAME_GENERATION] = "N/A"
    else:
        r[FRAME_GENERATION] = ", ".join(parts) if parts else "Off"

    # Quick Preset — registry-based games have no known preset field
    r[QUICK_PRESET] = "N/A"

    return r


# ── CS2 (cs2_video.txt + convars) ───────────────────────────────────

def _parse_cs2(all_configs: List[Dict[str, Any]]) -> Dict[str, Optional[str]]:
    """Parse CS2 settings from multiple config file entries."""
    r = _empty_result()

    video_kv: Dict[str, str] = {}
    convar_kv: Dict[str, str] = {}

    for cfg in all_configs:
        content = cfg.get("content") or ""
        path = cfg.get("expanded_path", "")
        if "cs2_video" in path.lower():
            video_kv = {}
            for line in content.splitlines():
                line = line.strip()
                m = re.match(r'"([^"]+)"\s+"([^"]*)"', line)
                if m:
                    video_kv[m.group(1)] = m.group(2)
        elif "machine_convars" in path.lower() or "user_convars" in path.lower():
            for line in content.splitlines():
                line = line.strip()
                m = re.match(r'"([^"]+)"\s+"([^"]*)"', line)
                if m:
                    convar_kv[m.group(1)] = m.group(2)

    # Resolution
    w = video_kv.get("setting.defaultres")
    h = video_kv.get("setting.defaultresheight")
    if w and h:
        r[RESOLUTION] = f"{w}x{h}"

    # Screen Mode
    fs = video_kv.get("setting.fullscreen", "0")
    nwb = video_kv.get("setting.nowindowborder", "0")
    if fs == "1":
        r[SCREEN_MODE] = "Fullscreen"
    elif nwb == "1":
        r[SCREEN_MODE] = "Borderless Windowed"
    else:
        r[SCREEN_MODE] = "Windowed"

    # VSync
    vs = video_kv.get("setting.mat_vsync")
    if vs is not None:
        r[VSYNC] = "On" if vs != "0" else "Off"

    # Frame Limit
    fps = convar_kv.get("fps_max")
    if fps:
        try:
            val = float(fps)
            r[FRAME_LIMIT] = "Unlimited" if val <= 0 else f"{val:.0f} FPS"
        except ValueError:
            r[FRAME_LIMIT] = fps

    # Upscaling
    fsr = video_kv.get("setting.videocfg_fsr_detail")
    if fsr is not None:
        fsr_map = {"0": "Off", "1": "Ultra Quality", "2": "Quality", "3": "Balanced", "4": "Performance"}
        r[UPSCALING] = "FSR" if fsr != "0" else "Off"
        r[UPSCALING_MODE] = fsr_map.get(fsr, f"Mode {fsr}") if fsr != "0" else "N/A"

    # CS2 has no Dynamic Resolution, Frame Generation, or Quick Preset
    r[DYNAMIC_RESOLUTION] = "N/A"
    r[FRAME_GENERATION] = "N/A"
    r[QUICK_PRESET] = "N/A"

    return r


# ── Main dispatcher ─────────────────────────────────────────────────

def extract_key_settings(
    game_name: str,
    config_files: List[Dict[str, Any]],
) -> Dict[str, Optional[str]]:
    """Extract the 9 key graphics settings from a game's config files.

    Parameters
    ----------
    game_name:
        The name of the game (used to select the appropriate parser).
    config_files:
        The ``config_files`` list from the export JSON, where each entry
        has ``expanded_path``, ``content``, ``found``, ``error``, etc.

    Returns
    -------
    dict
        A dict mapping each of the 8 setting keys to a human-readable
        value string, or ``None`` if not found.
    """
    readable = [c for c in config_files if c.get("content") and c.get("found")]
    if not readable:
        return _empty_result()

    def _content_for(*names: str) -> str:
        """Return the content of the candidate matching one of *names*.

        Directory scans (e.g. Unreal Engine's ``Saved\\Config\\Windows\\``)
        can return dozens of near-empty config files; picking ``readable[0]``
        blindly would parse the wrong one. Fall back to it only when none of
        the expected filenames are present.
        """
        wanted = {name.lower() for name in names}
        for cfg in readable:
            if os.path.basename(str(cfg.get("expanded_path", ""))).lower() in wanted:
                return cfg["content"]
        return readable[0]["content"]

    name_lower = game_name.lower()

    if "cyberpunk" in name_lower:
        return _parse_cyberpunk(_content_for("UserSettings.json"))

    if "black myth" in name_lower or "wukong" in name_lower:
        return _parse_black_myth(
            _content_for("GameUserSettings.ini"),
            benchmark="benchmark" in name_lower,
        )

    if "clair obscur" in name_lower or "expedition 33" in name_lower:
        return _parse_expedition_33(_content_for("GameUserSettings.ini"))

    if "street fighter" in name_lower or "streetfighter" in name_lower:
        return _parse_sf6(_content_for("config.ini"))

    if "counter-strike" in name_lower or "cs2" in name_lower:
        return _parse_cs2(readable)

    if "forza" in name_lower:
        return _parse_forza_xml(_content_for("UserConfigSelections"))

    if "f1" in name_lower and "25" in name_lower:
        return _parse_f1_xml(_content_for("hardware_settings_config.xml"))

    for cfg in readable:
        if cfg.get("type") == "registry":
            return _parse_registry_json(cfg["content"], game_hint=name_lower)

    for cfg in readable:
        content = cfg["content"]
        if "ResolutionSizeX" in content or "FullscreenMode" in content:
            return _parse_unreal_ini(content)

    # Generic fallback: try all parsers and return the one with most results
    best = _empty_result()
    best_count = 0
    for parser in [_parse_unreal_ini, _parse_forza_xml]:
        for cfg in readable:
            try:
                result = parser(cfg["content"])
                count = sum(1 for v in result.values() if v is not None)
                if count > best_count:
                    best = result
                    best_count = count
            except Exception:
                pass
    return best
