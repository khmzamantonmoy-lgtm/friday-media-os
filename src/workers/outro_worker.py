"""
outro_worker.py

Generates a premium, production-ready vertical (9:16) outro clip for FRIDAY Media OS.
Includes staggered animations, brand color matching, logo/initials generation,
mobile-safe boundaries, and platform-specific CTA buttons.
"""

from moviepy.editor import ColorClip, TextClip, CompositeVideoClip, ImageClip
import os
from google.cloud import storage

def hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    """Converts a hex color string (e.g., #0B0F19) to an RGB tuple."""
    hex_str = hex_str.lstrip('#')
    if len(hex_str) == 3:
        hex_str = ''.join([c*2 for c in hex_str])
    try:
        return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))
    except Exception:
        # Fallback to dark navy color if hex is invalid
        return (11, 15, 25)


def generate_outro(brand: dict, duration: int = 8, video_size: tuple[int, int] = (1080, 1920)) -> CompositeVideoClip:
    """
    Builds a highly premium vertical outro composition with a generic CTA.
    """
    # 1. Parse brand identity parameters
    bg_color = hex_to_rgb(brand.get("hex_primary", "#0B0F19"))
    accent_color_hex = brand.get("hex_accent", "#6366F1")
    accent_color = hex_to_rgb(accent_color_hex)
    platforms = brand.get("target_platforms", ["youtube"])

    # 2. Base Background Clip
    bg_clip = ColorClip(size=video_size, color=bg_color).set_duration(duration)

    # Subtle premium background geometric accents (e.g., top/bottom glowing borders)
    top_glow = ColorClip(size=(video_size[0], 12), color=accent_color).set_duration(duration).set_opacity(0.8).set_position(("center", "top"))
    bottom_glow = ColorClip(size=(video_size[0], 12), color=accent_color).set_duration(duration).set_opacity(0.8).set_position(("center", "bottom"))

    # 3. Interactive Platform Action Button (Single Generic CTA)
    has_youtube = any(p.lower() == "youtube" for p in platforms)
    action_text = "subscribe" if has_youtube else "follow"
    cta_label = f"Like this video, share it, and {action_text} for more."

    # Styled CTA Button centered vertically
    btn_border = ColorClip(size=(756, 136), color=(255, 255, 255)).set_opacity(0.1)
    btn_bg = ColorClip(size=(750, 130), color=accent_color)
    btn_text = TextClip(
        cta_label,
        fontsize=28,
        color="white",
        font="DejaVu-Sans-Bold",
        method="caption",
        size=(700, None)
    )

    btn_clip = CompositeVideoClip(
        [btn_border, btn_bg.set_position("center"), btn_text.set_position("center")],
        size=(756, 136)
    ).set_position(("center", 892)).set_start(0.4).fadein(0.4).set_duration(duration - 0.4)

    # 4. Composite Outro elements
    outro = CompositeVideoClip(
        [
            bg_clip,
            top_glow,
            bottom_glow,
            btn_clip
        ],
        size=video_size
    )

    return outro
