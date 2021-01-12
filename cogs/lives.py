import asyncio
import logging
import traceback
import typing as t
from datetime import datetime, timezone

import discord
from discord.channel import TextChannel
from discord.ext import commands, tasks

from vtutils.bot import VTuberBot


def setup(bot: VTuberBot):
    bot.add_cog(LiveWatcher(bot))


class LiveWatcher(commands.Cog):
    def __init__(self, bot: VTuberBot):
        self.bot: commands.Bot = bot
        self.conf = bot.botconf
        self.ihaapi = bot.ihaapiv2
        channels_data: t.Dict[str, t.Union[str, int, None]] = self.conf
        self.channels_set: t.Dict[str, TextChannel] = {
            "hololive": self.bot.get_channel(channels_data["holo"]) if channels_data["holo"] is not None else None,  # noqa: E501
            "nijisanji": self.bot.get_channel(channels_data["niji"]) if channels_data["niji"] is not None else None,  # noqa: E501
            "other": self.bot.get_channel(channels_data["other"]) if channels_data["other"] is not None else None  # noqa: E501
        }
        self.upcoming_message_set = {
            "hololive": -1 if bot.upcoming_message["hololive"] is None else bot.upcoming_message["hololive"],
            "nijisanji": -1 if bot.upcoming_message["nijisanji"] is None else bot.upcoming_message["nijisanji"],  # noqa: E501
            "other": -1 if bot.upcoming_message["other"] is None else bot.upcoming_message["other"]
        }
        self.logger: logging.Logger = logging.getLogger("cogs.lives")

        self._korone_img = "idle"
        self._korone_data = bot.korone_img
        self.enable_twitch = True
        self.enable_twitcasting = True
        self.total_streams_map = {
            "hololive": -1,
            "nijisanji": -1,
            "other": -1
        }

        # Tasks
        self.improved_live_watcher.start()

    def cog_unload(self):
        self.improved_live_watcher.cancel()

    async def create_embed(self, live_data: dict, web_type="youtube"):
        color_web = {
            "youtube": {
                "c": 0xFF0000,
                "b": "https://youtube.com/watch?v=",
                "cb": "https://youtube.com/channel/",
                "fi": "https://s.ytimg.com/yts/img/favicon_144-vfliLAfaB.png",
            },
            "bilibili": {
                "c": 0x23ADE5,
                "b": "https://live.bilibili.com/",
                "cb": "https://space.bilibili.com/",
                "fi": "https://logodix.com/logo/1224389.png",
            },
            "twitch": {
                "c": 0x9147ff,
                "b": "https://www.twitch.tv/",
                "cb": "https://twitch.tv/",
                "fi": "https://p.n4o.xyz/i/twitchlogo.png"
            },
            "twitcasting": {
                "c": 0x280fc,
                "b": "https://twitcasting.tv/",
                "cb": "https://twitcasting.tv/",
                "fi": "https://twitcasting.tv/img/icon192.png"
            }
        }

        web_data = color_web.get(web_type)
        web_col, web_base, channel_base, web_logo = (
            web_data["c"],
            web_data["b"],
            web_data["cb"],
            web_data["fi"],
        )
        channeru = live_data["channel"]
        if web_type == "youtube":
            stream_url = f"{web_base}{live_data['id']}"
        elif web_type == "bilibili":
            print(live_data)
            stream_url = f"{web_base}{live_data['room_id']}"
        elif web_type == "twitcasting":
            stream_url = f"{web_base}{live_data['channel']['id']}"
        elif web_type == "twitch":
            stream_url = f"{web_base}{live_data['channel']['id']}"
        channel_url = f"{channel_base}{channeru['id']}"
        start_time = datetime.fromtimestamp(
            live_data["timeData"]["startTime"], tz=timezone.utc
        )
        is_member = live_data.get("is_member", False)
        is_premiere = live_data.get("is_premiere", False)

        embed = discord.Embed(
            title=live_data["title"],
            colour=web_col,
            url=stream_url,
            description=f"[Watch Here!]({stream_url})",
            timestamp=start_time
        )

        embed.description += f"\n{web_type.capitalize()} "
        if is_premiere:
            embed.description += "Premiere"
            embed.description = "▶ " + embed.description
        else:
            embed.description += "Stream"
        if is_member:
            embed.description += " **(Member-Only)**"

        embed.set_image(url=live_data["thumbnail"])
        embed.set_thumbnail(url=channeru["image"])
        embed.set_author(
            name=channeru["name"],
            icon_url=channeru["image"],
            url=channel_url,
        )
        foot = live_data["id"]
        if web_type == "twitch":
            foot = "twitch" + foot
        elif web_type == "twitcasting":
            foot = "twcast" + foot
        embed.set_footer(text=foot, icon_url=web_logo)
        return embed

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
            if result["platform"] == "bilibili":
                if result["group"] not in ["hololive", "nijisanji", "hololivecn", "virtuareal"]:
                    continue
            if not self.enable_twitcasting and result["platform"] == "twitcasting":
                continue
            if not self.enable_twitch and result["platform"] == "twitch":
                continue
            if self.is_nijisanji(result["group"]):
                streams_data["nijisanji"].append(result)
            elif self.is_holopro(result["group"]):
                streams_data["hololive"].append(result)
            else:
                streams_data["other"].append(result)
        return streams_data

    async def find_msg(
        self, message_list: list, video_id: str
    ) -> discord.Message:
        for msg in message_list:
            if video_id == msg["id"]:
                return msg["msg_data"]

    async def find_live_info(self, live_data: list, video_id: str) -> dict:
        for live in live_data:
            if live["id"] == video_id:
                return live

    async def filter_message(
        self, message_set: t.List[discord.Message], tipe: str
    ) -> t.List[discord.Message]:
        # Filter out user message
        message_set = [msg for msg in message_set if msg.author.bot]
        message_set = [
            msg for msg in message_set if msg.id != self.upcoming_message_set[tipe]
        ]  # Filter out upcoming message
        return message_set

    async def collect_and_map_messages(self):
        holomessages: t.List[discord.Message] = await self.channels_set["hololive"].history(
            limit=None
        ).flatten()
        nijimessages: t.List[discord.Message] = await self.channels_set["nijisanji"].history(
            limit=None
        ).flatten()
        othermessages: t.List[discord.Message] = await self.channels_set["other"].history(
            limit=None
        ).flatten()
        return {
            "hololive": await self.filter_message(holomessages, "hololive"),
            "nijisanji": await self.filter_message(nijimessages, "nijisanji"),
            "other": await self.filter_message(othermessages, "other")
        }

    async def update_korone_profile_image(self, channels_lives_yt):
        if (
            "UChAnqc_AY5_I3Px5dig3X1Q" in channels_lives_yt
            and self._korone_img == "idle"  # noqa: W503
        ):
            self.logger.info(
                "[Live] Changing Profile Picture to Korone LIVE image..."
            )
            self._korone_img = "live"
            await self.bot.user.edit(avatar=self._korone_data["live"])
        elif (
            "UChAnqc_AY5_I3Px5dig3X1Q" not in channels_lives_yt
            and self._korone_img == "live"  # noqa: W503
        ):
            self.logger.info(
                "[Live] Changing Profile Picture to Korone IDLE image..."
            )
            self._korone_img = "idle"
            await self.bot.user.edit(avatar=self._korone_data["idle"])

    async def do_and_post_live_data(
        self, collected_messages: t.List[discord.Message], current_lives_data: t.List[dict], group: str
    ):
        self.logger.info(f"[Live:{group}] Mapping everything...")
        collected_msgs_yt = []
        collected_msgs_b2 = []
        collected_msgs_ttv = []
        collected_msgs_twcast = []
        if collected_messages:
            for msg in collected_messages:
                embed_data = msg.embeds
                if not embed_data:
                    continue
                embed_data: discord.Embed = embed_data[0]
                embed_dict = embed_data.to_dict()
                watch_id = embed_dict["footer"]["text"]

                if watch_id.startswith("bili"):
                    collected_msgs_b2.append(
                        {"id": watch_id, "msg_data": msg}
                    )
                elif watch_id.startswith("twitch"):
                    collected_msgs_ttv.append(
                        {"id": watch_id, "msg_data": msg}
                    )
                elif watch_id.startswith("twcast"):
                    collected_msgs_twcast.append(
                        {"id": watch_id, "msg_data": msg}
                    )
                else:
                    collected_msgs_yt.append(
                        {"id": watch_id, "msg_data": msg}
                    )

        if self.total_streams_map[group] == -1:
            # Avoid renaming.
            self.total_streams_map[group] = len(collected_messages)

        current_lives_yt = [
            c for c in current_lives_data if c["platform"] == "youtube"]
        current_lives_bili = [
            c for c in current_lives_data if c["platform"] == "bilibili"]
        current_lives_ttv = [
            c for c in current_lives_data if c["platform"] == "twitch"]
        current_lives_twcast = [
            c for c in current_lives_data if c["platform"] == "twitcasting"]

        collected_ytmsg_ids = [c["id"] for c in collected_msgs_yt]
        channels_lives_yt = [c["channel"]["id"] for c in current_lives_yt]
        collected_lives_ytids = [c["id"] for c in current_lives_yt]

        if group == "hololive":
            await self.update_korone_profile_image(channels_lives_yt)

        collected_bilimsg_ids = [c["id"] for c in collected_msgs_b2]
        collected_lives_biliids = [c["id"] for c in current_lives_bili]

        collected_ttvmsg_ids = [c["id"] for c in collected_msgs_ttv]
        collected_lives_ttvids = [
            "twitch" + c["id"] for c in current_lives_ttv
        ]

        collected_twcastmsg_ids = [c["id"] for c in collected_msgs_twcast]
        collected_lives_twcastids = [
            "twcast" + c["id"] for c in current_lives_twcast
        ]

        self.logger.info(f"[Live:{group}] Collecting everything...")
        collective_msg_merge = []
        collective_msg_merge.extend(collected_msgs_yt)
        collective_msg_merge.extend(collected_msgs_b2)
        collective_msg_merge.extend(collected_msgs_ttv)
        collective_msg_merge.extend(collected_msgs_twcast)

        need_to_be_posted = []
        need_to_be_deleted = []
        for live_id in current_lives_yt:
            if live_id["id"] not in collected_ytmsg_ids:
                need_to_be_posted.append(live_id["id"])
        for live_id in collected_lives_biliids:
            if live_id not in collected_bilimsg_ids:
                need_to_be_posted.append(live_id)
        for live_id in collected_lives_ttvids:
            if live_id not in collected_ttvmsg_ids:
                need_to_be_posted.append(live_id)
        for live_id in collected_lives_twcastids:
            if live_id not in collected_twcastmsg_ids:
                need_to_be_posted.append(live_id)

        for msg_id in collected_ytmsg_ids:
            if msg_id not in collected_lives_ytids:
                need_to_be_deleted.append(msg_id)
        for msg_id in collected_bilimsg_ids:
            if msg_id not in collected_lives_biliids:
                need_to_be_deleted.append(msg_id)
        for msg_id in collected_ttvmsg_ids:
            if msg_id not in collected_lives_ttvids:
                need_to_be_deleted.append(msg_id)
        for msg_id in collected_twcastmsg_ids:
            if msg_id not in collected_lives_twcastids:
                need_to_be_deleted.append(msg_id)

        # Let's delete everything first!
        self.logger.info(f"[Live:{group}] Starting deletion process...")
        for stream in need_to_be_deleted:
            self.logger.warn(
                f"[Live:{group}]: Deleting {stream} from channel...")
            msg_data: discord.Message = await self.find_msg(collective_msg_merge, stream)
            try:
                await msg_data.delete()
            except Exception:
                self.logger.error(
                    f"[Live:{group}] Failed to delete {stream}, possibly gone.")

        self.logger.info(f"[Live:{group}] Starting posting process...")
        for new_live in need_to_be_posted:
            self.logger.warn(f"[Live:{group}] Posting {new_live}...")
            if new_live.startswith("twitch") or new_live.startswith("twcast"):
                new_live = new_live[6:]
            live_data = await self.find_live_info(current_lives_data, new_live)
            embed_info = await self.create_embed(live_data, live_data["platform"])
            if not isinstance(embed_info, discord.Embed):
                self.logger.warn(
                    f"[Live:{group}] Skipping {new_live} since it's YouTube rebroadcast."
                )
                continue
            await self.channels_set[group].send(content="Currently Live!", embed=embed_info)

    async def try_to_rename_channel(self, dataset: list, group: str):
        channel_prefix = {
            "hololive": "holo-",
            "nijisanji": "nijisanji-",
            "other": "others-"
        }
        if len(dataset) != self.total_streams_map[group]:
            self.total_streams_map[group] = len(dataset)
            self.logger.info(f"[Live:{group}] Renaming channel...")

            BASE_TEXT = channel_prefix.get(group, "unknown-")
            if len(dataset) > 0:
                BASE_TEXT += f"{len(dataset)}-live-now"
                BASE_TEXT = "🔴-" + BASE_TEXT
            else:
                BASE_TEXT += "live"
            await self.channels_set[group].edit(
                name=BASE_TEXT, reason="Change to amount of channels live."
            )

    @tasks.loop(minutes=1.0)
    async def improved_live_watcher(self):
        try:
            if (
                self.channels_set["hololive"] is None
                and self.channels_set["nijisanji"] is None
                and self.channels_set["other"] is None
            ):
                self.logger.warn(
                    "[Live] There's no channel, ignoring"
                )
                return
            self.logger.info("[Live] Collecting messages...")
            collected_messages = await self.collect_and_map_messages()

            current_lives_all = []
            self.logger.info("[Live] Fetching ihateani.me API streams...")
            try:
                current_lives_ihaapi = await self.ihaapi.fetch_lives()
                current_lives_all.extend(current_lives_ihaapi)
            except ValueError:
                self.logger.error(
                    "[Live] Received ihaapi data are incomplete, cancelling...")
                return
            except asyncio.TimeoutError:
                self.logger.error(
                    "[Live] Timeout error while fetching ihaapi data, cancelling...")
                return

            self.logger.info("[Live] Mapping results...")
            mapped_lives_data = await self._split_results_into_group(current_lives_all)
            self.logger.info("[Live] Starting live update processing...")
            await self.do_and_post_live_data(
                collected_messages["hololive"], mapped_lives_data["hololive"], "hololive"
            )
            await self.do_and_post_live_data(
                collected_messages["nijisanji"], mapped_lives_data["nijisanji"], "nijisanji"
            )
            await self.do_and_post_live_data(
                collected_messages["other"], mapped_lives_data["other"], "other"
            )

            self.logger.info("[Live] Finalizing...")
            if self.channels_set["hololive"] is not None:
                await self.try_to_rename_channel(mapped_lives_data["hololive"], "hololive")
            if self.channels_set["nijisanji"] is not None:
                await self.try_to_rename_channel(mapped_lives_data["nijisanji"], "nijisanji")
            if self.channels_set["other"] is not None:
                await self.try_to_rename_channel(mapped_lives_data["other"], "other")
            self.logger.info("[Live] Sleeping...")
        except Exception as e:
            tb = traceback.format_exception(type(e), e, e.__traceback__)
            self.logger.error("".join(tb))
