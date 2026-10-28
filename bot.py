
import os
import json
import random
import asyncio
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
DATA_FILE = "data.json"

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
data = {"welcome_channels": {}, "giveaways": {}}
data_lock = asyncio.Lock()


def load_data():
    global data
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
        data.update(saved)
    except FileNotFoundError:
        save_data()


def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def cute_embed(title, description, color=0xE8B4CB):
    embed = discord.Embed(
        title=f"୨୧ {title} ୨୧",
        description=description,
        color=color
    )
    embed.set_footer(text="Astra • made with ♡")
    return embed


def is_admin():
    return app_commands.checks.has_permissions(administrator=True)


class GiveawayView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Enter Giveaway 🎀",
        style=discord.ButtonStyle.primary,
        custom_id="astra:giveaway:enter"
    )
    async def enter(self, interaction: discord.Interaction,
                    button: discord.ui.Button):
        if interaction.message is None:
            return await interaction.response.send_message(
                "Giveaway message nahi mila.", ephemeral=True
            )

        gid = str(interaction.message.id)
        giveaway = data["giveaways"].get(gid)

        if not giveaway or giveaway.get("ended"):
            return await interaction.response.send_message(
                "Ye giveaway ab active nahi hai. ♡", ephemeral=True
            )

        if datetime.now(timezone.utc).timestamp() >= giveaway["end_ts"]:
            return await interaction.response.send_message(
                "Entry ka time khatam ho gaya hai!", ephemeral=True
            )

        user_id = interaction.user.id
        if user_id in giveaway["entries"]:
            giveaway["entries"].remove(user_id)
            save_data()
            return await interaction.response.send_message(
                "Tumhari entry remove kar di! ♡", ephemeral=True
            )

        giveaway["entries"].append(user_id)
        save_data()
        await interaction.response.send_message(
            "You're entered! Good luck 🎀", ephemeral=True
        )


@bot.event
async def on_ready():
    print(f"Astra is online as {bot.user}!")
    print("Slash commands are ready.")


@bot.event
async def on_member_join(member):
    channel_id = data["welcome_channels"].get(str(member.guild.id))
    if not channel_id:
        return

    channel = member.guild.get_channel(channel_id)
    if channel:
        embed = cute_embed(
            "Welcome!",
            f"Welcome {member.mention} to **{member.guild.name}**! ♡\n"
            "Please read the server rules and enjoy your stay."
        )
        await channel.send(embed=embed)


@bot.tree.command(name="announce", description="Post a server announcement")
@is_admin()
@app_commands.describe(
    channel="Where to post",
    title="Announcement title",
    message="Announcement text"
)
async def announce(interaction: discord.Interaction,
                   channel: discord.TextChannel,
                   title: str, message: str):
    embed = cute_embed(title, message)
    embed.timestamp = datetime.now(timezone.utc)
    await channel.send(embed=embed)
    await interaction.response.send_message(
        f"Announcement posted in {channel.mention} ♡",
        ephemeral=True
    )


@bot.tree.command(name="rules", description="Show server rules")
async def rules(interaction: discord.Interaction):
    text = (
        "୨୧ **Server Rules** ୨୧\n\n"
        "01. Be respectful to everyone.\n"
        "02. No spam or unwanted advertising.\n"
        "03. No harassment, hate speech or threats.\n"
        "04. Use the correct channels.\n"
        "05. Follow Discord's Terms and Community Guidelines.\n"
        "06. Listen to the moderation team.\n\n"
        "Have fun and keep the server comfy! ♡"
    )
    await interaction.response.send_message(
        embed=cute_embed("Server Rules", text)
    )


@bot.tree.command(name="welcome_setup",
                  description="Set the welcome channel")
@is_admin()
async def welcome_setup(interaction: discord.Interaction,
                        channel: discord.TextChannel):
    data["welcome_channels"][str(interaction.guild_id)] = channel.id
    save_data()
    await interaction.response.send_message(
        f"Welcome messages will go to {channel.mention} 🎀",
        ephemeral=True
    )


@bot.tree.command(name="giveaway", description="Start a button giveaway")
@is_admin()
@app_commands.describe(
    prize="What members can win",
    minutes="Giveaway duration in minutes",
    winners="Number of winners"
)
async def giveaway(interaction: discord.Interaction,
                   prize: str, minutes: app_commands.Range[int, 1, 10080],
                   winners: app_commands.Range[int, 1, 20] = 1):
    await interaction.response.defer(ephemeral=True)

    end_ts = (datetime.now(timezone.utc)
              + timedelta(minutes=minutes)).timestamp()

    embed = cute_embed(
        f"Giveaway: {prize}",
        f"**Prize:** {prize}\n"
        f"**Winners:** {winners}\n"
        f"**Ends:** <t:{int(end_ts)}:R>\n\n"
        "Press the button below to enter!\n"
        "Entries: **0**"
    )

    message = await interaction.channel.send(
        embed=embed, view=GiveawayView()
    )

    data["giveaways"][str(message.id)] = {
        "guild_id": interaction.guild_id,
        "channel_id": interaction.channel_id,
        "prize": prize,
        "winners": winners,
        "end_ts": end_ts,
        "entries": [],
        "ended": False
    }
    save_data()

    await interaction.followup.send(
        f"Giveaway created! Message ID: `{message.id}` 🎁",
        ephemeral=True
    )


@tasks.loop(seconds=15)
async def check_giveaways():
    now = datetime.now(timezone.utc).timestamp()

    for gid, giveaway_data in list(data["giveaways"].items()):
        if giveaway_data["ended"] or now < giveaway_data["end_ts"]:
            continue

        giveaway_data["ended"] = True
        save_data()

        channel = bot.get_channel(giveaway_data["channel_id"])
        if channel is None:
            continue

        try:
            message = await channel.fetch_message(int(gid))
        except (discord.NotFound, discord.Forbidden,
                discord.HTTPException):
            continue

        entries = list(set(giveaway_data["entries"]))
        count = min(giveaway_data["winners"], len(entries))
        chosen = random.sample(entries, count) if count else []

        if chosen:
            winner_text = ", ".join(f"<@{uid}>" for uid in chosen)
        else:
            winner_text = "No valid entries this time."

        embed = cute_embed(
            "Giveaway ended!",
            f"**Prize:** {giveaway_data['prize']}\n"
            f"**Winner(s):** {winner_text}\n"
            f"**Total entries:** {len(entries)}",
            color=0xB8E0D2
        )

        await message.edit(embed=embed, view=None)
        await channel.send(
            f"🎉 Giveaway results for **{giveaway_data['prize']}**!\n"
            f"Winner(s): {winner_text}"
        )


@check_giveaways.before_loop
async def before_giveaway_check():
    await bot.wait_until_ready()


@bot.tree.command(name="warn", description="Warn a server member")
@app_commands.checks.has_permissions(moderate_members=True)
@app_commands.describe(member="Member to warn", reason="Reason for warning")
async def warn(interaction: discord.Interaction,
               member: discord.Member, reason: str):
    if member.top_role >= interaction.user.top_role and (
        interaction.guild.owner_id != interaction.user.id
    ):
        return await interaction.response.send_message(
            "You cannot warn someone with an equal or higher role.",
            ephemeral=True
        )

    try:
        await member.send(
            f"You received a warning in **{interaction.guild.name}**.\n"
            f"Reason: {reason}"
        )
    except discord.HTTPException:
        pass

    await interaction.response.send_message(
        f"{member.mention} has been warned. Reason: {reason}",
        ephemeral=True
    )


@bot.tree.command(name="kick", description="Kick a server member")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction,
               member: discord.Member, reason: str):
    if member.id == interaction.guild.owner_id:
        return await interaction.response.send_message(
            "The server owner cannot be kicked.", ephemeral=True
        )

    if member.top_role >= interaction.user.top_role and (
        interaction.guild.owner_id != interaction.user.id
    ):
        return await interaction.response.send_message(
            "You cannot kick someone with an equal or higher role.",
            ephemeral=True
        )

    try:
        await member.kick(reason=reason)
    except discord.Forbidden:
        return await interaction.response.send_message(
            "Astra needs Kick Members permission and a higher role.",
            ephemeral=True
        )

    await interaction.response.send_message(
        f"Kicked {member}.\nReason: {reason}", ephemeral=True
    )


@bot.tree.command(name="clear", description="Delete recent messages")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear(interaction: discord.Interaction,
                amount: app_commands.Range[int, 1, 100]):
    if not isinstance(interaction.channel, discord.TextChannel):
        return await interaction.response.send_message(
            "Use this in a text channel.", ephemeral=True
        )

    await interaction.response.defer(ephemeral=True)
    try:
        deleted = await interaction.channel.purge(limit=amount)
    except discord.Forbidden:
        return await interaction.followup.send(
            "Astra needs Manage Messages permission.", ephemeral=True
        )

    await interaction.followup.send(
        f"Deleted {len(deleted)} messages. ♡", ephemeral=True
    )


@bot.tree.error
async def on_app_command_error(interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        message = "You don't have permission to use this command. ♡"
    else:
        print(f"Command error: {error}")
        message = "Something went wrong. Please check bot permissions."

    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(
            message, ephemeral=True
        )


async def main():
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN is missing from environment.")

    load_data()
    async with bot:
        bot.add_view(GiveawayView())
        check_giveaways.start()
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
