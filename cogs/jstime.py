import asyncio
import logging
import traceback
from datetime import datetime

from discord.ext import commands, tasks
from discord import Game as GamePresence


class JSTimePresence(commands.Cog):
    def __init__(self, bot):
        self.bot: commands.Bot = bot
        self.last_known = None
        self.logger: logging.Logger = logging.getLogger("cogs.jstime")
        self.on_hold = False

        self.jstime_main.start()

    def cog_unload(self):
        self.jstime_main.cancel()

    @tasks.loop(seconds=1.0)
    async def jstime_main(self):
        while True:
            if not self.on_hold:
                self.on_hold = True
                break
            await asyncio.sleep(0.1)
        current_time = datetime.now(self.bot.jst_tz).strftime(
            "%d %b - %H:%M JST"
        )

        try:
            if self.last_known is None:
                self.last_known = current_time
            if self.last_known != current_time:
                self.last_known = current_time
                self.logger.info(
                    f"[JSTime] Updating clock: {current_time}"
                )
                ct_act = GamePresence(
                    name=current_time, type=3
                )
                await self.bot.change_presence(activity=ct_act)
            self.on_hold = False
        except Exception as e:
            tb = traceback.format_exception(
                type(e), e, e.__traceback__
            )
            self.logger.error("[JSTime] Error occured.")
            self.logger.error("[JSTime] {}".format("".join(tb)))
            self.on_hold = False


def setup(bot: commands.Bot):
    bot.add_cog(JSTimePresence(bot))
