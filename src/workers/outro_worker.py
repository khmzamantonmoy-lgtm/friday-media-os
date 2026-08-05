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
    Builds a highly premium vertical outro composition.
    Staggered timings are applied to give a smooth entrance to each element.
    """
    # 1. Parse brand identity parameters
    bg_color = hex_to_rgb(brand.get("hex_primary", "#0B0F19"))
    accent_color_hex = brand.get("hex_accent", "#6366F1")
    accent_color = hex_to_rgb(accent_color_hex)
    display_name = brand.get("display_name", "FRIDAY Media")
    platforms = brand.get("target_platforms", ["youtube"])

    # 2. Base Background Clip
    bg_clip = ColorClip(size=video_size, color=bg_color).set_duration(duration)

    # Subtle premium background geometric accents (e.g., top/bottom glowing borders)
    top_glow = ColorClip(size=(video_size[0], 12), color=accent_color).set_duration(duration).set_opacity(0.8).set_position(("center", "top"))
    bottom_glow = ColorClip(size=(video_size[0], 12), color=accent_color).set_duration(duration).set_opacity(0.8).set_position(("center", "bottom"))

    # 3. Dynamic Initials / Logo Generator
    # Extract the initials of the brand (e.g., "WealthWise Daily" -> "WD")
    words = display_name.split()
    initials = "".join([w[0].upper() for w in words[:2]])
    if not initials:
        initials = "FM"

    # Logo outer border
    logo_border = ColorClip(size=(176, 176), color=(255, 255, 255)).set_duration(duration).set_opacity(0.15)
    # Logo background fill (accent color)
    logo_fill = ColorClip(size=(160, 160), color=accent_color).set_duration(duration)
    # Initials text overlay
    logo_text = TextClip(
        initials,
        fontsize=75,
        color="white",
        font="DejaVu-Sans-Bold",
        method="label"
    ).set_duration(duration)

    # Composite logo icon
    logo_icon = CompositeVideoClip(
        [logo_border, logo_fill.set_position("center"), logo_text.set_position("center")],
        size=(176, 176)
    ).set_position(("center", 350)).set_start(0.2).fadein(0.4)

    # 4. Brand Name Header
    title_clip = TextClip(
        display_name,
        fontsize=64,
        color="white",
        font="DejaVu-Sans-Bold",
        method="label",
    ).set_position(("center", 580)).set_start(0.5).fadein(0.4).set_duration(duration - 0.5)

    # Subtle accent underline below the brand name
    underline = ColorClip(size=(140, 4), color=accent_color).set_duration(duration - 0.7).set_position(("center", 670)).set_start(0.7).fadein(0.3)

    # 5. Core Value Proposition / Subtitle
    angle_text = brand.get("content_angle", "")
    if len(angle_text) > 80:
        angle_text = angle_text[:77] + "..."
    
    sub_title = TextClip(
        angle_text,
        fontsize=34,
        color="#94A3B8", # Slate gray
        font="DejaVu-Sans",
        method="caption",
        size=(video_size[0] - 160, None),
    ).set_position(("center", 710)).set_start(0.9).fadein(0.4).set_duration(duration - 0.9)

    # 6. Interactive Platform Action Buttons (CTAs)
    # If the brand targets YouTube, render a "SUBSCRIBE" button. If TikTok/Instagram, show "FOLLOW"
    cta_clips = []
    y_offset = 1000
    
    for idx, platform in enumerate(platforms[:2]):
        action_text = "SUBSCRIBE" if platform.lower() == "youtube" else "FOLLOW"
        cta_label = f"{action_text} FOR MORE"
        
        # Styled CTA Button
        btn_border = ColorClip(size=(606, 96), color=(255, 255, 255)).set_opacity(0.1)
        btn_bg = ColorClip(size=(600, 90), color=accent_color)
        btn_text = TextClip(
            cta_label,
            fontsize=36,
            color="white",
            font="DejaVu-Sans-Bold",
            method="label"
        )
        
        btn_clip = CompositeVideoClip(
            [btn_border, btn_bg.set_position("center"), btn_text.set_position("center")],
            size=(606, 96)
        ).set_position(("center", y_offset)).set_start(1.2 + idx * 0.3).fadein(0.4).set_duration(duration - (1.2 + idx * 0.3))
        
        cta_clips.append(btn_clip)
        y_offset += 140

    # 7. Curiosity Hook / Footer
    footer_clip = TextClip(
        "New videos every day",
        fontsize=36,
        color="#64748B", # Muted slate gray
        font="DejaVu-Sans",
        method="label",
    ).set_position(("center", 1600)).set_start(1.8).fadein(0.4).set_duration(duration - 1.8)

    # 8. Composite Outro elements
    outro = CompositeVideoClip(
        [
            bg_clip,
            top_glow,
            bottom_glow,
            logo_icon,
            title_clip,
            underline,
            sub_title,
            *cta_clips,
            footer_clip
        ],
        size=video_size
    )

    return outro
