"""
render_worker.py

Downloads generated frames + audio from GCS, composes a synced vertical
1080x1920 MP4 with animated captions using MoviePy (FFmpeg backend),
uploads the final render back to GCS.

Runs ONLY inside the pipeline Cloud Run Job container (has ffmpeg + moviepy
installed) — never inside the UI service.
"""

import PIL.Image
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

import os
import tempfile
import numpy as np
from google.cloud import storage
from moviepy.editor import (
    ImageClip,
    AudioFileClip,
    CompositeVideoClip,
    TextClip,
    ColorClip,
    concatenate_videoclips,
)

from google.auth import default

try:
    _, PROJECT_ID = default()
except Exception:
    PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "friday-media-os")

BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", f"friday-media-assets-{PROJECT_ID}")
VIDEO_SIZE = (1080, 1920)


def _download_blob(storage_client: storage.Client, gs_uri: str, local_path: str) -> None:
    bucket_name, blob_path = gs_uri.replace("gs://", "").split("/", 1)
    bucket = storage_client.bucket(bucket_name)
    bucket.blob(blob_path).download_to_filename(local_path)


def format_srt_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis == 1000:
        millis = 0
        secs += 1
        if secs == 60:
            secs = 0
            minutes += 1
            if minutes == 60:
                minutes = 0
                hours += 1
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def render_video(
    script: dict,
    audio_uri: str,
    image_uris: list[str],
    brand_id: str,
    content_id: str,
    brand: dict = None,
) -> str:
    storage_client = storage.Client()

    if brand is None:
        from src.config.firestore_schema import get_db, get_brand
        db = get_db()
        brand = get_brand(db, brand_id)

    with tempfile.TemporaryDirectory() as tmp:
        audio_path = os.path.join(tmp, "audio.mp3")
        _download_blob(storage_client, audio_uri, audio_path)
        audio_clip = AudioFileClip(audio_path)
        total_duration = audio_clip.duration

        # Download all frames
        frame_paths = []
        for i, uri in enumerate(image_uris):
            frame_path = os.path.join(tmp, f"frame_{i}.png")
            _download_blob(storage_client, uri, frame_path)
            frame_paths.append(frame_path)

        # Split total duration evenly across frames if no explicit timestamps
        n = max(len(frame_paths), 1)
        segment_duration = total_duration / n

        clips = []
        for i, frame_path in enumerate(frame_paths):
            img_clip = (
                ImageClip(frame_path)
                .set_duration(segment_duration)
                .resize(height=VIDEO_SIZE[1])
            )
            # Center-crop to exact 1080x1920 if aspect doesn't match exactly
            img_clip = img_clip.crop(
                x_center=img_clip.w / 2, width=VIDEO_SIZE[0]
            )
            if i > 0:
                img_clip = img_clip.crossfadein(0.4)
            clips.append(img_clip)

        video = concatenate_videoclips(clips, method="compose", padding=-0.4)

        # Caption overlay — split narration using numpy.array_split to prevent truncation
        narration = script.get("narration", "")
        words = narration.split()
        word_chunks = np.array_split(words, n)
        reconstructed_chunks = []
        caption_clips = []

        for i in range(n):
            chunk_words = list(word_chunks[i])
            if not chunk_words:
                continue
            chunk = " ".join(chunk_words)
            reconstructed_chunks.append(chunk)

            txt_clip = TextClip(
                chunk,
                fontsize=64,
                color="white",
                font="DejaVu-Sans-Bold",
                method="caption",
                size=(VIDEO_SIZE[0] - 100, None),
                stroke_color="black",
                stroke_width=2,
            )

            # Dark semi-transparent background plate behind caption for legibility
            txt_w, txt_h = txt_clip.w, txt_clip.h
            bg_clip = (
                ColorClip(size=(txt_w + 40, txt_h + 20), color=(0, 0, 0))
                .set_opacity(0.55)
            )

            caption_box = (
                CompositeVideoClip(
                    [bg_clip, txt_clip.set_position("center")],
                    size=(txt_w + 40, txt_h + 20),
                )
                .set_start(i * segment_duration)
                .set_duration(segment_duration)
                .set_position(("center", VIDEO_SIZE[1] - txt_h - 140))
            )
            caption_clips.append(caption_box)

        # Verification assertion: concatenating caption chunks must match original narration
        reconstructed_narration = " ".join(reconstructed_chunks)
        assert reconstructed_narration == " ".join(words), (
            f"Caption truncation detected! Original: ' {' '.join(words)} ', "
            f"Reconstructed: ' {reconstructed_narration} '"
        )

        main_video = CompositeVideoClip([video, *caption_clips], size=VIDEO_SIZE)
        main_video = main_video.set_audio(audio_clip)
        main_video = main_video.set_duration(total_duration)

        from src.workers.outro_worker import generate_outro
        
        outro_duration = 8  # 8-second branded outro
        outro_clip = generate_outro(brand, duration=outro_duration, video_size=VIDEO_SIZE).fadein(1.0)

        final = concatenate_videoclips([main_video, outro_clip], method="compose")

        output_path = os.path.join(tmp, f"{content_id}.mp4")
        final.write_videofile(
            output_path,
            fps=30,
            codec="libx264",
            audio_codec="aac",
            preset="medium",
            threads=2,
            ffmpeg_params=[
                "-pix_fmt", "yuv420p",      # YouTube-required pixel format
                "-movflags", "+faststart",   # Move moov atom to start for streaming
                "-b:a", "128k",              # Explicit AAC bitrate (stereo 44.1kHz)
            ],
        )

        bucket = storage_client.bucket(BUCKET_NAME)
        blob_path = f"{brand_id}/final_renders/{content_id}.mp4"
        bucket.blob(blob_path).upload_from_filename(output_path)

        # Generate and upload SRT captions
        srt_lines = []
        for i in range(len(reconstructed_chunks)):
            chunk = reconstructed_chunks[i]
            start_t = i * segment_duration
            end_t = (i + 1) * segment_duration
            srt_lines.append(f"{i+1}")
            srt_lines.append(f"{format_srt_time(start_t)} --> {format_srt_time(end_t)}")
            srt_lines.append(chunk)
            srt_lines.append("")
        srt_content = "\n".join(srt_lines)

        srt_path = os.path.join(tmp, f"{content_id}.srt")
        with open(srt_path, "w", encoding="utf-8") as srt_file:
            srt_file.write(srt_content)

        srt_blob_path = f"{brand_id}/captions/{content_id}.srt"
        bucket.blob(srt_blob_path).upload_from_filename(srt_path, content_type="text/plain")
        srt_uri = f"gs://{BUCKET_NAME}/{srt_blob_path}"

        return f"gs://{BUCKET_NAME}/{blob_path}", srt_uri
