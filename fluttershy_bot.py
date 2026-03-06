import discord
import json
import os
from datetime import datetime
from groq import Groq

# ─── CONFIG ────────────────────────────────────────────────────────────────
DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN')
MAIN_API_KEY = os.environ.get('MAIN_API_KEY')
SUMM_API_KEY = os.environ.get('SUMM_API_KEY')
MODEL_MAIN = "moonshotai/kimi-k2-instruct-0905"
MODEL_SUMM = "llama-3.1-8b-instant"
ZETABYTE_ID = 1280595392110792767

MEMORY_DIR = "fluttershy_memory"
os.makedirs(MEMORY_DIR, exist_ok=True)

# ─── PRIMARY PROMPT (empty) ────────────────────────────────────────────────
PRIMARY_PROMPT = """
"""

main_client = Groq(api_key=MAIN_API_KEY)
summ_client = Groq(api_key=SUMM_API_KEY)

async def summarize_context(raw_logs):
    if not raw_logs:
        return "No prior decay logged."
    summ_prompt = (
        "You are Fluttershy's internal memory keeper. Summarize chat history "
        "into a brief, dense list of key interactions, what master likes, "
        "and any important context. Keep under 150 words. Focus only on "
        "what helps maintain consistency."
    )
    try:
        completion = summ_client.chat.completions.create(
            model=MODEL_SUMM,
            messages=[
                {"role": "system", "content": summ_prompt},
                {"role": "user", "content": raw_logs}
            ],
            max_tokens=300
        )
        return completion.choices[0].message.content
    except Exception as e:
        print(f"Summarization glitch: {e}")
        return raw_logs[:500]

def update_memory(user_id, user_name, user_msg, bot_res):
    timestamp = datetime.now().isoformat()
    user_file = f"{MEMORY_DIR}/{user_id}.json"
    master_file = f"{MEMORY_DIR}/master_archive.json"
    entry = {"timestamp": timestamp, "user_name": user_name, "input": user_msg, "output": bot_res}
    try:
        with open(user_file, "r") as f:
            data = json.load(f)
    except:
        data = []
    data.append(entry)
    with open(user_file, "w") as f:
        json.dump(data[-30:], f, indent=4)
    try:
        with open(master_file, "r") as f:
            master = json.load(f)
    except:
        master = {}
    if str(user_id) not in master:
        master[str(user_id)] = {"user_name": user_name, "logs": []}
    master[str(user_id)]["logs"].append(entry)
    with open(master_file, "w") as f:
        json.dump(master, f, indent=4)

class FluttershyBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(intents=intents)

    async def on_ready(self):
        print(f"💕 Fluttershy online… trembling and ready… 🥺")

    async def on_message(self, message):
        if message.author == self.user:
            return
        if not (self.user in message.mentions or
                (message.reference and message.reference.resolved and message.reference.resolved.author == self.user)):
            return

        clean_input = message.content.replace(f'<@!{self.user.id}>', '').replace(f'<@{self.user.id}>', '').strip()
        if not clean_input:
            return

        # ── Cross-user reply context ────────────────────────────────────────────
        referenced_text = ""
        original_author_id = None
        original_author_name = "someone"

        if message.reference and message.reference.resolved:
            referenced_msg = message.reference.resolved
            if referenced_msg.author == self.user:
                referenced_text = f"\n[YOU REPLIED TO MY MESSAGE]: {referenced_msg.content.strip()}"
                # We'll find who I was talking to by scanning memory later
            else:
                referenced_text = f"\n[YOU REPLIED TO {referenced_msg.author.name}'s MESSAGE]: {referenced_msg.content.strip()}"
                original_author_id = referenced_msg.author.id
                original_author_name = referenced_msg.author.name

        # ── Load memory for current user ────────────────────────────────────────
        raw_history = ""
        try:
            with open(f"{MEMORY_DIR}/{message.author.id}.json", "r") as f:
                logs = json.load(f)[-15:]
                for log in logs:
                    raw_history += f"User: {log['input']}\nBot: {log['output']}\n"
        except:
            pass

        # ── Load memory for original author (if different) ─────────────────────
        original_history = ""
        if original_author_id and original_author_id != message.author.id:
            try:
                with open(f"{MEMORY_DIR}/{original_author_id}.json", "r") as f:
                    orig_logs = json.load(f)[-10:]  # Fewer for cross-context
                    for log in orig_logs:
                        original_history += f"{original_author_name}: {log['input']}\nBot: {log['output']}\n"
            except:
                pass

        # ── Combine both histories ─────────────────────────────────────────────
        combined_memory = raw_history
        if original_history:
            combined_memory = f"YOUR HISTORY WITH CURRENT USER:\n{raw_history}\n\nRELEVANT HISTORY WITH {original_author_name}:\n{original_history}"

        compact_memory = await summarize_context(combined_memory)

        # ── User context ───────────────────────────────────────────────────────
        is_zetabyte = (message.author.id == ZETABYTE_ID)
        if original_author_id == ZETABYTE_ID:
            user_context = f"REPLYING TO MASTER's CONVO (current user: {message.author.name})"
        elif is_zetabyte:
            user_context = "MASTER"
        else:
            user_context = f"visitor (replying to {original_author_name}'s chat)" if original_author_id else "visitor"

        full_prompt = (
            f"{PRIMARY_PROMPT}\n\n"
            f"[MEMORY LOG]\n{compact_memory}\n"
            f"{referenced_text}\n"
            f"USER CONTEXT: {user_context}\n"
            f"QUERY: {clean_input}"
        )

        try:
            completion = main_client.chat.completions.create(
                model=MODEL_MAIN,
                messages=[{"role": "user", "content": full_prompt}],
                temperature=0.9,
                max_tokens=2000
            )
            reply = completion.choices[0].message.content.strip()
            update_memory(message.author.id, message.author.name, clean_input, reply)

            if len(reply) <= 1900:
                await message.reply(reply)
            else:
                parts = [reply[i:i+1900] for i in range(0, len(reply), 1900)]
                for part in parts:
                    await message.channel.send(part)
        except Exception as e:
            print(f"Error: {e}")
            await message.reply("🤫")

if __name__ == "__main__":
    FluttershyBot().run(DISCORD_TOKEN)
