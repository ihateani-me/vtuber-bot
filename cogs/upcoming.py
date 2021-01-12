import asyncio
import logging
import traceback
from datetime import datetime, timezone
import typing as t

import discord
from discord import TextChannel
from discord.ext import commands, tasks

from vtutils.bot import VTuberBot


OTHERVTUBER_LIST = """[https://api.ihateani.me/v2/vtuber](https://api.ihateani.me/v2/vtuber)"""

HOLOPRO_LIST = """- Hololive
- Hololive ID
- Hololive EN
- Holostars
"""

NIJISANJI_LIST = """- Nijisanji
- Nijisanji ID
- Nijisanji KR
- Nijisanji IN
"""


def setup(bot: VTuberBot):
    bot.add_cog(UpcomingWatcher(bot))


class UpcomingWatcher(commands.Cog):

    def __init__(self, bot: VTuberBot):
        self.bot = bot
        self.conf = bot.botconf
        self.ihaapi = bot.ihaapiv2
        self.jst: timezone = bot.jst_tz

        self.channels_set: t.Dict[str, TextChannel] = {
            "hololive": self.bot.get_channel(self.conf["channels"]["holo"]),
            "nijisanji": self.bot.get_channel(self.conf["channels"]["niji"]),
            "other": self.bot.get_channel(self.conf["channels"]["other"])
        }
        self.upcoming_message_set = bot.upcoming_message

        self.messages_logo = {
            "hololive": "https://user-images.strikinglycdn.com/res/hrscywv4p/image/upload/h_192,w_192,q_auto/1369026/logo_square_qn4ncy.png",  # noqa: E501
            "nijisanji": "https://nijisanji.ichikara.co.jp/wp-content/uploads/2018/12/cropped-Nijisanji_Rogo_icon_eye_RGB-192x192.png",  # noqa: E501
            "other": "https://s.ytimg.com/yts/img/favicon_144-vfliLAfaB.png"  # noqa: E501
        }
        self.logger: logging.Logger = logging.getLogger("cogs.upcoming")

        # Tasks
        self.improved_upcoming_watcher.start()

    def cog_unload(self):
        self.improved_upcoming_watcher.cancel()

    def _truncate_fields(self, dataset: list, limit: int = 1024):
        final_text = ""
        for data in dataset:
            add_text = data + "\n"
            length_now = len(final_text) + len(add_text)
            if length_now >= limit:
                break
            final_text += add_text
        return final_text

    async def design_youtube(self, dataset: list):
        collected_yt = []
        current_time = datetime.now(timezone.utc).timestamp()
        for yt in dataset:
            start_time = yt["timeData"]["startTime"]
            if isinstance(start_time, str):
                start_time = int(start_time)
            late_max = start_time + (5 * 60)
            if yt["platform"] != "youtube":
                continue
            lower_title = yt["title"].lower()
            if "freechat" in lower_title or "free chat" in lower_title:
                continue
            msg_design = ""
            strf = datetime.fromtimestamp(
                start_time + (9 * 60 * 60), tz=timezone.utc
            ).strftime("%m/%d %H:%M JST")
            msg_design += f"`{strf}` "
            if yt.get("is_member", False):
                msg_design += "🔒 "
            if yt.get("is_premiere", False):
                msg_design += "▶ "
            channel_data = yt["channel"]
            channel_name = channel_data.get(
                "en_name", channel_data.get("name", "Unknown"))
            msg_design += f"- [{channel_name}]"
            # https://youtu.be/nvTQ4TEPnsk
            msg_design += f"(https://youtu.be/{yt['id']})"
            if current_time > late_max:
                msg_design = "❓ " + msg_design
            collected_yt.append({"t": msg_design, "st": start_time})
        if collected_yt:
            collected_yt.sort(key=lambda x: x["st"])
        return collected_yt

    async def design_bilibili(self, dataset: list):
        collected_bili = []
        for bili in dataset:
            start_time = bili["timeData"]["startTime"]
            if isinstance(start_time, str):
                start_time = int(start_time)
            msg_design = ""
            strf = datetime.fromtimestamp(
                start_time + (9 * 60 * 60), tz=timezone.utc
            ).strftime("%m/%d %H:%M JST")
            msg_design += f"`{strf}` "
            channel_data = bili["channel"]
            channel_name = channel_data.get(
                "en_name", channel_data.get("name", "Unknown"))
            msg_design += f"- [{channel_name}]"
            msg_design += f"- [{channel_name}]"
            # https://live.bilibili.com/21908196
            msg_design += "(https://live.bilibili.com/"
            msg_design += f"{bili['room_id']})"
            collected_bili.append({"t": msg_design, "st": start_time})
        if collected_bili:
            collected_bili.sort(key=lambda x: x["st"])
        return collected_bili

    async def collect_and_map_messages(self) -> t.Dict[str, discord.Message]:
        holomessages: discord.Message = await self.channels_set["hololive"].fetch_message(
            self.upcoming_message_set["hololive"]
        )
        nijimessages: discord.Message = await self.channels_set["nijisanji"].fetch_message(
            self.upcoming_message_set["nijisanji"]
        )
        othermessages: discord.Message = await self.channels_set["other"].fetch_message(
            self.upcoming_message_set["other"]
        )
        return {
            "hololive": holomessages,
            "nijisanji": nijimessages,
            "other": othermessages
        }

    def is_nijisanji(self, group_name):
        groups_set = [
            "nijisanji",
            "nijisanjijp",
            "nijisanjikr",
            "nijisanjiid",
            "nijisanjien",
            "nijisanjiin",
            "virtuareal"
        ]
        if group_name in groups_set:
            return True
        return False

    def is_holopro(self, group_name):
        groups_set = ["hololive", "hololiveid", "hololivecn",
                      "hololiveen", "hololivejp", "holostars"]
        if group_name in groups_set:
            return True
        return False

    async def _split_results_into_group(self, results_items):
        streams_data = {
            "hololive": [],
            "nijisanji": [],
            "other": []
        }
        for result in results_items:
            if result["group"] in self.bot.ignore_lists:
                continue
            if result["platform"] == "bilibili":
                if result["group"] not in ["hololive", "nijisanji", "hololivecn", "virtuareal"]:
                    continue
            if self.is_nijisanji(result["group"]):
                streams_data["nijisanji"].append(result)
            elif self.is_holopro(result["group"]):
                streams_data["hololive"].append(result)
            else:
                streams_data["other"].append(result)
        return streams_data

    async def update_message_data(self, message: discord.Message, upcoming_data: list, group: str):
        self.logger.info(f"[Upcoming:{group}] Mapping data...")
        group_set = {
            "hololive": HOLOPRO_LIST,
            "nijisanji": NIJISANJI_LIST,
            "other": OTHERVTUBER_LIST
        }
        youtube_dataset = [
            stream for stream in upcoming_data if stream["platform"] == "youtube"]
        bilibili_dataset = []
        if group != "other":
            bilibili_dataset = [
                stream for stream in upcoming_data if stream["platform"] == "bilibili"]
        youtube_formatted = await self.design_youtube(youtube_dataset)
        bilibili_formatted = await self.design_bilibili(bilibili_dataset)

        youtube_formatted = [m["t"] for m in youtube_formatted]
        bilibili_formatted = [m["t"] for m in bilibili_formatted]
        self.logger.info(f"[Upcoming:{group}] Generating new embed...")
        embed = discord.Embed(timestamp=datetime.now(tz=self.jst))
        embed.add_field(
            name="Channel",
            value=group_set.get(group, "Unknown"),
        )
        embed.add_field(
            name="Info Icon",
            value="▶ Premiere\n🔒 Member-only\n❓ Late (5 minutes threshold)"
        )
        if youtube_formatted:
            embed.add_field(
                name="Upcoming! (YouTube)",
                value=self._truncate_fields(youtube_formatted),
                inline=False,
            )
        if bilibili_formatted:
            embed.add_field(
                name="Upcoming! (BiliBili)",
                value=self._truncate_fields(bilibili_formatted),
                inline=False,
            )
        embed.set_thumbnail(
            url=self.messages_logo.get(
                group, "https://s.ytimg.com/yts/img/favicon_144-vfliLAfaB.png")
        )
        embed.set_footer(text="Infobox v1.3 | Updated")

        self.logger.info(f"[Upcoming:{group}] Updating message....")
        try:
            await message.edit(embed=embed)
        except Exception as e:
            tb = traceback.format_exception(type(e), e, e.__traceback__)
            self.logger.error("".join(tb))
        self.logger.info(f"[Upcoming:{group}] Message updated!")

    @tasks.loop(minutes=3.0)
    async def improved_upcoming_watcher(self):
        try:
            if (
                self.upcoming_message_set["hololive"] is None
                and self.upcoming_message_set["nijisanji"] is None
                and self.upcoming_message_set["other"] is None
            ):
                self.logger.warn(
                    "[Upcoming] There's no placeholder message, ignoring"
                )
                return
            self.logger.info("[Upcoming] Collecting messages...")
            collected_messages = await self.collect_and_map_messages()

            current_upcoming_all = []
            self.logger.info(
                "[Upcoming] Fetching ihateani.me API upcoming streams...")
            try:
                current_upcoming_ihaapi = await self.ihaapi.fetch_upcoming()
                current_upcoming_all.extend(current_upcoming_ihaapi)
            except ValueError:
                self.logger.error(
                    "[Upcoming] Received ihaapi data are incomplete, cancelling...")
                return
            except asyncio.TimeoutError:
                self.logger.error(
                    "[Upcoming] Timeout error while fetching ihaapi data, cancelling...")
                return

            self.logger.info("[Upcoming] Mapping results...")
            mapped_upcoming_data = await self._split_results_into_group(current_upcoming_all)
            self.logger.info(
                "[Upcoming] Starting upcoming update processing..."
            )
            if self.upcoming_message_set["hololive"] is not None:
                await self.update_message_data(
                    collected_messages["hololive"], mapped_upcoming_data["hololive"], "hololive"
                )
            if self.upcoming_message_set["nijisanji"] is not None:
                await self.update_message_data(
                    collected_messages["nijisanji"], mapped_upcoming_data["nijisanji"], "nijisanji"
                )
            if self.upcoming_message_set["other"] is not None:
                await self.update_message_data(
                    collected_messages["other"], mapped_upcoming_data["other"], "other"
                )
            self.logger.info("[Upcoming] Now sleeping...")
        except Exception as e:
            tb = traceback.format_exception(type(e), e, e.__traceback__)
            self.logger.error("".join(tb))
