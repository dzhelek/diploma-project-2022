#!/usr/bin/python3
import os

from disnake.ext import commands
import dotenv

from views import HostsView, ProblemsView


bot = commands.Bot(command_prefix=commands.when_mentioned, test_guilds=[947447267697233920])


@bot.slash_command()
async def problems(inter):
    """
    Display all recent problems
    """
    view = await ProblemsView.create()
    await inter.response.send_message(f"Problems from {view.time_from} to {view.time_till}", view=view)


@bot.slash_command()
async def hosts(inter):
    """
    Display all hosts
    """
    view = await HostsView.create()
    await inter.response.send_message(view=view)


@bot.event
async def on_ready():
    print("ok!")


@bot.command()
async def ping(ctx):
    await ctx.send(f"pong! {round(bot.latency * 1000)}ms")


@bot.message_command()
async def send_over_email(inter, message):
    await inter.response.send_message(f"{message.content} sent")


dotenv.load_dotenv()
bot.run(os.getenv('DISCORD_TOKEN'))