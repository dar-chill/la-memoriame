import discord
from discord.ext import commands
from discord import app_commands
import requests
import os
from collections import defaultdict
from dotenv import load_dotenv
import re

# === LOAD ENV VARIABLES ===
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = "openrouter/quasar-alpha"

# === INTENTS AND BOT SETUP ===
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="/", intents=intents)
tree = bot.tree

# === USER MESSAGE STORAGE ===
user_messages = defaultdict(list)
user_facts = defaultdict(set)
user_mentions = defaultdict(list)

# === ON MESSAGE: COLLECT MESSAGES FOR STYLE LEARNING ===
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    username = message.author.name.lower()
    content = message.content
    user_messages[username].append(content)
    if len(user_messages[username]) > 50:
        user_messages[username] = user_messages[username][-50:]

    hobbies_keywords = ["like", "love", "enjoy", "playing", "watching"]
    for keyword in hobbies_keywords:
        if keyword in content.lower():
            user_facts[username].add(content.strip())

    for user in message.mentions:
        user_mentions[user.name.lower()].append(content.strip())

    await bot.process_commands(message)

# === ON READY ===
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user.name}")
    try:
        synced = await tree.sync()
        print(f"🔁 Synced {len(synced)} global commands.")
    except Exception as e:
        print(f"❌ Sync error: {e}, pls beg dar to fix")

# === STYLE PROMPT GENERATOR ===
def generate_style_prompt(username):
    messages = user_messages.get(username.lower(), [])
    facts = user_facts.get(username.lower(), set())
    mentions = user_mentions.get(username.lower(), [])
    sample = '\n'.join(messages[-10:]) if messages else ""
    fact_summary = '\n'.join(list(facts)[:5]) if facts else ""
    mention_sample = '\n'.join(mentions[-5:]) if mentions else ""

    prompt = f"Respond in the style of {username}."
    if sample:
        prompt += f"\nHere are some example messages:\n{sample}"
    if fact_summary:
        prompt += f"\nHere are some things they care about:\n{fact_summary}"
    if mention_sample:
        prompt += f"\nHere are some things people say about them:\n{mention_sample}"

    prompt += "\nResponse:"
    return prompt

# === AUTOCOMPLETE CALLBACK ===
async def user_autocomplete(interaction: discord.Interaction, current: str):
    members = [member.name for member in interaction.guild.members if not member.bot]
    return [app_commands.Choice(name=name, value=name) for name in members if current.lower() in name.lower()][:25]

# === MAIN SLASH COMMAND ===
@tree.command(name="chatbot", description="Talk to the bot or mimic a user")
@app_commands.describe(prompt="What do you want to say? (optional)", user="Username to mimic (must match username, not @mention)")
@app_commands.autocomplete(user=user_autocomplete)
async def chatbot(interaction: discord.Interaction, prompt: str = None, user: str = None):
    if not prompt and not user:
        await interaction.response.send_message("❌ You must provide at least a prompt or a user to mimic.", ephemeral=True)
        return

    await interaction.response.defer()
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    if user:
        style_prompt = generate_style_prompt(user)
        system_prompt = style_prompt
        title = f"🗣 Mimicking {user}"
    else:
        system_prompt = "Respond concisely like a human Discord user."
        title = "💬 Chatbot"

    final_prompt = prompt if prompt else "(Say something in the style of the user.)"

    data = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": final_prompt}
        ]
    }

    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data, timeout=10)
        response.raise_for_status()
        result = response.json()
        reply = result['choices'][0]['message']['content']
    except Exception as e:
        reply = f"⚠️ Failed to get response from OpenRouter: {e}, pls beg dar to fix"

    embed = discord.Embed(title=title, description=f"**Prompt:** {final_prompt}\n\n{reply}", color=discord.Color.blurple())
    embed.set_footer(text=f"Requested by {interaction.user.display_name}")
    await interaction.followup.send(embed=embed)

# === ADMIN-ONLY UPDATE COMMAND ===
@tree.command(name="update", description="Scan recent messages from all server members (admin only)")
async def update(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You must be an admin to use this command.", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)
    scanned = 0
    limit = 50000

    keywords = ["forsaken", "blue lock", "blr", "decaying winter", "dw", "basketball zero"]

    for channel in interaction.guild.text_channels:
        try:
            async for message in channel.history(limit=None):
                if scanned >= limit:
                    break
                if message.author.bot:
                    continue

                name = message.author.name.lower()
                content = message.content
                user_messages[name].append(content)
                if len(user_messages[name]) > 50:
                    user_messages[name] = user_messages[name][-50:]
                scanned += 1

                hobbies_keywords = ["like", "love", "enjoy", "playing", "watching"]
                for keyword in hobbies_keywords:
                    if keyword in content.lower():
                        user_facts[name].add(content.strip())

                for keyword in keywords:
                    if keyword in content.lower():
                        user_facts[name].add(f"Mentions interest in: {keyword}")

                for user in message.mentions:
                    user_mentions[user.name.lower()].append(content.strip())

        except discord.Forbidden as e:
            print(f"⚠️ Forbidden error: {e}, pls beg dar to fix")
            continue
        except Exception as e:
            print(f"⚠️ Unexpected error: {e}, pls beg dar to fix")
            continue

    await interaction.followup.send(f"✅ Scanned {scanned} messages for style learning.")

# === RUN THE BOT ===
bot.run(DISCORD_TOKEN)
