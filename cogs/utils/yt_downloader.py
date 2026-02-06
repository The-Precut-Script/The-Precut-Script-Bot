# -*- coding: utf-8 -*-
import os
from pathlib import Path
from typing import Optional, List

import discord
from yt_dlp import YoutubeDL


def _get_ffmpeg_dir() -> Optional[str]:
    import shutil
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    return os.path.dirname(ffmpeg)


def extract_video_id_from_url(url: str) -> str:
    import re
    if "&list=" in url or "&start_radio=" in url:
        m = re.search(
            r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([a-zA-Z0-9_-]+)",
            url,
        )
        if m:
            return f"https://www.youtube.com/watch?v={m.group(1)}"
    return url


MAX_DURATION_SECONDS = 1800


def download_video_webm(
    url: str,
    output_dir: Path,
    max_height: int = 1080,
    ffmpeg_dir: Optional[str] = None,
) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    ydl_opts = {
        "format": f"bestvideo[height<={max_height}][ext=webm]+bestaudio[ext=webm]/best[ext=webm]/best",
        "merge_output_format": "webm",
        "postprocessor_args": ["-c:v", "copy", "-c:a", "copy"],
        "outtmpl": str(output_dir / f"{max_height}p_%(title)s.%(ext)s"),
        "restrictfilenames": True,
        "quiet": True,
        "noplaylist": True,
        "no_warnings": True,
    }
    if ffmpeg_dir:
        ydl_opts["ffmpeg_location"] = ffmpeg_dir

    with YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=False)
        if not info_dict:
            raise RuntimeError("Could not extract video info")
        if info_dict.get("duration") and info_dict["duration"] > MAX_DURATION_SECONDS:
            raise RuntimeError("Video exceeds 30 minutes. Please try a shorter video.")
        ydl.download([url])
        video_file = ydl.prepare_filename(info_dict)

    path = Path(video_file).resolve()
    if not path.exists():
        webms = list(output_dir.glob("*.webm"))
        if not webms:
            raise RuntimeError("Download finished but no WebM found.")
        path = max(webms, key=lambda p: p.stat().st_mtime)
    return path


def download_audio_mp3(
    url: str,
    output_dir: Path,
    bitrate_kbps: str = "320",
    ffmpeg_dir: Optional[str] = None,
) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    clean_url = extract_video_id_from_url(url)
    ffmpeg_dir = ffmpeg_dir or _get_ffmpeg_dir()

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(output_dir / "%(title)s.%(ext)s"),
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": bitrate_kbps}
        ],
        "socket_timeout": 20,
        "retries": 2,
        "fragment_retries": 2,
        "file_access_retries": 2,
        "extractor_retries": 2,
        "http_chunk_size": 20971520,
        "buffersize": 16384,
        "concurrent_fragment_downloads": 16,
        "max_sleep_interval": 0.5,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [],
        "noplaylist": True,
        "restrictfilenames": True,
    }
    if ffmpeg_dir:
        ydl_opts["ffmpeg_location"] = ffmpeg_dir

    with YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(clean_url, download=False)
        if not info_dict:
            raise RuntimeError("Could not extract audio info")
        if info_dict.get("duration", 0) > MAX_DURATION_SECONDS:
            raise RuntimeError("Audio is too long (max 30 minutes). Please try a shorter video.")
        ydl.download([clean_url])
        download_path = str(Path(ydl.prepare_filename(info_dict)).with_suffix(".mp3"))

    path = Path(download_path).resolve()
    if not path.exists():
        mp3s = list(output_dir.glob("*.mp3"))
        if not mp3s:
            raise RuntimeError("Download finished but no MP3 found.")
        path = max(mp3s, key=lambda p: p.stat().st_mtime)
    if path.stat().st_size == 0:
        raise RuntimeError("Downloaded file is empty")
    return path


def build_yt_download_layout(
    output_path: str,
    footer_text: Optional[str] = None,
    requested_by: Optional[str] = None,
    kind: str = "video",
    info_text: Optional[str] = None,
) -> tuple[Optional[discord.ui.LayoutView], List[discord.File]]:
    filename = os.path.basename(output_path) or ("video.webm" if kind == "video" else "audio.mp3")
    files = [discord.File(output_path, filename=filename)]

    if kind == "audio":
        return None, files

    LayoutView = getattr(discord.ui, "LayoutView", None)
    Container = getattr(discord.ui, "Container", None)
    TextDisplay = getattr(discord.ui, "TextDisplay", None)
    Separator = getattr(discord.ui, "Separator", None)
    MediaGallery = getattr(discord.ui, "MediaGallery", None)
    MediaGalleryItem = getattr(discord, "MediaGalleryItem", None) or getattr(discord.ui, "MediaGalleryItem", None)
    if not all((LayoutView, Container, TextDisplay, Separator, MediaGallery, MediaGalleryItem)):
        return None, files

    try:
        sep = Separator(spacing=discord.SeparatorSpacing.small)
    except Exception:
        sep = Separator()

    kind_label = "video" if kind == "video" else "audio"
    if requested_by:
        title_text = f"**Requested by** {requested_by}\n-# Click below to play or download the {kind_label}."
    else:
        title_text = f"**{kind_label.capitalize()} downloaded.**\n-# Click below to play or download the {kind_label}."
    if info_text:
        title_text += "\n\n" + info_text

    children = [
        TextDisplay(title_text),
        sep,
        MediaGallery(MediaGalleryItem(files[0])),
    ]
    if footer_text:
        children.append(TextDisplay(f"-# {footer_text}"))

    class YTLayout(LayoutView):
        def __init__(self):
            super().__init__(timeout=None)
            container = Container(*children)
            self.add_item(container)

    return YTLayout(), files


def download_video_mp4(url: str, output_dir: Path, max_height: int = 1080) -> Path:
    return download_video_webm(url, output_dir, max_height=max_height, ffmpeg_dir=_get_ffmpeg_dir())
