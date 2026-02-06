import asyncio
import io
import os
import platform
import logging
import re
import uuid
from datetime import datetime
from typing import Optional

YT_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/)[\w-]+",
    re.IGNORECASE,
)

import discord
from discord import app_commands
from discord.ext import commands

_bot_dir = os.path.dirname(os.path.abspath(__file__))
from dotenv import load_dotenv
load_dotenv(os.path.join(_bot_dir, ".env"))

from cogs.utils.db import (
    initialize_database,
    load_channels_from_db,
    enqueue_media,
    count_pending,
    get_next_pending,
    set_queue_job_completed,
    set_queue_job_failed,
)

BOT_LOGO = (os.environ.get("BOT_LOGO", "").strip() or None)
TOKEN = os.environ.get("DISCORD_TOKEN", "").strip()
if not TOKEN:
    raise ValueError("Set DISCORD_TOKEN in .env.")

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("ae_scripts_bot")

connection = initialize_database()
if connection is None:
    logger.warning("MySQL not configured. Set MYSQL_* in .env. Channel setup disabled.")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
bot.connection = connection
bot.BOT_LOGO = BOT_LOGO
bot.channels_cache = load_channels_from_db(connection) if connection else {}
_env_max_removebg = (os.environ.get("MAX_REMOVEBG_SIZE_MB", "") or "").strip()
_env_max_dedup = (os.environ.get("MAX_DEDUP_SIZE_MB", "") or "").strip()
bot.max_removebg_size_mb_env = int(_env_max_removebg) if _env_max_removebg.isdigit() else None
bot.max_dedup_size_mb_env = int(_env_max_dedup) if _env_max_dedup.isdigit() else None
bot.removebg_max_dimension = int(os.environ.get("REMOVEBG_MAX_DIMENSION", "1024") or "1024")
bot.removebg_timeout_seconds = float(os.environ.get("REMOVEBG_TIMEOUT_SECONDS", "120") or "120")
bot.removebg_model = (os.environ.get("REMOVEBG_MODEL", "u2netp") or "u2netp").strip().lower()

bot.removebg_setup_title = (os.environ.get("REMOVEBG_SETUP_TITLE", "") or "").strip() or "Remove Background System"
bot.dedup_setup_title = (os.environ.get("DEDUP_SETUP_TITLE", "") or "").strip() or "Remove Duplicate Frames System"
bot.dedup_results_setup_title = (os.environ.get("DEDUP_RESULTS_SETUP_TITLE", "") or "").strip() or "Dedup Results"
bot.removebg_results_setup_title = (os.environ.get("REMOVEBG_RESULTS_SETUP_TITLE", "") or "").strip() or "Remove BG Results"
bot.removebg_setup_image_url = (os.environ.get("REMOVEBG_SETUP_IMAGE_URL", "") or "").strip() or None
bot.dedup_setup_image_url = (os.environ.get("DEDUP_SETUP_IMAGE_URL", "") or "").strip() or None
bot.dedup_results_setup_image_url = (os.environ.get("DEDUP_RESULTS_SETUP_IMAGE_URL", "") or "").strip() or None
bot.removebg_results_setup_image_url = (os.environ.get("REMOVEBG_RESULTS_SETUP_IMAGE_URL", "") or "").strip() or None
bot.yt_download_mp4_setup_title = (os.environ.get("YT_DOWNLOAD_MP4_SETUP_TITLE", "") or "").strip() or "YouTube Download (MP4)"
bot.yt_download_mp4_setup_image_url = (os.environ.get("YT_DOWNLOAD_MP4_SETUP_IMAGE_URL", "") or "").strip() or None
bot.yt_download_mp3_setup_title = (os.environ.get("YT_DOWNLOAD_MP3_SETUP_TITLE", "") or "").strip() or "YouTube Download (MP3)"
bot.yt_download_mp3_setup_image_url = (os.environ.get("YT_DOWNLOAD_MP3_SETUP_IMAGE_URL", "") or "").strip() or None

_manage_ids_str = (os.environ.get("BOT_MANAGE_USER_IDS", "") or "977190163736322088").strip()
bot.manage_user_ids = set()
for part in _manage_ids_str.split(","):
    part = part.strip()
    if part.isdigit():
        bot.manage_user_ids.add(int(part))

_queue_dir = os.path.join(_bot_dir, "queue_uploads")
bot.queue_uploads_dir = _queue_dir
for sub in ("removebg", "dedup", "yt_download"):
    d = os.path.join(_queue_dir, sub)
    if not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)

def bot_get_system_channel(guild_id: int, system: str) -> Optional[int]:
    g = bot.channels_cache.get(str(guild_id), {})
    return g.get(system)

def reload_channels():
    if bot.connection:
        bot.channels_cache = load_channels_from_db(bot.connection)

bot.reload_channels = reload_channels
_ready_once = False

async def _change_status():
    statuses = [
        discord.Activity(name="🛠️ In development not released yet", type=discord.ActivityType.playing),
    ]
    while True:
        for activity in statuses:
            try:
                await bot.change_presence(status=discord.Status.dnd, activity=activity)
            except Exception:
                pass
            await asyncio.sleep(30)

async def _reply_or_send(bot, channel_id: int, author_id: int, message_id: Optional[int], text: str):
    ch = bot.get_channel(channel_id)
    if not ch:
        return
    if message_id:
        try:
            msg = await ch.fetch_message(message_id)
            await msg.reply(text)
            return
        except Exception:
            pass
    await ch.send(f"<@{author_id}> {text}")

async def _send_status_reply(bot, channel_id: int, author_id: int, message_id: Optional[int], content: str):
    ch = bot.get_channel(channel_id)
    if not ch:
        return None
    if message_id:
        try:
            ref_msg = await ch.fetch_message(message_id)
            return await ref_msg.reply(content)
        except Exception:
            pass
    return await ch.send(f"<@{author_id}> {content}")


async def _progress_loop(status_msg, prefix: str, interval: float = 2.0):
    steps = [0, 15, 25, 40, 55, 70, 85, 90]
    for p in steps:
        try:
            await status_msg.edit(content=f"{prefix} **{p}%**")
        except Exception:
            pass
        await asyncio.sleep(interval)
    while True:
        try:
            await status_msg.edit(content=f"{prefix} **90%**")
        except Exception:
            pass
        await asyncio.sleep(interval)

async def _worker_removebg():
    from cogs.commands.mediaprocessing.removebg import process_removebg_from_path, build_removebg_layout
    while True:
        try:
            if not bot.connection:
                await asyncio.sleep(5)
                continue
            row = get_next_pending(bot.connection, "removebg")
            if not row:
                await asyncio.sleep(2)
                continue
            job_id, guild_id, channel_id, author_id, message_id, file_path = row
            channel = bot.get_channel(channel_id)
            if not channel:
                set_queue_job_failed(bot.connection, job_id, "Channel not found")
                try:
                    os.remove(file_path)
                except Exception:
                    pass
                continue
            try:
                status_msg = await _send_status_reply(bot, channel_id, author_id, message_id, "Removing background… **0%**")
                if not status_msg:
                    status_msg = await channel.send("Removing background… **0%**")
                progress_task = asyncio.create_task(_progress_loop(status_msg, "Removing background…", 2.0))
                try:
                    png_bytes, err = await process_removebg_from_path(
                        file_path,
                        get_max_removebg_size_mb(guild_id),
                        max_dimension=getattr(bot, "removebg_max_dimension", 1024),
                        timeout_seconds=getattr(bot, "removebg_timeout_seconds", 120.0),
                        model=getattr(bot, "removebg_model", "u2netp"),
                    )
                finally:
                    progress_task.cancel()
                    try:
                        await progress_task
                    except asyncio.CancelledError:
                        pass
                if err:
                    set_queue_job_failed(bot.connection, job_id, err)
                    try:
                        await status_msg.edit(content=err)
                    except Exception:
                        await _reply_or_send(bot, channel_id, author_id, message_id, err)
                else:
                    set_queue_job_completed(bot.connection, job_id)
                    results_channel_id = bot_get_system_channel(guild_id, "removebg_results")
                    requested_by = f"<@{author_id}>" if results_channel_id else None
                    view, files = build_removebg_layout(
                        png_bytes,
                        footer_text="© TPS Bot (2026) | Remove Background",
                        requested_by=requested_by,
                    )
                    if results_channel_id:
                        results_channel = bot.get_channel(results_channel_id)
                        if results_channel:
                            await results_channel.send(view=view, files=files)
                            done_text = f"Done! Your image was sent to {results_channel.mention}."
                        else:
                            if view is not None:
                                await channel.send(view=view, files=files)
                            else:
                                await channel.send("**Background removed**", file=files[0])
                            done_text = "Done! Background removed."
                    else:
                        if view is not None:
                            await channel.send(view=view, files=files)
                        else:
                            await channel.send("**Background removed**", file=files[0])
                        done_text = "Done! Background removed."
                    try:
                        await status_msg.edit(content=done_text)
                    except Exception:
                        await _reply_or_send(bot, channel_id, author_id, message_id, done_text)
            except Exception as e:
                logger.exception("Removebg worker error: %s", e)
                set_queue_job_failed(bot.connection, job_id, str(e))
                try:
                    await channel.send(f"Remove background failed: {e}")
                except Exception:
                    pass
            finally:
                try:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                    d = os.path.dirname(file_path)
                    if d and os.path.isdir(d) and not os.listdir(d):
                        os.rmdir(d)
                except Exception:
                    pass
        except Exception as e:
            logger.exception("Removebg worker loop: %s", e)
            await asyncio.sleep(5)

async def _worker_dedup():
    from cogs.commands.mediaprocessing.dedup import process_dedup_from_path, _cleanup_tmp, build_dedup_layout
    while True:
        try:
            if not bot.connection:
                await asyncio.sleep(5)
                continue
            row = get_next_pending(bot.connection, "dedup")
            if not row:
                await asyncio.sleep(2)
                continue
            job_id, guild_id, channel_id, author_id, message_id, file_path = row
            channel = bot.get_channel(channel_id)
            if not channel:
                set_queue_job_failed(bot.connection, job_id, "Channel not found")
                _cleanup_tmp(os.path.dirname(file_path))
                continue
            out = None
            try:
                status_msg = await _send_status_reply(bot, channel_id, author_id, message_id, "Removing duplicate frames…")
                if not status_msg:
                    status_msg = await channel.send("Removing duplicate frames…")
                out, err, stats = await process_dedup_from_path(file_path, get_max_dedup_size_mb(guild_id))
                if err:
                    set_queue_job_failed(bot.connection, job_id, err)
                    try:
                        await status_msg.edit(content=err)
                    except Exception:
                        await _reply_or_send(bot, channel_id, author_id, message_id, err)
                else:
                    set_queue_job_completed(bot.connection, job_id)
                    results_channel_id = bot_get_system_channel(guild_id, "dedup_results")
                    requested_by = f"<@{author_id}>" if results_channel_id else None
                    view, files = build_dedup_layout(
                        stats, out,
                        footer_text="© TPS Bot (2026) | Duplicate DeadFrames Remover",
                        requested_by=requested_by,
                    )
                    if results_channel_id:
                        results_channel = bot.get_channel(results_channel_id)
                        if results_channel:
                            await results_channel.send(view=view, files=files)
                            done_text = f"Done! Your clip was sent to {results_channel.mention}."
                        else:
                            await channel.send(view=view, files=files)
                            done_text = "Done! Duplicate frames removed."
                    else:
                        await channel.send(view=view, files=files)
                        done_text = "Done! Duplicate frames removed."
                    try:
                        await status_msg.edit(content=done_text)
                    except Exception:
                        await _reply_or_send(bot, channel_id, author_id, message_id, done_text)
            except Exception as e:
                logger.exception("Dedup worker error: %s", e)
                set_queue_job_failed(bot.connection, job_id, str(e))
                try:
                    await channel.send(f"Dedup failed: {e}")
                except Exception:
                    pass
            finally:
                if out and os.path.dirname(out):
                    _cleanup_tmp(os.path.dirname(out))
        except Exception as e:
            logger.exception("Dedup worker loop: %s", e)
            await asyncio.sleep(5)

def _guild_file_size_limit_bytes(guild_id: int) -> int:
    guild = bot.get_guild(guild_id)
    if guild and getattr(guild, "premium_subscription_count", 0) >= 7:
        return 50 * 1024 * 1024
    return 8 * 1024 * 1024

def _guild_max_upload_mb(guild_id: int) -> int:
    return _guild_file_size_limit_bytes(guild_id) // (1024 * 1024)

def get_max_removebg_size_mb(guild_id: int) -> int:
    if getattr(bot, "max_removebg_size_mb_env", None) is not None:
        return bot.max_removebg_size_mb_env
    return _guild_max_upload_mb(guild_id)

def get_max_dedup_size_mb(guild_id: int) -> int:
    if getattr(bot, "max_dedup_size_mb_env", None) is not None:
        return bot.max_dedup_size_mb_env
    return _guild_max_upload_mb(guild_id)

bot.get_max_removebg_size_mb = get_max_removebg_size_mb
bot.get_max_dedup_size_mb = get_max_dedup_size_mb

async def _worker_yt_download():
    from cogs.utils.yt_downloader import download_video_mp4, download_audio_mp3, build_yt_download_layout
    while True:
        try:
            if not bot.connection:
                await asyncio.sleep(5)
                continue
            row = get_next_pending(bot.connection, "yt_download_mp4")
            system = "yt_download_mp4"
            if not row:
                row = get_next_pending(bot.connection, "yt_download_mp3")
                system = "yt_download_mp3"
            if not row:
                await asyncio.sleep(2)
                continue
            job_id, guild_id, channel_id, author_id, message_id, file_path = row
            url = (file_path or "").strip()
            if not url:
                set_queue_job_failed(bot.connection, job_id, "Invalid job data")
                continue
            channel = bot.get_channel(channel_id)
            if not channel:
                set_queue_job_failed(bot.connection, job_id, "Channel not found")
                continue
            job_dir = os.path.join(bot.queue_uploads_dir, "yt_download", str(uuid.uuid4()))
            out_path = None
            try:
                status_msg = await _send_status_reply(
                    bot, channel_id, author_id, message_id,
                    "Downloading from YouTube…",
                )
                if not status_msg:
                    status_msg = await channel.send("Downloading from YouTube…")
                max_height = None
                if system == "yt_download_mp3":
                    out_path = await asyncio.to_thread(
                        download_audio_mp3, url, job_dir, "320",
                    )
                else:
                    discord_limit = _guild_file_size_limit_bytes(guild_id)
                    max_height = 1080 if discord_limit >= 50 * 1024 * 1024 else 720
                    out_path = await asyncio.to_thread(
                        download_video_mp4, url, job_dir, max_height,
                    )
                out_path = os.path.normpath(str(out_path))
                if not os.path.isfile(out_path):
                    set_queue_job_failed(bot.connection, job_id, "Output file not found")
                    try:
                        await status_msg.edit(content="Download failed: output file not found.")
                    except Exception:
                        await _reply_or_send(bot, channel_id, author_id, message_id, "Download failed: output file not found.")
                    continue
                size = os.path.getsize(out_path)
                discord_limit = _guild_file_size_limit_bytes(guild_id)
                limit_mb = discord_limit / (1024 * 1024)
                if size > discord_limit:
                    set_queue_job_completed(bot.connection, job_id)
                    try:
                        await status_msg.edit(
                            content=f"Done, but the file is too large for Discord (**{size / (1024*1024):.1f} MB** > {limit_mb:.0f} MB for this server). Boost the server for a higher limit.",
                        )
                    except Exception:
                        await _reply_or_send(
                            bot, channel_id, author_id, message_id,
                            f"File too large for Discord ({size / (1024*1024):.1f} MB > {limit_mb:.0f} MB).",
                        )
                    continue
                set_queue_job_completed(bot.connection, job_id)
                results_key = "yt_download_mp4_results" if system == "yt_download_mp4" else "yt_download_mp3_results"
                results_channel_id = bot_get_system_channel(guild_id, results_key)
                kind = "audio" if system == "yt_download_mp3" else "video"
                footer = (
                    "© TPS Bot (2026) | YouTube Download (MP3)"
                    if kind == "audio"
                    else "© TPS Bot (2026) | YouTube Download (MP4)"
                )
                size_mb = os.path.getsize(out_path) / (1024 * 1024)
                if kind == "video":
                    res = "1080p" if max_height == 1080 else "720p"
                    info_text = f"Format: **WebM** • Resolution: **{res}**\nFile size: **{size_mb:.1f} MB**"
                else:
                    info_text = f"Format: **MP3** • Bitrate: **320 kbps**\nFile size: **{size_mb:.1f} MB**"
                if results_channel_id and bot.get_channel(results_channel_id):
                    requested_by = f"<@{author_id}>"
                else:
                    requested_by = None
                view, files = build_yt_download_layout(
                    out_path, footer_text=footer, requested_by=requested_by, kind=kind, info_text=info_text
                )
                plain_content = (f"**Requested by** <@{author_id}>" if requested_by else f"**{kind.capitalize()} downloaded.**") + "\n\n" + info_text
                if results_channel_id:
                    results_channel = bot.get_channel(results_channel_id)
                    if results_channel:
                        if view is not None:
                            await results_channel.send(view=view, files=files)
                        else:
                            await results_channel.send(plain_content, file=files[0])
                        done_text = f"Done! Your file was sent to {results_channel.mention}."
                    else:
                        if view is not None:
                            await channel.send(view=view, files=files)
                        else:
                            await channel.send(plain_content, file=files[0])
                        done_text = "Done! Here's your file."
                else:
                    if view is not None:
                        await channel.send(view=view, files=files)
                    else:
                        await channel.send(plain_content, file=files[0])
                    done_text = "Done! Here's your file."
                try:
                    await status_msg.edit(content=done_text)
                except Exception:
                    await _reply_or_send(bot, channel_id, author_id, message_id, done_text)
            except Exception as e:
                logger.exception("YT download worker error: %s", e)
                set_queue_job_failed(bot.connection, job_id, str(e))
                try:
                    await channel.send(f"YouTube download failed: {e}")
                except Exception:
                    pass
            finally:
                if job_dir and os.path.isdir(job_dir):
                    try:
                        for f in os.listdir(job_dir):
                            try:
                                os.remove(os.path.join(job_dir, f))
                            except Exception:
                                pass
                        os.rmdir(job_dir)
                    except Exception:
                        pass
        except Exception as e:
            logger.exception("YT download worker loop: %s", e)
            await asyncio.sleep(5)

async def load_cogs():
    base = os.path.join(os.path.dirname(__file__), "cogs", "commands")
    if not os.path.isdir(base):
        return
    for folder in os.listdir(base):
        # Skip legacy After Effects extension commands for the public bot build
        if folder == "aftereffects":
            continue
        path = os.path.join(base, folder)
        if not os.path.isdir(path):
            continue
        for f in os.listdir(path):
            if f.endswith(".py") and not f.startswith("__"):
                ext = f"cogs.commands.{folder}.{f[:-3]}"
                try:
                    await bot.load_extension(ext)
                    logger.info("Loaded: %s", ext)
                except Exception as e:
                    logger.exception("Failed %s: %s", ext, e)

@bot.event
async def on_message(message):
    await bot.process_commands(message)
    if message.author.bot or not message.guild:
        return
    gid = message.guild.id
    cid = message.channel.id
    is_removebg_ch = bot_get_system_channel(gid, "removebg") == cid
    is_dedup_ch = bot_get_system_channel(gid, "dedup") == cid
    is_yt_mp4_ch = bot_get_system_channel(gid, "yt_download_mp4") == cid
    is_yt_mp3_ch = bot_get_system_channel(gid, "yt_download_mp3") == cid

    if is_yt_mp4_ch or is_yt_mp3_ch:
        match = YT_URL_PATTERN.search(message.content or "")
        if not match:
            try:
                await message.delete()
            except discord.Forbidden:
                pass
            return
        url = match.group(0)
        if not connection:
            await message.reply("Queue is unavailable (database not configured).")
            return
        system = "yt_download_mp4" if is_yt_mp4_ch else "yt_download_mp3"
        job_id = enqueue_media(connection, gid, message.channel.id, message.author.id, message.id, system, url)
        if job_id is None:
            await message.reply("Could not add to queue. Try again later.")
            return
        n = count_pending(connection, system)
        if n > 1:
            await message.reply(f"You're **#{n}** in the queue. I'll reply here when your download is ready.")
        return

    if is_removebg_ch or is_dedup_ch:
        if not message.attachments or len(message.attachments) > 1:
            try:
                await message.delete()
            except discord.Forbidden:
                pass
            return

    if not message.attachments or len(message.attachments) != 1:
        return
    att = message.attachments[0]

    if is_removebg_ch:
        if not connection:
            await message.reply("Queue is unavailable (database not configured).")
            return
        max_mb = get_max_removebg_size_mb(gid)
        if att.size > max_mb * 1024 * 1024:
            await message.reply(f"Image must be under **{max_mb} MB** for this server (based on your boost level). Your file: {att.size / (1024*1024):.1f} MB.")
            return
        try:
            data = await att.read()
        except Exception as e:
            await message.reply(f"Failed to download image: {e}")
            return
        ext = (att.filename or "image.png").split(".")[-1].lower() or "png"
        if ext not in ("png", "jpg", "jpeg", "webp", "bmp", "gif"):
            ext = "png"
        job_dir = os.path.join(bot.queue_uploads_dir, "removebg", str(uuid.uuid4()))
        os.makedirs(job_dir, exist_ok=True)
        file_path = os.path.join(job_dir, f"input.{ext}")
        try:
            with open(file_path, "wb") as f:
                f.write(data)
        except Exception as e:
            await message.reply(f"Failed to save file: {e}")
            return
        job_id = enqueue_media(connection, gid, message.channel.id, message.author.id, message.id, "removebg", file_path)
        if job_id is None:
            try:
                os.remove(file_path)
            except Exception:
                pass
            await message.reply("Could not add to queue. Try again later.")
            return
        n = count_pending(connection, "removebg")
        if n > 1:
            await message.reply(f"You're **#{n}** in the queue. \n I'll reply here when your request is done.")
        return

    if is_dedup_ch:
        if not connection:
            await message.reply("Queue is unavailable (database not configured).")
            return
        max_mb = get_max_dedup_size_mb(gid)
        if att.size > max_mb * 1024 * 1024:
            await message.reply(f"Video must be under **{max_mb} MB** for this server (based on your boost level). Your file: {att.size / (1024*1024):.1f} MB.")
            return
        try:
            data = await att.read()
        except Exception as e:
            await message.reply(f"Failed to download video: {e}")
            return
        ext = (att.filename or "video.mp4").split(".")[-1].lower() or "mp4"
        if ext not in ("mp4", "mov", "avi", "mkv", "webm"):
            ext = "mp4"
        job_dir = os.path.join(bot.queue_uploads_dir, "dedup", str(uuid.uuid4()))
        os.makedirs(job_dir, exist_ok=True)
        file_path = os.path.join(job_dir, f"input.{ext}")
        try:
            with open(file_path, "wb") as f:
                f.write(data)
        except Exception as e:
            await message.reply(f"Failed to save file: {e}")
            return
        job_id = enqueue_media(connection, gid, message.channel.id, message.author.id, message.id, "dedup", file_path)
        if job_id is None:
            from cogs.commands.mediaprocessing.dedup import _cleanup_tmp
            _cleanup_tmp(job_dir)
            await message.reply("Could not add to queue. Try again later.")
            return
        n = count_pending(connection, "dedup")
        if n > 1:
            await message.reply(f"You're **#{n}** in the queue. Processing one at a time—I'll reply here when yours is ready.")
        return

@bot.event
async def on_ready():
    global _ready_once
    try:
        bot.start_time = datetime.now()
        if not _ready_once:
            _ready_once = True
            print("\n" + "=" * 60 + "\nTPS BOT — STARTUP\n" + "=" * 60)
            await load_cogs()
            bot.loop.create_task(_worker_removebg())
            bot.loop.create_task(_worker_dedup())
            bot.loop.create_task(_worker_yt_download())
            bot.loop.create_task(_change_status())
            print("Queue workers started (removebg, dedup, yt_download). Status: development.")
            print("Connected:", bot.user.name, "| Python:", platform.python_version(), "| discord.py:", discord.__version__)
            print("MySQL:", "connected" if connection else "not configured")
            try:
                synced = await bot.tree.sync()
                print("Slash commands synced:", len(synced))
            except Exception as e:
                print("Sync warning:", e)
            print("Bot ready.\n")
        else:
            if connection:
                reload_channels()
            print("Bot reconnected. Guilds:", len(bot.guilds))
    except Exception as e:
        logger.exception("on_ready failed: %s", e)
        raise

@bot.event
async def on_guild_join(guild: discord.Guild):
    logger.info("Joined guild: %s (id=%s, member_count=%s)", guild.name, guild.id, guild.member_count)
    print(f"Joined server: {guild.name} (id={guild.id})")

@bot.event
async def on_guild_remove(guild: discord.Guild):
    logger.info("Removed from guild: %s (id=%s)", guild.name, guild.id)
    print(f"Removed from server: {guild.name} (id={guild.id}) — check server Audit Log to see who/what removed the bot.")

def main():
    bot.run(TOKEN)

if __name__ == "__main__":
    main()
