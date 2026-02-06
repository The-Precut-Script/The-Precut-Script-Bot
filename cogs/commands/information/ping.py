import time
import platform
import discord
from discord import app_commands
from discord.ext import commands

from cogs.utils.setup_message import build_text_container

try:
    import psutil
except ImportError:
    psutil = None


class PingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.BOT_LOGO = getattr(bot, "BOT_LOGO", None)

    def get_latency_color(self, latency):
        if latency < 50:
            return 0x00FF00
        if latency < 100:
            return 0xFFFF00
        if latency < 200:
            return 0xFFA500
        return 0xFF0000

    def get_latency_status(self, latency):
        if latency < 50:
            return "🟢 Excellent"
        if latency < 100:
            return "🟡 Good"
        if latency < 200:
            return "🟠 Fair"
        return "🔴 Poor"

    @app_commands.command(name="ping", description="Check bot latency and response time.")
    async def ping(self, interaction: discord.Interaction):
        start_time = time.time()
        bot_latency = round((self.bot.latency or 0) * 1000, 2)
        await interaction.response.defer()
        api_latency = round((time.time() - start_time) * 1000, 2)
        status = self.get_latency_status(bot_latency)

        body_lines = [
            "**🏓 Pong!**",
            "",
            "**📡 Bot Latency:** `{}ms`".format(bot_latency),
            "**⚡ API Latency:** `{}ms`".format(api_latency),
            "**📊 Status:** {}".format(status),
        ]
        if psutil:
            cpu = psutil.cpu_percent()
            mem = psutil.virtual_memory()
            body_lines.append("**🖥️ System:** CPU: {}% | RAM: {}%".format(cpu, mem.percent))
        body_lines.append(
            "**🤖 Bot:** Python {} | discord.py {} | Servers: {}".format(
                platform.python_version(), discord.__version__, len(self.bot.guilds)
            )
        )
        body = "\n".join(body_lines)
        footer = "© TPS Bot (2026) | Ping"
        view, _ = build_text_container(body, footer_text=footer)
        if view is not None:
            await interaction.edit_original_response(content=None, view=view)
        else:
            color = self.get_latency_color(bot_latency)
            embed = discord.Embed(
                title="🏓 Pong!",
                description="Latency and status:",
                color=color,
            )
            embed.add_field(name="📡 Bot Latency", value="`{}ms`".format(bot_latency), inline=True)
            embed.add_field(name="⚡ API Latency", value="`{}ms`".format(api_latency), inline=True)
            embed.add_field(name="📊 Status", value=status, inline=True)
            if psutil:
                cpu = psutil.cpu_percent()
                mem = psutil.virtual_memory()
                embed.add_field(
                    name="🖥️ System",
                    value="CPU: {}% | RAM: {}%".format(cpu, mem.percent),
                    inline=False,
                )
            embed.add_field(
                name="🤖 Bot",
                value="Python {} | discord.py {} | Servers: {}".format(
                    platform.python_version(), discord.__version__, len(self.bot.guilds)
                ),
                inline=False,
            )
            embed.set_footer(text=footer, icon_url=self.BOT_LOGO)
            await interaction.edit_original_response(content=None, embed=embed)


async def setup(bot):
    await bot.add_cog(PingCog(bot))
