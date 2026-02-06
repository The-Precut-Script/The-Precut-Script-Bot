import asyncio
import io
import os
from typing import List, Optional, Tuple

import discord
from discord.ext import commands

_removebg_semaphore = asyncio.Semaphore(1)
_rembg_remove = None
_new_session = None

def _get_rembg():
    global _rembg_remove, _new_session
    if _rembg_remove is None:
        try:
            from rembg import remove as rembg_remove
            from rembg import new_session
            _rembg_remove = rembg_remove
            _new_session = new_session
        except ImportError:
            raise RuntimeError(
                "rembg is required for remove background. Install with: pip install rembg[cpu] (or rembg[gpu])"
            )
    return _rembg_remove, _new_session

def _downscale_if_needed(image_bytes: bytes, max_dimension: int):
    if max_dimension <= 0:
        return image_bytes, False
    from PIL import Image
    inp = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    w, h = inp.size
    if w <= max_dimension and h <= max_dimension:
        return image_bytes, False
    if w >= h:
        new_w = max_dimension
        new_h = max(1, int(h * max_dimension / w))
    else:
        new_h = max_dimension
        new_w = max(1, int(w * max_dimension / h))
    try:
        resample = Image.Resampling.LANCZOS
    except AttributeError:
        resample = Image.LANCZOS
    inp = inp.resize((new_w, new_h), resample)
    buf = io.BytesIO()
    inp.save(buf, format="PNG")
    return buf.getvalue(), True

def _run_remove_bg_sync(image_bytes: bytes, model: str = "u2netp") -> bytes:
    from PIL import Image
    remove_fn, new_session_fn = _get_rembg()
    session = None
    if model:
        try:
            session = new_session_fn(model)
        except Exception:
            session = new_session_fn("u2net")
    inp = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    out = remove_fn(inp, session=session) if session else remove_fn(inp)
    if out.mode != "RGBA":
        out = out.convert("RGBA")
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()

async def process_removebg(
    attachment: discord.Attachment,
    max_size_mb: int,
    max_dimension: int = 1024,
    timeout_seconds: float = 120.0,
    model: str = "u2netp",
) -> tuple[Optional[bytes], Optional[str]]:
    if attachment.size > max_size_mb * 1024 * 1024:
        return None, f"Image must be under **{max_size_mb} MB** (Discord limit). Your file: {attachment.size / (1024*1024):.1f} MB."
    content_type = (attachment.content_type or "").lower()
    if content_type and "image" not in content_type:
        return None, "Please upload an **image** (PNG, JPG, etc.)."
    try:
        image_bytes = await attachment.read()
    except Exception as e:
        return None, f"Failed to download image: {e}"

    if max_dimension > 0:
        try:
            image_bytes, _ = await asyncio.to_thread(_downscale_if_needed, image_bytes, max_dimension)
        except Exception:
            pass

    async with _removebg_semaphore:
        try:
            png_bytes = await asyncio.wait_for(
                asyncio.to_thread(_run_remove_bg_sync, image_bytes, model),
                timeout=timeout_seconds,
            )
            return png_bytes, None
        except asyncio.TimeoutError:
            return None, "Background removal timed out (server busy or image too large). Try a smaller image or try again later."
        except Exception as e:
            return None, f"Background removal failed: {e}"

async def process_removebg_from_path(
    file_path: str,
    max_size_mb: int,
    max_dimension: int = 1024,
    timeout_seconds: float = 120.0,
    model: str = "u2netp",
) -> tuple[Optional[bytes], Optional[str]]:
    if not os.path.isfile(file_path):
        return None, "Image file not found."
    size = os.path.getsize(file_path)
    if size > max_size_mb * 1024 * 1024:
        return None, f"Image must be under **{max_size_mb} MB**. Your file: {size / (1024*1024):.1f} MB."
    ext = (os.path.basename(file_path) or "").split(".")[-1].lower()
    if ext not in ("png", "jpg", "jpeg", "webp", "bmp", "gif"):
        return None, "Please use an **image** file (PNG, JPG, etc.)."
    try:
        with open(file_path, "rb") as f:
            image_bytes = f.read()
    except Exception as e:
        return None, f"Failed to read image: {e}"
    if max_dimension > 0:
        try:
            image_bytes, _ = await asyncio.to_thread(_downscale_if_needed, image_bytes, max_dimension)
        except Exception:
            pass
    async with _removebg_semaphore:
        try:
            png_bytes = await asyncio.wait_for(
                asyncio.to_thread(_run_remove_bg_sync, image_bytes, model),
                timeout=timeout_seconds,
            )
            return png_bytes, None
        except asyncio.TimeoutError:
            return None, "Background removal timed out (server busy or image too large). Try a smaller image or try again later."
        except Exception as e:
            return None, f"Background removal failed: {e}"

def build_removebg_layout(
    png_bytes: bytes,
    footer_text: Optional[str] = None,
    requested_by: Optional[str] = None,
) -> Tuple[Optional[discord.ui.LayoutView], List[discord.File]]:
    files = [discord.File(io.BytesIO(png_bytes), filename="removebg.png")]
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

    if requested_by:
        title_text = f"**Requested by** {requested_by}\n-# Click below to view or download the image."
    else:
        title_text = "**Background removed.**\n-# Click below to view or download the image."

    container_children = [
        TextDisplay(title_text),
        sep,
        MediaGallery(MediaGalleryItem(files[0])),
    ]
    if footer_text:
        container_children.append(TextDisplay(f"-# {footer_text}"))

    class RemoveBgLayout(LayoutView):
        def __init__(self):
            super().__init__(timeout=None)
            container = Container(*container_children)
            self.add_item(container)

    return RemoveBgLayout(), files

class RemoveBgCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.BOT_LOGO = getattr(bot, "BOT_LOGO", None)

    @discord.app_commands.command(name="removebg", description="Remove background from an image. Upload one image.")
    async def removebg(self, interaction: discord.Interaction, image: discord.Attachment):
        guild_id = interaction.guild.id if interaction.guild else 0
        max_mb = self.bot.get_max_removebg_size_mb(guild_id)
        max_dim = getattr(self.bot, "removebg_max_dimension", 1024)
        timeout_s = getattr(self.bot, "removebg_timeout_seconds", 120.0)
        model = getattr(self.bot, "removebg_model", "u2netp")
        await interaction.response.defer()
        png_bytes, err = await process_removebg(image, max_mb, max_dimension=max_dim, timeout_seconds=timeout_s, model=model)
        if err:
            embed = discord.Embed(description=err, color=0xE74C3C)
            if self.BOT_LOGO:
                embed.set_footer(text="© TPS Bot (2026) | Remove Background", icon_url=self.BOT_LOGO)
            await interaction.edit_original_response(content=None, embed=embed)
            return
        view, files = build_removebg_layout(
            png_bytes,
            footer_text="© TPS Bot (2026) | Remove Background",
            requested_by=None,
        )
        if view is not None:
            await interaction.edit_original_response(content="Processed.")
            await interaction.followup.send(view=view, files=files)
        else:
            embed = discord.Embed(description="**Background removed**", color=0x2A2A2A)
            if self.BOT_LOGO:
                embed.set_footer(text="© TPS Bot (2026) | Remove Background", icon_url=self.BOT_LOGO)
            await interaction.edit_original_response(content=None, embed=embed)
            await interaction.followup.send(file=files[0])

async def setup(bot):
    await bot.add_cog(RemoveBgCog(bot))
