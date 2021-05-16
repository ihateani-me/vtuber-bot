import asyncio
import re
import logging
import traceback
from datetime import datetime, timezone
import typing as t

import discord
from discord import TextChannel
from discord.ext import commands, tasks

from vtutils.bot import VTuberBot


def setup(bot: VTuberBot):
    bot.add_cog(UpcomingWatcher(bot))


class UpcomingWatcher(commands.Cog):

    def __init__(self, bot: VTuberBot):
        self.bot = bot
        self.conf = bot.botconf
        self.ihaapi = bot.ihaapiv2
        self.jst: timezone = bot.jst_tz
        self.LATE = (5 * 60)
        self.LATE_TOLERANCE = (12 * 60)

        self.channels_set: t.Dict[str, TextChannel] = {
            "hololive": self.bot.get_channel(self.conf["channels"]["holo"]),
            "nijisanji": self.bot.get_channel(self.conf["channels"]["niji"]),
            "other": self.bot.get_channel(self.conf["channels"]["other"])
        }
        self.upcoming_message_set = bot.upcoming_message

        self.messages_logo = {
            "hololive": "https://user-images.strikinglycdn.com/res/hrscywv4p/image/upload/h_192,w_192,q_auto/1369026/logo_square_qn4ncy.png",  # noqa: E501
            "nijisanji": "https://www.nijisanji.jp/favicon/apple-touch-icon.png",  # noqa: E501
            "other": "https://s.ytimg.com/yts/img/favicon_144-vfliLAfaB.png"  # noqa: E501
        }
        self._fcre = re.compile(r"(fr[e]{2}).*(chat)", re.I)
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

    def is_freechat(self, title: str) -> bool:
        match = re.match(self._fcre, title)
        if match is None:
            return False
        return True

    async def design_scheduled(self, dataset: list):
        grouped_time = {}
        current_time = datetime.now(timezone.utc).timestamp()

        for data in dataset:
            start_time = data["timeData"].get(
                "scheduledStartTime", data["timeData"].get("startTime")
            )
            if start_time is None:
                continue
            start_time = int(round(start_time))
            if self.is_freechat(data["title"]):
                # Skip free chat room
                continue
            if current_time >= start_time + self.LATE_TOLERANCE:
                # Too long
                continue
            formatted_time = datetime.fromtimestamp(
                start_time + (9 * 60 * 60), tz=timezone.utc
            ).strftime("%m/%d %H:%M JST")
            if formatted_time not in grouped_time:
                grouped_time[formatted_time] = []
            grouped_time[formatted_time].append(data)

        MAX_LENGTH = 2048
        formatted_schedule = ""
        LINK_FORMAT = {
            "youtube": "https://youtu.be/",
            "twitch": "https://twitch.tv/",
            "twitcasting": "https://twitcasting.tv/",
            "mildom": "https://mildom.com/"
        }
        ICONS_MAP_FORMAT = {
            "youtube": "<:vtBYT:843473930348920832>",
            "twitch": "<:vtBTTV:843474008984518687>",
            "twitcasting": "<:vtBTW:843473977484509184>",
            "mildom": "<:vtBMD:843474000159965226>",
            "bilibili": "<:vtBB2:843474401310670848>"
        }
        should_break = False
        for start_time, dataset in grouped_time.items():
            temp = f"{formatted_schedule}**{start_time}**\n"
            if len(temp) >= MAX_LENGTH:
                break
            if len(dataset) < 1:
                continue
            formatted_schedule = temp
            for data in dataset:
                start_time = data["timeData"].get(
                    "scheduledStartTime", data["timeData"].get("startTime")
                )
                msg_fmt = ""
                if data.get("is_member", False):
                    msg_fmt += "🔒 "
                if data.get("is_premiere", False):
                    msg_fmt += "▶ "
                if current_time > start_time + self.LATE:
                    msg_fmt += "❓ "
                channel_data = data["channel"]
                channel_name = channel_data.get(
                    "en_name", channel_data.get(
                        "name", "Unknown"
                    )
                )
                LINK_PREFIX = LINK_FORMAT.get(data["platform"])
                ICON_PREFIX = ICONS_MAP_FORMAT.get(data["platform"], "")
                if self.bot.user.id == 714518710924345475:
                    # Add icon prefix if it's my deployed bot
                    msg_fmt += f"{ICON_PREFIX} "
                msg_fmt += f"**`{channel_name}`**"
                msg_fmt += f" - [{data['title']}]({LINK_PREFIX}{data['id']})\n"
                temp = formatted_schedule + msg_fmt
                if len(temp) >= MAX_LENGTH:
                    should_break = True
                    break
                formatted_schedule = temp
            if should_break:
                break
            temp = formatted_schedule + "\n"
            if len(temp) >= MAX_LENGTH:
                break
            formatted_schedule = temp
        formatted_schedule = formatted_schedule.rstrip("\n")
        return formatted_schedule

    async def collect_and_map_messages(self) -> t.Dict[str, discord.Message]:
        holomessages = nijimessages = othermessages = None
        if self.channels_set["hololive"] is not None and self.upcoming_message_set["hololive"] is not None:
            holomessages: discord.Message = await self.channels_set["hololive"].fetch_message(
                self.upcoming_message_set["hololive"]
            )
        if self.channels_set["nijisanji"] is not None and self.upcoming_message_set["nijisanji"] is not None:
            nijimessages: discord.Message = await self.channels_set["nijisanji"].fetch_message(
                self.upcoming_message_set["nijisanji"]
            )
        if self.channels_set["other"] is not None and self.upcoming_message_set["other"] is not None:
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
        schedule_formatted = await self.design_scheduled(upcoming_data)

        self.logger.info(f"[Upcoming:{group}] Generating new embed...")
        embed = discord.Embed(title="Upcoming Stream", timestamp=datetime.now(tz=self.jst))
        if schedule_formatted:
            embed.description = schedule_formatted
        else:
            embed.description = "No scheduled stream!"
        embed.add_field(
            name="More Informtion",
            value=f"▶ Premiere\n🔒 Member-only\n❓ Late ({self.LATE // 60} minutes threshold)\n\n"
            "Powered by [ihateani.me API](https://vtuber.ihateani.me/schedules)"
        )
        embed.set_thumbnail(
            url=self.messages_logo.get(
                group, "https://s.ytimg.com/yts/img/favicon_144-vfliLAfaB.png"
            )
        )
        embed.set_footer(text="Infobox v1.4 | Updated")

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
