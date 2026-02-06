import discord
from discord import app_commands
from discord.ext import commands

from cogs.utils.db import set_system_channel_db, get_system_channel_db
from cogs.utils.setup_message import build_setup_container_with_image

SYSTEM_CONFIG = {
    "Remove Background": {
        "key": "removebg",
        "description": (
            "**How to use?**\n"
            "Send an image in this channel and the bot will remove the background.\n\n"
            "**Simple, right?** (Max size: **{max_removebg_size_mb} MB**.)"
        ),
    },
    "Remove Duplicate Frames": {
        "key": "dedup",
        "description": (
            "**How to use?**\n"
            "Send a video in this channel and the bot will remove duplicate/dead frames.\n\n"
            "**Keep videos under {max_dedup_size_mb} MB** so the result can be uploaded."
        ),
    },
    "YouTube Download (MP4)": {
        "key": "yt_download_mp4",
        "description": (
            "**How to use?**\n"
            "Post a **YouTube URL** in this channel. The bot will download it as **1080p MP4** and send the file here (or to the results channel)."
        ),
    },
    "YouTube Download (MP3)": {
        "key": "yt_download_mp3",
        "description": (
            "**How to use?**\n"
            "Post a **YouTube URL** in this channel. The bot will download it as **320 kbps MP3** and send the file here (or to the results channel)."
        ),
    },
}

class ManageSystemCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.BOT_LOGO = getattr(bot, "BOT_LOGO", None)

    def _can_manage(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            return False
        allowed_ids = getattr(self.bot, "manage_user_ids", set())
        return (
            interaction.user.id == interaction.guild.owner_id
            or interaction.user.guild_permissions.administrator
            or interaction.user.id in allowed_ids
        )

    @app_commands.command(name="managesystem", description="Setup, change, or remove a system channel (e.g. Remove Background, Dedup).")
    @app_commands.describe(system="Which system to configure", action="Setup this channel, change to this channel, or remove")
    @app_commands.choices(
        system=[app_commands.Choice(name=k, value=k) for k in SYSTEM_CONFIG.keys()],
        action=[
            app_commands.Choice(name="Setup", value="setup"),
            app_commands.Choice(name="Change", value="change"),
            app_commands.Choice(name="Remove", value="remove"),
        ],
    )
    async def managesystem(
        self,
        interaction: discord.Interaction,
        system: app_commands.Choice[str],
        action: app_commands.Choice[str],
    ):
        system_val = system.value
        action_val = action.value
        if not self.bot.connection:
            await interaction.response.send_message(
                "Database is not configured. Set MYSQL_* in .env to use channel setup.",
                ephemeral=True,
            )
            return
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
        if not self._can_manage(interaction):
            await interaction.response.send_message(
                f"Only the server owner or administrators can manage the **{system_val}** channel.",
                ephemeral=True,
            )
            return

        guild_id = interaction.guild.id
        channel_id = interaction.channel.id
        config = SYSTEM_CONFIG[system_val]
        key = config["key"]
        current = get_system_channel_db(self.bot.connection, guild_id, key)

        if action_val in ("setup", "change"):
            set_system_channel_db(self.bot.connection, guild_id, key, channel_id)
            if hasattr(self.bot, "reload_channels"):
                self.bot.reload_channels()
            if action_val == "setup":
                key = config["key"]
                if key == "yt_download_mp4":
                    description = config["description"]
                    title = getattr(self.bot, "yt_download_mp4_setup_title", "YouTube Download (MP4)")
                    image_url = getattr(self.bot, "yt_download_mp4_setup_image_url", None)
                elif key == "yt_download_mp3":
                    description = config["description"]
                    title = getattr(self.bot, "yt_download_mp3_setup_title", "YouTube Download (MP3)")
                    image_url = getattr(self.bot, "yt_download_mp3_setup_image_url", None)
                else:
                    max_rb = self.bot.get_max_removebg_size_mb(guild_id)
                    max_dedup = self.bot.get_max_dedup_size_mb(guild_id)
                    description = config["description"].format(
                        max_removebg_size_mb=max_rb,
                        max_dedup_size_mb=max_dedup,
                    )
                    title = getattr(self.bot, "removebg_setup_title", "Remove Background System") if key == "removebg" else getattr(self.bot, "dedup_setup_title", "Remove Duplicate Frames System")
                    image_url = getattr(self.bot, "removebg_setup_image_url", None) if key == "removebg" else getattr(self.bot, "dedup_setup_image_url", None)
                view, files = await build_setup_container_with_image(
                    title,
                    description,
                    image_url=image_url,
                )
                if view is not None:
                    msg = await interaction.channel.send(view=view, files=files)
                else:
                    embed = discord.Embed(
                        title=title,
                        description=description,
                        color=0x2A2A2A,
                    )
                    if self.BOT_LOGO:
                        embed.set_footer(text="TPS BOT | Setup", icon_url=self.BOT_LOGO)
                    msg = await interaction.channel.send(embed=embed)
                await msg.pin()
            await interaction.response.send_message(
                f"The **{system_val}** channel has been {'set' if action_val == 'setup' else 'updated'} to this channel.",
                ephemeral=True,
            )
        else:
            if current is None:
                await interaction.response.send_message(
                    f"There is no **{system_val}** channel set in this server.",
                    ephemeral=True,
                )
                return
            set_system_channel_db(self.bot.connection, guild_id, key, None)
            if hasattr(self.bot, "reload_channels"):
                self.bot.reload_channels()
            await interaction.response.send_message(
                f"The **{system_val}** channel has been removed from this server.",
                ephemeral=True,
            )

async def setup(bot):
    await bot.add_cog(ManageSystemCog(bot))
