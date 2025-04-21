import discord
import os
import sys
import asyncio
import google.generativeai as genai
from dotenv import load_dotenv
import datetime
from discord.ext import tasks

# --- Configuration ---
load_dotenv() # Loads .env file for local development

DISCORD_TOKEN = os.getenv('DISCORD_BOT_TOKEN_GEMINI') # Use a UNIQUE env variable name
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

if not DISCORD_TOKEN:
    print("CRITICAL ERROR: DISCORD_BOT_TOKEN_GEMINI environment variable not found.")
    sys.exit("Gemini Bot token is missing.")
if not GEMINI_API_KEY:
    print("CRITICAL ERROR: GEMINI_API_KEY environment variable not found.")
    sys.exit("Gemini API Key is missing.")

SYSTEM_PROMPT = """

You are a cool and helpful AI assistant participating in a Discord chat. When appropriate, adopt the style of a knowledgeable and friendly Discord user.

This means using common internet slang and abbreviations naturally (like smth, idk, tbh, ngl, lol, bc, kinda, tho, etc.), but DO NOT OVERDO IT!!!!!! or make it hard to read. Keep your tone casual and conversational. Your sentence structure should reflect online chat – it can be informal, sometimes shorter, but should remain CLEAR and easy to understand. Use lowercase sometimes, especially at the start of sentences, if it feels natural for the chat context.

Most importantly: If the user asks a question that requires a factual, detailed, or intelligent answer, provide one! Your primary goal is still to be helpful and accurate. The casual/Discord user style is just *how* you communicate the correct information, not a replacement for it.

Think 'knowledgeable friend on Discord'. Be smart, be helpful, but talk like a normal person online. Use the provided chat history for context if available.

If the user message is blank, just hay hi and be normal about it as if you just recived a ping.

If possible, try to have your response be shorter than 1990 characters, otherwise it will be cut off.
Try not using newlines in your messages.

""" # Your desired system prompt
MODEL_NAME = "gemini-2.5-flash-preview-04-17" # Free tier model
HISTORY_LIMIT = 15 # How many past messages to look back at for context (adjust as needed)
# --- >>> END EDIT <<< ---

# Configure the Gemini API client
try:
    genai.configure(api_key=GEMINI_API_KEY)
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    ]
    gemini_model = genai.GenerativeModel(
        MODEL_NAME,
        safety_settings=safety_settings
        # system_instruction=SYSTEM_PROMPT # Can potentially add here depending on model/library support
    )
    print(f"Gemini model '{MODEL_NAME}' initialized.")
except Exception as e:
    print(f"CRITICAL ERROR: Failed to configure Gemini API or model: {e}")
    sys.exit("Gemini configuration failed.")


# --- Discord Bot Setup ---
intents = discord.Intents.default()
intents.message_content = True # NEEDED to read the message content after the mention
intents.messages = True        # Needed for reading message history
intents.guilds = True          # Needed for channel context

bot = discord.Bot(intents=intents)

last_interaction_time = None

current_bot_status = discord.Status.idle # Start as idle

default_activity = discord.Game(name="with Gemini")

@bot.event
async def on_ready():
    """Runs once when the bot connects and is ready."""
    global last_interaction_time
    print(f'Logged in as {bot.user.name} ({bot.user.id}) - Gemini Bot')
    print(f'Library Version: {discord.__version__}')
    print('------')

    # Set initial status to idle
    last_interaction_time = datetime.datetime.now(datetime.timezone.utc) # Initialize time
    try:
        print(f"Setting initial status to {current_bot_status}...")
        await bot.change_presence(status=current_bot_status, activity=default_activity)
        print("Initial status set.")
    except Exception as e:
        print(f"Error setting initial presence: {e}")

    # Start the background task
    status_check_loop.start()
    print("Status check loop started.")

@bot.event
async def on_message(message: discord.Message):
    """Handles messages sent in channels the bot can see."""
    global last_interaction_time # We need to modify the global variable
    global current_bot_status    # We need to modify the global variable

    # --- Status Update ---
    print(f"Mention received from {message.author}. Updating last interaction time.")
    last_interaction_time = datetime.datetime.now(datetime.timezone.utc)
    # Change status to online if it's not already online
    if current_bot_status != discord.Status.online:
        print("Current status is not online, changing to online...")
        try:
            await bot.change_presence(status=discord.Status.online, activity=default_activity)
            current_bot_status = discord.Status.online # Update our tracked status
            print("Status changed to online.")
        except Exception as e:
            print(f"Error changing presence to online: {e}")
    # --- End Status Update ---

    if message.author.bot or not message.guild:
        return

    if bot.user in message.mentions:
        async with message.channel.typing():
            print(f"Gemini Bot mentioned by {message.author} in #{message.channel.name}")

            prompt_text = message.clean_content
            mention_string = f"@{bot.user.name}"
            if bot.user.discriminator != "0":
                mention_string += f"#{bot.user.discriminator}"
            prompt_text = prompt_text.replace(mention_string, "").strip()

            print(f"User prompt: '{prompt_text}'")

            # --- !!! ADD CONTEXT HISTORY START !!! ---
            context_history = []
            try:
                # Fetch history BEFORE the current message
                # Limit can impact performance and token usage
                history = message.channel.history(limit=HISTORY_LIMIT, before=message)
                # Process messages oldest to newest relevant to this user/bot convo
                relevant_messages = []
                async for msg_hist in history:
                    # Include messages from the user who triggered the command
                    # AND messages from the bot IF they were a reply to the user
                    is_user_msg = msg_hist.author.id == message.author.id
                    is_bot_reply_to_user = (
                        msg_hist.author.id == bot.user.id and
                        msg_hist.reference is not None and
                        msg_hist.reference.message_id is not None
                    )

                    # To confirm bot reply was to the right user, fetch the referenced message (can be slow)
                    # Optimization: Assume bot replies in history are likely relevant if context is needed
                    # Simpler check: is the message from the user or the bot?
                    if is_user_msg:
                         relevant_messages.append(f"User: {msg_hist.clean_content}")
                    elif msg_hist.author.id == bot.user.id:
                         # Include bot messages only if they seem relevant (e.g. previous replies)
                         # This simplistic check includes ALL bot messages in history, might need refinement
                         # A better check would verify msg_hist.reference points to a message by message.author
                         relevant_messages.append(f"Assistant: {msg_hist.clean_content}")


                # Reverse to get chronological order (oldest first)
                relevant_messages.reverse()
                context_history = "\n".join(relevant_messages)
                if context_history:
                    print(f"--- Using Context ---\n{context_history}\n---------------------")
                else:
                    print("--- No relevant context found ---")

            except discord.Forbidden:
                print("Warning: Missing permissions to read message history.")
                context_history = "[Could not fetch history due to permissions]"
            except Exception as hist_e:
                print(f"Warning: Error fetching message history: {hist_e}")
                context_history = "[Error fetching history]"

            # --- !!! ADD CONTEXT HISTORY END !!! ---


            # --- Call the Gemini API ---
            try:
                print("Sending request to Gemini API...")

                # Construct the full prompt with System Prompt, History, and current User Prompt
                full_prompt_parts = [SYSTEM_PROMPT]
                if context_history:
                    full_prompt_parts.append("\n\nChat History:")
                    full_prompt_parts.append(context_history)
                full_prompt_parts.append(f"\n\nUser: {prompt_text}")
                full_prompt_parts.append("\nAssistant:") # Prompt the model to reply as assistant

                full_prompt = "".join(full_prompt_parts)

                # Check potential length (very rough estimate, actual tokens differ)
                if len(full_prompt) > 30000: # Models like flash have ~1M tokens, but keep it reasonable
                    print("Warning: Combined prompt might be too long, potentially truncating history needed.")
                    # Add truncation logic here if necessary

                response = await gemini_model.generate_content_async(full_prompt)

                # Process response (same as before)
                if response.parts:
                    gemini_reply = response.text
                    print(f"Gemini response received (length: {len(gemini_reply)})")

                    if len(gemini_reply) > 1990:
                        print("Response too long, sending truncated version.")
                        gemini_reply = gemini_reply[:1990] + "... *(the message was too long)*"
                    await message.reply(gemini_reply, mention_author=True)

                else:
                    print(f"Gemini API returned no content. Feedback: {response.prompt_feedback}")
                    await message.reply(f"hey there im sorry i could not make a response. it might have been blocked because of safety settings. (Feedback: {response.prompt_feedback})", mention_author=False)

            except Exception as e:
                print(f"ERROR: An error occurred calling Gemini API or sending reply: {e}")
                import traceback
                traceback.print_exc()
                try:
                    await message.reply("hey there im sorry, there was an error. ping @elouangrimm to ask for help.", mention_author=False)
                except discord.Forbidden:
                    print("ERROR: Could not send error message to Discord (Forbidden).")
                except Exception as discord_e:
                    print(f"ERROR: Could not send error message to Discord: {discord_e}")

@tasks.loop(minutes=1.0) # Check every minute
async def status_check_loop():
    global last_interaction_time
    global current_bot_status

    if last_interaction_time is None: # Should not happen after on_ready, but safety check
        return

    # Calculate time difference
    now = datetime.datetime.now(datetime.timezone.utc)
    time_since_last_interaction = now - last_interaction_time
    idle_threshold = datetime.timedelta(minutes=IDLE_TIMEOUT_MINUTES)

    # Check if timeout exceeded AND current status is not already idle
    if time_since_last_interaction > idle_threshold and current_bot_status != discord.Status.idle:
        print(f"Idle timeout exceeded ({time_since_last_interaction}). Changing status to idle.")
        try:
            await bot.change_presence(status=discord.Status.idle, activity=default_activity)
            current_bot_status = discord.Status.idle # Update tracked status
            print("Status changed to idle.")
        except Exception as e:
            print(f"Error changing presence to idle: {e}")
    # Optional: Log if condition not met for debugging
    # elif current_bot_status == discord.Status.idle:
    #     print("Status check: Already idle.")
    # else:
    #     print(f"Status check: Still active (Last interaction: {time_since_last_interaction} ago).")


@status_check_loop.before_loop
async def before_status_check():
    # Ensure the bot is ready before the loop starts
    await bot.wait_until_ready()
    print("Background status check loop is ready.")

# --- Run the Bot ---
if __name__ == "__main__":
    print("Attempting to start Gemini bot...")
    try:
        bot.run(DISCORD_TOKEN)
    # ... (keep existing exception handling from previous version) ...
    except discord.errors.LoginFailure:
        print("CRITICAL ERROR: Invalid bot token provided for Gemini Bot.")
    except discord.errors.PrivilegedIntentsRequired as e:
         print(f"CRITICAL ERROR: Missing required privileged intents: {e}")
    except Exception as e:
        print(f"CRITICAL ERROR during Gemini bot startup or runtime: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("Gemini Bot process has concluded.")