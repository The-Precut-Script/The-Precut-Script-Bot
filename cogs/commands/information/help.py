import discord
from discord import app_commands
from discord.ext import commands

from cogs.utils.setup_message import build_text_container


class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.BOT_LOGO = getattr(bot, "BOT_LOGO", None)

    @app_commands.command(name="help", description="Shows all bot commands.")
    async def help(self, interaction: discord.Interaction):
        commands_list = {
            "Information": [
                ("/info", "About the bot"),
                ("/help", "This command list"),
                ("/ping", "Bot latency and status"),
            ],
            "Media processing": [
                ("/removebg", "Remove background from an image"),
                ("/dedup", "Remove duplicate/dead frames from a video (small files)"),
                ("YouTube MP4 (channel)", "Post a YouTube URL in the YouTube Download (MP4) channel → 1080p MP4"),
                ("YouTube MP3 (channel)", "Post a YouTube URL in the YouTube Download (MP3) channel → 320 kbps MP3"),
            ],
            "Setup (admin)": [
                ("/managesystem", "Setup Remove BG, Dedup, YouTube MP4, or YouTube MP3 channel (run in that channel)"),
                ("/setup_results", "Set channel where Dedup or Remove BG results are posted (run in that channel)"),
            ],
        }

        parts = []
        for category, cmds in commands_list.items():
            part = f"**{category}**\n" + "\n".join(f"• {name} — {desc}" for name, desc in cmds)
            parts.append(part)

        body = "**TPS Bot — Commands**\n\n" + "\n\n".join(parts)
        footer = "© TPS Bot (2026) | Help"
        view, _ = build_text_container(body, footer_text=footer)
        if view is not None:
            await interaction.response.send_message(view=view, ephemeral=True)
        else:
            embed = discord.Embed(
                title="TPS Bot — Commands",
                description="\n\n".join(parts),
                color=0x2A2A2A,
            )
            if self.BOT_LOGO:
                embed.set_footer(text=footer, icon_url=self.BOT_LOGO)
            else:
                embed.set_footer(text=footer)
            await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(HelpCog(bot))
