import asyncio
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional, Tuple, List

import discord
from discord import app_commands
from discord.ext import commands

def _get_dedup_python_dir() -> Optional[Path]:
    env_path = os.environ.get("DEDUP_PYTHON_PATH", "").strip()
    if env_path:
        p = Path(env_path).resolve()
        if p.is_dir():
            return p
    repo_root = Path(__file__).resolve().parents[4]
    python_dir = repo_root / "python"
    return python_dir if python_dir.is_dir() else None

_PYTHON_DIR = _get_dedup_python_dir()
if _PYTHON_DIR is not None and str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))


def _run_dedup_sync(input_path: str, output_path: str) -> dict:
    from remove_duplicate_frames import remove_duplicate_frames
    return remove_duplicate_frames(
        input_path, output_path,
        similarity_threshold=0.95,
        use_optical_flow=True,
        region_sensitivity=1,
        camera_motion_compensation=True,
        remove_static_subject_frames=True,
    )


async def process_dedup(
    attachment: discord.Attachment,
    max_size_mb: int,
    max_output_mb: Optional[int] = None,
) -> Tuple[Optional[str], Optional[str], Optional[dict]]:
    max_out = max_output_mb if max_output_mb is not None else max_size_mb
    if _PYTHON_DIR is None:
        return None, (
            "**Dedup is unavailable:** Set **DEDUP_PYTHON_PATH** in `.env` to the folder containing `remove_duplicate_frames.py`."
        ), None
    if attachment.size > max_size_mb * 1024 * 1024:
        return None, f"Video must be under **{max_size_mb} MB**. Your file: {attachment.size / (1024*1024):.1f} MB.", None
    ct = (attachment.content_type or "").lower()
    if ct and "video" not in ct and "octet" not in ct:
        ext = (attachment.filename or "").split(".")[-1].lower()
        if ext not in ("mp4", "mov", "avi", "mkv", "webm"):
            return None, "Please upload a **video** file (e.g. MP4, MOV).", None
    try:
        data = await attachment.read()
    except Exception as e:
        return None, f"Failed to download file: {e}", None
    tmp = tempfile.mkdtemp(prefix="ae_bot_dedup_")
    input_path = os.path.join(tmp, "input_" + (attachment.filename or "video.mp4"))
    output_path = os.path.join(tmp, "output_dedup.mp4")
    try:
        with open(input_path, "wb") as f:
            f.write(data)
    except Exception as e:
        _cleanup_tmp(tmp)
        return None, f"Failed to save file: {e}", None
    try:
        stats = await asyncio.to_thread(_run_dedup_sync, input_path, output_path)
    except ImportError as e:
        _cleanup_tmp(tmp)
        err_msg = str(e).strip()
        if "cv2" in err_msg or "opencv" in err_msg:
            return None, "**Dedup is unavailable:** Install `opencv-python-headless` and `numpy` in the bot environment.", None
        return None, f"**Dedup is unavailable:** {err_msg} Set **DEDUP_PYTHON_PATH** if the script folder is elsewhere.", None
    except FileNotFoundError:
        _cleanup_tmp(tmp)
        return None, "FFmpeg or script not found. Install repo deps and FFmpeg.", None
    except Exception as e:
        _cleanup_tmp(tmp)
        return None, f"Duplicate removal failed: {e}", None
    if not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
        _cleanup_tmp(tmp)
        return None, "Processing produced no output.", None
    if os.path.getsize(output_path) > max_out * 1024 * 1024:
        _cleanup_tmp(tmp)
        return None, f"Output over {max_out} MB. Use a shorter/smaller input.", None
    return output_path, None, stats


async def process_dedup_from_path(
    input_path: str,
    max_size_mb: int,
    max_output_mb: Optional[int] = None,
) -> Tuple[Optional[str], Optional[str], Optional[dict]]:
    max_out = max_output_mb if max_output_mb is not None else max_size_mb
    if _PYTHON_DIR is None:
        return None, "**Dedup is unavailable:** Set **DEDUP_PYTHON_PATH** in `.env`.", None
    if not os.path.isfile(input_path):
        return None, "Video file not found.", None
    size = os.path.getsize(input_path)
    if size > max_size_mb * 1024 * 1024:
        return None, f"Video must be under **{max_size_mb} MB**. Your file: {size / (1024*1024):.1f} MB.", None
    ext = (os.path.basename(input_path) or "").split(".")[-1].lower()
    if ext not in ("mp4", "mov", "avi", "mkv", "webm"):
        return None, "Please use a **video** file (e.g. MP4, MOV).", None
    out_dir = os.path.dirname(input_path)
    output_path = os.path.join(out_dir, "output_dedup.mp4")
    try:
        stats = await asyncio.to_thread(_run_dedup_sync, input_path, output_path)
    except ImportError as e:
        err_msg = str(e).strip()
        if "cv2" in err_msg or "opencv" in err_msg:
            return None, "**Dedup is unavailable:** Install `opencv-python-headless` and `numpy`.", None
        return None, f"**Dedup is unavailable:** {err_msg}", None
    except FileNotFoundError:
        return None, "FFmpeg or script not found.", None
    except Exception as e:
        return None, f"Duplicate removal failed: {e}", None
    if not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
        return None, "Processing produced no output.", None
    if os.path.getsize(output_path) > max_out * 1024 * 1024:
        return None, f"Output over {max_out} MB. Use a shorter/smaller input.", None
    return output_path, None, stats


def _cleanup_tmp(tmp: str) -> None:
    try:
        for f in os.listdir(tmp):
            p = os.path.join(tmp, f)
            if os.path.isfile(p):
                os.unlink(p)
        os.rmdir(tmp)
    except Exception:
        pass

def build_dedup_layout(
    stats: Optional[dict],
    output_path: str,
    footer_text: Optional[str] = None,
    requested_by: Optional[str] = None,
) -> Tuple[Optional[discord.ui.LayoutView], List[discord.File]]:
    files = [discord.File(output_path, filename="dedup.mp4")]
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

    stats_text = ""
    if stats:
        stats_text = (
            f"Original frames: **{stats.get('originalFrames', '?')}**\n"
            f"Duplicates removed: **{stats.get('duplicateFrames', '?')}**\n"
            f"Unique frames: **{stats.get('uniqueFrames', '?')}**"
        )
    if requested_by:
        title_text = f"**Requested by** {requested_by}\n-# Click below to view or download the video."
    else:
        title_text = "**Duplicate frames removed.**\n-# Click below to view or download the video."
    if stats_text:
        title_text += "\n\n" + stats_text

    container_children = [
        TextDisplay(title_text),
        sep,
        MediaGallery(MediaGalleryItem(files[0])),
    ]
    if footer_text:
        container_children.append(TextDisplay(f"-# {footer_text}"))

    class DedupLayout(LayoutView):
        def __init__(self):
            super().__init__(timeout=None)
            container = Container(*container_children)
            self.add_item(container)

    return DedupLayout(), files


class DedupCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.BOT_LOGO = getattr(bot, "BOT_LOGO", None)

    @app_commands.command(name="dedup", description="Remove duplicate/dead frames from a video (small files).")
    async def dedup(self, interaction: discord.Interaction, video: discord.Attachment):
        guild_id = interaction.guild.id if interaction.guild else 0
        max_mb = self.bot.get_max_dedup_size_mb(guild_id)
        await interaction.response.defer()
        output_path, err, stats = await process_dedup(video, max_mb)
        if err:
            embed = discord.Embed(description=err, color=0xE74C3C)
            if self.BOT_LOGO:
                embed.set_footer(text="© TPS Bot (2026) | Duplicate DeadFrames Remover", icon_url=self.BOT_LOGO)
            await interaction.edit_original_response(content=None, embed=embed)
            return
        try:
            footer = "© TPS Bot (2026) | Duplicate DeadFrames Remover"
            view, files = build_dedup_layout(stats, output_path, footer_text=footer)
            if view is not None:
                await interaction.edit_original_response(content="Processed.")
                await interaction.followup.send(view=view, files=files)
            else:
                embed = discord.Embed(description="**Duplicate frames removed.**", color=0x36CFD1)
                if stats:
                    embed.add_field(
                        name="Stats",
                        value=f"Original: **{stats.get('originalFrames', '?')}** | Removed: **{stats.get('duplicateFrames', '?')}** | Unique: **{stats.get('uniqueFrames', '?')}**",
                        inline=False,
                    )
                if self.BOT_LOGO:
                    embed.set_footer(text="© TPS Bot (2026) | Duplicate DeadFrames Remover", icon_url=self.BOT_LOGO)
                await interaction.edit_original_response(content=None, embed=embed)
                await interaction.followup.send(file=files[0])
        finally:
            _cleanup_tmp(os.path.dirname(output_path))


async def setup(bot):
    await bot.add_cog(DedupCog(bot))
