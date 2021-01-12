# -*- coding: utf-8 -*-

import asyncio
import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone

import aiohttp
import discord
from discord.ext import commands

from vtutils import ihateanimeAPIV2, VTuberBot

# Silent some imported module
logging.getLogger("websockets").setLevel(logging.WARNING)

cogs_list = [
    "cogs." + x.replace(".py", "")
    for x in os.listdir("cogs")
    if x.endswith(".py")
]

logger = logging.getLogger()
logging.basicConfig(
    level=logging.DEBUG,
    handlers=[logging.FileHandler("vtuber_bot.log", "w", "utf-8")],
    format="[%(asctime)s] - (%(name)s)[%(levelname)s](%(funcName)s): %(message)s",  # noqa: E501
    datefmt="%Y-%m-%d %H:%M:%S",
)

console = logging.StreamHandler(sys.stdout)
console.setLevel(logging.INFO)
console_formatter = logging.Formatter(
    "[%(levelname)s] (%(name)s): %(funcName)s: %(message)s"
)
console.setFormatter(console_formatter)
logger.addHandler(console)


def prefixes(bot, message):
    """
    A modified version of discord.ext.command.when_mentioned_or
    """
    pre_data = ["vt.", "vt!", "vt>"]
    pre_data = [bot.user.mention + " ", "<@!%s> " % bot.user.id] + pre_data

    return pre_data


async def init_bot():
    """
    Start loading all the bot process
    Will start:
        - Logging
        - discord.py and the modules
        - Fetching naoTimes main database
        - Setting some global variable
    """
    logger.info("Looking up config")
    with open("config.json", "r") as fp:
        config = json.load(fp)

    logger.info("Loading korone/bot image...")
    with open("_korone_idle.png", "rb") as fp:
        korone_idle = fp.read()
    with open("_korone_live.png", "rb") as fp:
        korone_live = fp.read()

    try:
        logger.info("Initiating discord.py")
        description = (
            """A simple VTuber Bot\nversion 1.0.0 || Created by: N4O#8868"""
        )
        bot = VTuberBot(command_prefix=prefixes, description=description, intents=discord.Intents.all())
        bot.remove_command("help")
        bot.korone_img = {"idle": korone_idle, "live": korone_live}
        logger.info("Success Loading Discord.py")
    except Exception as exc:
        logger.error("Failed to load Discord.py ###")
        logger.error("\t" + str(exc))
    return (
        bot,
        config
    )


# Initiate everything
logger.info("Setting up loop")
async_loop = asyncio.get_event_loop()
init_results = async_loop.run_until_complete(
    init_bot()
)
bot: VTuberBot = init_results[0]
bot_config: dict = init_results[1]
logger.info("Initiating API class...")
if not hasattr(bot, "ihaapiv2"):
    bot.ihaapiv2 = ihateanimeAPIV2(async_loop)
if not hasattr(bot, "jst_tz"):
    bot.jst_tz = timezone(timedelta(hours=9))
if not hasattr(bot, "botconf"):
    bot.botconf = bot_config


@bot.event
async def on_ready():
    """Bot loaded here"""
    logger.info("[$] Connected to discord.")
    current_time_jst = datetime.now(tz=bot.jst_tz).strftime(
        "%d %b - %H:%M JST"
    )
    activity = discord.Game(name=current_time_jst, type=3)
    await bot.change_presence(activity=activity)
    logger.info(
        "---------------------------------------------------------------"
    )
    logger.info("Bot Ready!")
    logger.info("Using Python {}".format(sys.version))
    logger.info("And Using Discord.py v{}".format(discord.__version__))
    logger.info(
        "---------------------------------------------------------------"
    )
    logger.info("Logged in as:")
    logger.info("Bot name: {}".format(bot.user.name))
    logger.info("With Client ID: {}".format(bot.user.id))
    logger.info(
        "---------------------------------------------------------------"
    )
    if "message" in bot_config:
        bot.upcoming_message = bot_config["message"]
    else:
        bot.upcoming_message = {"hololive": None, "nijisanji": None, "other": None}
    bot.ignore_lists = bot_config["ignore"]["groups"]
    if not hasattr(bot, "uptime"):
        bot.owner = (await bot.application_info()).owner
        bot.uptime = time.time()
        logger.info("[#][@][!] Start loading cogs...")
        for load in cogs_list:
            try:
                logger.info("[#] Loading " + load + " module.")
                bot.load_extension(load)
                logger.info("[#] Loaded " + load + " module.")
            except Exception as e:
                tb = traceback.format_exception(type(e), e, e.__traceback__)
                logger.error("[!!] Failed Loading " + load + " module.")
                logger.error("".join(tb))
        logger.info("[#][@][!] All cogs/extensions loaded.")
        logger.info(
            "---------------------------------------------------------------"
        )
    logger.info("All bots module loaded, bot it's now very much ready!")


def create_uptime():
    current_time = time.time()
    up_secs = int(round(current_time - bot.uptime))  # Seconds

    up_months = int(up_secs // 2592000)  # 30 days format
    up_secs -= up_months * 2592000
    up_weeks = int(up_secs // 604800)
    up_secs -= up_weeks * 604800
    up_days = int(up_secs // 86400)
    up_secs -= up_days * 86400
    up_hours = int(up_secs // 3600)
    up_secs -= up_hours * 3600
    up_minutes = int(up_secs // 60)
    up_secs -= up_minutes * 60

    return_text = "`"
    if up_months != 0:
        return_text += "{} months ".format(up_months)

    return (
        return_text
        + "{} weeks {} days {} hours {} minutes {} seconds`".format(
            up_weeks, up_days, up_hours, up_minutes, up_secs
        )
    )


@bot.command()
@commands.is_owner()
async def set_profile(ctx, mode):
    """Force set the profile picture"""
    mm: dict = bot.korone_img
    img_set = mm.get(mode, "")
    if not img_set:
        return await ctx.send("unknown profile tag.")
    await bot.user.edit(avatar=img_set)
    await ctx.send("profile set!")


def maybe_int(number):
    if isinstance(number, int):
        return number
    try:
        return int(number)
    except ValueError:
        return number


@bot.command()
@commands.is_owner()
async def initialize(ctx):
    bot.logger.info("Initilizing channels!")
    channels: dict = bot.botconf["channels"]
    template_embed = discord.Embed(timestamp=datetime.now(tz=bot.jst_tz))
    template_embed.set_footer(text="Infobox v1.3")
    template_embed.add_field(name="To be added", value="*This is a placeholder*")
    await ctx.send("Initializing...")
    if channels["hololive"] is not None:
        holochan = bot.get_channel(maybe_int(channels["hololive"]))
        if holochan is None:
            await ctx.send("Failed to get Hololive channel")
        else:
            try:
                holomsg = await holochan.send(embed=template_embed)
                bot.upcoming_message["hololive"] = holomsg.id
            except Exception:
                await ctx.send("Failed to create placeholder message for Hololive channel")
    if channels["nijisanji"] is not None:
        nijichan = bot.get_channel(maybe_int(channels["nijisanji"]))
        if nijichan is None:
            await ctx.send("Failed to get Nijisanji channel")
        else:
            try:
                nijimsg = await nijichan.send(embed=template_embed)
                bot.upcoming_message["nijisanji"] = nijimsg.id
            except Exception:
                await ctx.send("Failed to create placeholder message for Nijisanji channel")
    if channels["other"] is not None:
        otherchan = bot.get_channel(maybe_int(channels["nijisanji"]))
        if otherchan is None:
            await ctx.send("Failed to get Other channel")
        else:
            try:
                othermsg = await otherchan.send(embed=template_embed)
                bot.upcoming_message["other"] = othermsg.id
            except Exception:
                await ctx.send("Failed to create placeholder message for Other channel")
    bot.botconf["message"] = bot.upcoming_message
    with open("config.json", "w") as fp:
        json.dump(bot.botconf, fp, indent=4)
    await ctx.send("Initialized!")


def ping_emote(t_t):
    if t_t < 50:
        emote = ":race_car:"
    elif t_t >= 50 and t_t < 200:
        emote = ":blue_car:"
    elif t_t >= 200 and t_t < 500:
        emote = ":racehorse:"
    elif t_t >= 200 and t_t < 500:
        emote = ":runner:"
    elif t_t >= 500 and t_t < 3500:
        emote = ":walking:"
    elif t_t >= 3500:
        emote = ":snail:"
    return emote


async def check_web_speed(url, session: aiohttp.ClientSession):
    logger.info(f"ping: checking {url}")
    t1_start = time.perf_counter()
    error = False
    try:
        async with session.get(url) as resp:
            await resp.text()
            t2_end = time.perf_counter()
    except aiohttp.ClientTimeout:
        logger.warn("Timeout!")
        t2_end = time.perf_counter()
        error = True
    return t2_end - t1_start, error


@bot.command()
async def ping(ctx):
    channel = ctx.message.channel
    irnd = lambda t: int(round(t * 1000))  # noqa: E731
    logger.info("ping: checking websocket...")
    ws_ping = bot.latency

    session = aiohttp.ClientSession(
        headers={
            "User-Agent": "Listeners/1.0 ListenersPingTools/0.1"
        }
    )
    try:
        iha_url = "https://api.ihateani.me/echo"
        iha_ping, iha_err = await check_web_speed(iha_url, session)
        await session.close()
    except Exception:
        await session.close()
        iha_ping = 9999
        iha_err = True

    iha_ping = irnd(iha_ping)

    t1_ping = time.perf_counter()
    async with channel.typing():
        t2_ping = time.perf_counter()

        dis_ping = irnd(t2_ping - t1_ping)

        text_res = ":satellite: Ping Results :satellite:"
        text_res += f"\n{ping_emote(dis_ping)} Discord: `{dis_ping}ms`"

        if ws_ping != float("nan"):
            ws_time = irnd(ws_ping)
            ws_res = f"{ping_emote(ws_time)} Websocket `{ws_time}ms`"
        else:
            ws_res = ":x: Websocket: `nan`"

        text_res += "\n"
        text_res += ws_res

        if not iha_err:
            text_res += f"\n{ping_emote(iha_ping)} "
        else:
            text_res += "\n:x: "
        text_res += f"api.ihateani.me: `{iha_ping}ms`"

        await channel.send(content=text_res)


@bot.command()
async def uptime(ctx):
    uptime = create_uptime()
    await ctx.send(f":alarm_clock: {uptime}")


# All of the code from here are mainly a copy of discord.Client.run()
# function, which have been readjusted to fit my needs.
async def run_bot(*args, **kwargs):
    try:
        await bot.start(*args, **kwargs)
    finally:
        await bot.close()


def stop_stuff_on_completion(_):
    async_loop.stop()


def cancel_all_tasks(loop):
    """A copy of discord.Client _cancel_tasks function

    :param loop: [description]
    :type loop: [type]
    """
    try:
        try:
            task_retriever = asyncio.Task.all_tasks
        except AttributeError:
            # future proofing for 3.9 I guess
            task_retriever = asyncio.all_tasks

        tasks = {t for t in task_retriever(loop=loop) if not t.done()}

        if not tasks:
            return

        bot.logger.info("Cleaning up after %d tasks.", len(tasks))
        for task in tasks:
            task.cancel()

        loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
        bot.logger.info("All tasks finished cancelling.")

        for task in tasks:
            if task.cancelled():
                continue
            if task.exception() is not None:
                loop.call_exception_handler(
                    {
                        "message": "Unhandled exception during Client.run shutdown.",
                        "exception": task.exception(),
                        "task": task,
                    }
                )
        if sys.version_info >= (3, 6):
            loop.run_until_complete(loop.shutdown_asyncgens())
    finally:
        bot.logger.info("Closing the event loop.")


future = asyncio.ensure_future(run_bot(bot.botconf["bot_token"], bot=True, reconnect=True))
future.add_done_callback(stop_stuff_on_completion)
try:
    async_loop.run_forever()
except (KeyboardInterrupt, SystemExit, SystemError):
    bot.logger.info("Received signal to terminate bot.")
finally:
    future.remove_done_callback(stop_stuff_on_completion)
    bot.logger.info("Cleaning up tasks.")
    cancel_all_tasks(async_loop)

if not future.cancelled():
    try:
        future.result()
    except KeyboardInterrupt:
        pass
