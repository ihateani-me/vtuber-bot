import discord
import typing as t
from discord.ext import commands
from datetime import timezone
from .ihateanime import ihateanimeAPIV2
import logging


class VTuberBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.logger: logging.Logger = logging.getLogger("VTuberBot")
        self.botconf: dict
        self.upcoming_message: t.Dict[str, int]

        self.korone_img: t.Dict[str, bytes]
        self.ignore_lists: t.List[str]

        self.jst_tz: timezone

        self.uptime: float
        self.owner: t.Union[discord.User, discord.TeamMember]

        self.ihaapiv2: ihateanimeAPIV2
