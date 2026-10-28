
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
intents.members = True  # Also enable Server Members Intent in Developer Portal.

bot = commands.Bot(command_prefix="!", intents=intents)
data = {
    "welcome_channels": {},
    "welcome_messages": {},
    "giveaways": {},
}


def load_data():
    """Load saved settings while keeping compatibility with the old data.json."""
    global data
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
        if isinstance(saved, dict):
            data.update(saved)
    except FileNotFoundError:
        save_data()

    data.setdefault("welcome_channels", {})
    data.setdefault("welcome_messages", {})
    data.setdefault("giveaways", {})


def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def cute_embed(title, description, color=0xE8B4CB):
    embed = discord.Embed(
        title=f"୨୧ {title} ୨୧",
        description=description,
        color=color,
    )
    embed.set_footer(text="MairaSync • made with ♡")
    return embed


def is_admin():
    return app_commands.checks.has_permissions(administrator=True)


async def send_text_in_chunks(channel, text):
    """Send long custom text in Discord-safe chunks without changing its wording."""
    if not text:
        text = " "
    chunks = []
    while len(text) > 2000:
        split_at = text.rfind("\n", 0, 2000)
        if split_at < 1:
            split_at = 2000
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    if text:
        chunks.append(text)

    for chunk in chunks:
        await channel.send(chunk, allowed_mentions=discord.AllowedMentions.none())


def render_welcome(template, member):
    """Replace the supported placeholders in a saved welcome template."""
    replacements = {
        "{member}": member.mention,
        "{username}": discord.utils.escape_markdown(member.display_name),
        "{server}": discord.utils.escape_markdown(member.guild.name),
        "{count}": str(member.guild.member_count or 0),
    }
    for placeholder, value in replacements.items():
        template = template.replace(placeholder, value)
    return template


class GiveawayView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Enter Giveaway 🎀",
        style=discord.ButtonStyle.primary,
        custom_id="mairasync:giveaway:enter",
    )
    async def enter(self, interaction: discord.Interaction,
                    button: discord.ui.Button):
        if interaction.message is None:
            return await interaction.response.send_message(
                "Giveaway message nahi mila.", ephemeral=True
            )

        giveaway_id = str(interaction.message.id)
        giveaway = data["giveaways"].get(giveaway_id)

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
    print(f"MairaSync is online as {bot.user}!")
    try:
        synced = await bot.tree.sync()
        print(f"Slash commands synced: {len(synced)}")
    except discord.HTTPException as error:
        print(f"Slash command sync failed: {error}")


@bot.event
async def on_member_join(member):
    guild_key = str(member.guild.id)
    channel_id = data["welcome_channels"].get(guild_key)
    if not channel_id:
        return

    channel = member.guild.get_channel(channel_id)
    if channel is None:
        return

    template = data["welcome_messages"].get(
        guild_key,
        "Welcome {member} to **{server}**! ♡\n"
        "Please read the rules and enjoy your stay.",
    )
    message = render_welcome(template, member)

    try:
        # Only the new member mention is allowed; other accidental @everyone/@here
        # text in a custom template will not ping the whole server.
        await channel.send(
            message,
            allowed_mentions=discord.AllowedMentions(users=True, roles=False,
                                                    everyone=False),
        )
    except discord.Forbidden:
        print(f"MairaSync cannot send welcome messages in #{channel.name}.")


@bot.tree.command(name="announce", description="Post your custom announcement")
@is_admin()
@app_commands.describe(
    channel="Channel where the announcement will be posted",
    message="Write the exact announcement text you want to post",
    title="Optional title shown above your message",
)
async def announce(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    message: str,
    title: str = "",
):
    if title.strip():
        await channel.send(
            embed=cute_embed(title.strip(), message),
            allowed_mentions=discord.AllowedMentions.none(),
        )
    else:
        await send_text_in_chunks(channel, message)

    await interaction.response.send_message(
        f"Your announcement has been posted in {channel.mention} ♡",
        ephemeral=True,
    )


@bot.tree.command(name="rules", description="Post your custom server rules")
@is_admin()
@app_commands.describe(
    channel="Channel where the rules will be posted",
    message="Write or paste your complete custom rules here",
)
async def rules(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    message: str,
):
    await send_text_in_chunks(channel, message)
    await interaction.response.send_message(
        f"Your custom rules have been posted in {channel.mention} ♡",
        ephemeral=True,
    )


@bot.tree.command(
    name="welcome_setup",
    description="Set the welcome channel and your custom greeting",
)
@is_admin()
@app_commands.describe(
    channel="Channel where new members should be welcomed",
    message="Custom greeting. Placeholders: {member}, {username}, {server}, {count}",
)
async def welcome_setup(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    message: str,
):
    if interaction.guild_id is None:
        return await interaction.response.send_message(
            "Please use this command inside your server. ♡",
            ephemeral=True,
        )

    guild_key = str(interaction.guild_id)
    data["welcome_channels"][guild_key] = channel.id
    data["welcome_messages"][guild_key] = message
    save_data()

    await interaction.response.send_message(
        f"Welcome message saved! New members will be greeted in {channel.mention}.\n\n"
        f"**Preview:**\n{render_welcome(message, interaction.user)}",
        ephemeral=True,
        allowed_mentions=discord.AllowedMentions.none(),
    )


@bot.tree.command(name="giveaway", description="Start a button giveaway")
@is_admin()
@app_commands.describe(
    prize="What members can win",
    minutes="Giveaway duration in minutes",
    winners="Number of winners",
)
async def giveaway(
    interaction: discord.Interaction,
    prize: str,
    minutes: app_commands.Range[int, 1, 10080],
    winners: app_commands.Range[int, 1, 20] = 1,
):
    if not isinstance(interaction.channel, (discord.TextChannel, discord.Thread)):
        return await interaction.response.send_message(
            "Use this command in a server text channel.", ephemeral=True
        )

    await interaction.response.defer(ephemeral=True)
    end_ts = (
        datetime.now(timezone.utc) + timedelta(minutes=minutes)
    ).timestamp()

    embed = cute_embed(
        f"Giveaway: {prize}",
        f"**Prize:** {prize}\n"
        f"**Winners:** {winners}\n"
        f"**Ends:** <t:{int(end_ts)}:R>\n\n"
        "Press the button below to enter!\n"
        "Entries: **0**",
    )

    message = await interaction.channel.send(embed=embed, view=GiveawayView())
    data["giveaways"][str(message.id)] = {
        "guild_id": interaction.guild_id,
        "channel_id": interaction.channel_id,
        "prize": prize,
        "winners": winners,
        "end_ts": end_ts,
        "entries": [],
        "ended": False,
    }
    save_data()

    await interaction.followup.send(
        f"Giveaway created! Message ID: `{message.id}` 🎁",
        ephemeral=True,
    )


@tasks.loop(seconds=15)
async def check_giveaways():
    now = datetime.now(timezone.utc).timestamp()

    for giveaway_id, giveaway_data in list(data["giveaways"].items()):
        if giveaway_data.get("ended") or now < giveaway_data["end_ts"]:
            continue

        giveaway_data["ended"] = True
        save_data()

        channel = bot.get_channel(giveaway_data["channel_id"])
        if channel is None:
            continue

        try:
            message = await channel.fetch_message(int(giveaway_id))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            continue

        entries = list(set(giveaway_data["entries"]))
        winner_count = min(giveaway_data["winners"], len(entries))
        chosen = random.sample(entries, winner_count) if winner_count else []
        winner_text = (
            ", ".join(f"<@{user_id}>" for user_id in chosen)
            if chosen else "No valid entries this time."
        )

        embed = cute_embed(
            "Giveaway ended!",
            f"**Prize:** {giveaway_data['prize']}\n"
            f"**Winner(s):** {winner_text}\n"
            f"**Total entries:** {len(entries)}",
            color=0xB8E0D2,
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
    if interaction.guild is None:
        return await interaction.response.send_message(
            "Use this command inside a server.", ephemeral=True
        )

    if member.top_role >= interaction.user.top_role and (
        interaction.guild.owner_id != interaction.user.id
    ):
        return await interaction.response.send_message(
            "You cannot warn someone with an equal or higher role.",
            ephemeral=True,
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
        ephemeral=True,
    )


@bot.tree.command(name="kick", description="Kick a server member")
@app_commands.checks.has_permissions(kick_members=True)
@app_commands.describe(member="Member to kick", reason="Reason for kicking")
async def kick(interaction: discord.Interaction,
               member: discord.Member, reason: str):
    if interaction.guild is None:
        return await interaction.response.send_message(
            "Use this command inside a server.", ephemeral=True
        )

    if member.id == interaction.guild.owner_id:
        return await interaction.response.send_message(
            "The server owner cannot be kicked.", ephemeral=True
        )

    if member.top_role >= interaction.user.top_role and (
        interaction.guild.owner_id != interaction.user.id
    ):
        return await interaction.response.send_message(
            "You cannot kick someone with an equal or higher role.",
            ephemeral=True,
        )

    try:
        await member.kick(reason=reason)
    except discord.Forbidden:
        return await interaction.response.send_message(
            "MairaSync needs Kick Members permission and a higher role.",
            ephemeral=True,
        )

    await interaction.response.send_message(
        f"Kicked {member}.\nReason: {reason}", ephemeral=True
    )


@bot.tree.command(name="clear", description="Delete recent messages")
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.describe(amount="Number of messages to delete (1–100)")
async def clear(
    interaction: discord.Interaction,
    amount: app_commands.Range[int, 1, 100],
):
    if not isinstance(interaction.channel, discord.TextChannel):
        return await interaction.response.send_message(
            "Use this in a text channel.", ephemeral=True
        )

    await interaction.response.defer(ephemeral=True)
    try:
        deleted = await interaction.channel.purge(limit=amount)
    except discord.Forbidden:
        return await interaction.followup.send(
            "MairaSync needs Manage Messages permission.", ephemeral=True
        )

    await interaction.followup.send(
        f"Deleted {len(deleted)} messages. ♡", ephemeral=True
    )


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
):
    if isinstance(error, app_commands.MissingPermissions):
        message = "You don't have permission to use this command. ♡"
    else:
        print(f"Command error: {error!r}")
        message = "Something went wrong. Please check the bot permissions."

    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except discord.HTTPException:
        pass


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