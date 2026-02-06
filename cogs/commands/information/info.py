import discord
from discord import app_commands
from discord.ext import commands


class InfoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.BOT_LOGO = getattr(bot, "BOT_LOGO", None)

    def create_info_embed(self):
        embed = discord.Embed(
            title="About TPS Bot",
            description=(
                "TPS Bot is a Discord bot built from the **The Precut Script** After Effects extension. "
                "It is essentially a clone of the script, but reimagined as a Discord bot.\n\n"
            ),
            color=0x2A2A2A,
        )
        embed.add_field(
            name="Features",
            value=(
                "• After Effects extension features brought to Discord\n"
                "• Clone of The Precut Script, now as a bot\n"
                "• Slash commands for listing and downloading AE tools\n"
                "• Easy to use and setup"
            ),
            inline=False,
        )
        embed.add_field(name="Developer", value="moongetsu", inline=True)
        embed.add_field(name="Version", value="0.1 (DEV)", inline=True)
        embed.add_field(
            name="Status",
            value="🛠️ In development, not released yet. Features and behavior may change.",
            inline=False,
        )
        if self.BOT_LOGO:
            embed.set_footer(text="© TPS Bot (2026) | Information", icon_url=self.BOT_LOGO)
        else:
            embed.set_footer(text="© TPS Bot (2026) | Information")
        embed.set_author(name="TPS Bot", icon_url=self.BOT_LOGO)
        return embed

    @app_commands.command(name="info", description="Shows information about TPS Bot")
    async def info(self, interaction: discord.Interaction):
        embed = self.create_info_embed()
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(InfoCog(bot))
