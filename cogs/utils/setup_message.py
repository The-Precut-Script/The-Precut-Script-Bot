import asyncio
import io
import urllib.request
from typing import Optional, List, Tuple

import discord

def build_text_container(
    body_text: str,
    footer_text: Optional[str] = None,
) -> Tuple[Optional[discord.ui.LayoutView], List[discord.File]]:
    LayoutView = getattr(discord.ui, "LayoutView", None)
    Container = getattr(discord.ui, "Container", None)
    TextDisplay = getattr(discord.ui, "TextDisplay", None)
    Separator = getattr(discord.ui, "Separator", None)
    if not all((LayoutView, Container, TextDisplay)):
        return None, []
    text = body_text
    if footer_text:
        text += f"\n\n-# {footer_text}"
    try:
        sep = Separator(spacing=discord.SeparatorSpacing.small)
    except Exception:
        sep = Separator()
    container_children = [TextDisplay(text), sep]

    class TextLayout(LayoutView):
        def __init__(self):
            super().__init__(timeout=None)
            container = Container(*container_children)
            self.add_item(container)

    return TextLayout(), []

async def _fetch_image(url: str) -> Optional[bytes]:
    def _get():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AE-Scripts-Bot/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.read()
        except Exception:
            return None
    return await asyncio.to_thread(_get)

async def build_setup_container_with_image(
    title: str,
    description: str,
    image_url: Optional[str] = None,
    footer_text: Optional[str] = None,
) -> Tuple[Optional[discord.ui.LayoutView], List[discord.File]]:
    LayoutView = getattr(discord.ui, "LayoutView", None)
    Container = getattr(discord.ui, "Container", None)
    TextDisplay = getattr(discord.ui, "TextDisplay", None)
    Separator = getattr(discord.ui, "Separator", None)
    MediaGallery = getattr(discord.ui, "MediaGallery", None)
    MediaGalleryItem = getattr(discord, "MediaGalleryItem", None) or getattr(discord.ui, "MediaGalleryItem", None)
    if not all((LayoutView, Container, TextDisplay)):
        return None, []

    text = f"**{title}**\n\n{description}"
    if footer_text:
        text += f"\n\n-# {footer_text}"
    try:
        sep = Separator(spacing=discord.SeparatorSpacing.small)
    except Exception:
        sep = Separator()

    container_children = [TextDisplay(text), sep]
    files = []
    if image_url and MediaGallery and MediaGalleryItem:
        image_bytes = await _fetch_image(image_url)
        if image_bytes and len(image_bytes) < 8 * 1024 * 1024:
            f = discord.File(io.BytesIO(image_bytes), filename="setup.png")
            files.append(f)
            container_children.append(MediaGallery(MediaGalleryItem(f)))

    class SetupLayout(LayoutView):
        def __init__(self):
            super().__init__(timeout=None)
            container = Container(*container_children)
            self.add_item(container)

    return SetupLayout(), files
