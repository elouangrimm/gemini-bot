import discord
import os
import sys
import asyncio
import google.generativeai as genai
from dotenv import load_dotenv

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

# --- >>> EDIT THESE <<< ---
SYSTEM_PROMPT = "You are a helpful and creative assistant." # Your desired system prompt
MODEL_NAME = "gemini-1.5-flash-latest" # Free tier model
# --- >>> END EDIT <<< ---

# Configure the Gemini API client
try:
    genai.configure(api_key=GEMINI_API_KEY)
    # Optional: Configure safety settings
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    ]
    gemini_model = genai.GenerativeModel(
        MODEL_NAME,
        safety_settings=safety_settings
        # Optional: Add system_instruction=SYSTEM_PROMPT here if preferred
        # and supported well by the library version for your chosen model.
        # Otherwise, we'll prepend it to the user message.
    )
    print(f"Gemini model '{MODEL_NAME}' initialized.")
except Exception as e:
    print(f"CRITICAL ERROR: Failed to configure Gemini API or model: {e}")
    sys.exit("Gemini configuration failed.")


# --- Discord Bot Setup ---
intents = discord.Intents.default()
intents.message_content = True # NEEDED to read the message content after the mention
intents.members = False      # Probably not needed for this bot
intents.presences = False    # Probably not needed for this bot

bot = discord.Bot(intents=intents)

@bot.event
async def on_ready():
    """Runs once when the bot connects and is ready."""
    print(f'Logged in as {bot.user.name} ({bot.user.id}) - Gemini Bot')
    print(f'Library Version: {discord.__version__}')
    print('------')
    # Set a simple status
    await bot.change_presence(activity=discord.Game(name="with Gemini"))

@bot.event
async def on_message(message: discord.Message):
    """Handles messages sent in channels the bot can see."""

    # 1. Ignore messages from bots (including self) or DMs
    if message.author.bot or not message.guild:
        return

    # 2. Check if the bot itself was mentioned
    if bot.user in message.mentions:

        # 3. Indicate bot is processing (typing indicator)
        async with message.channel.typing():
            print(f"Gemini Bot mentioned by {message.author} in #{message.channel.name}")

            # 4. Extract the user's actual prompt (remove bot mention)
            # Using clean_content removes markdown formatting of mention
            prompt_text = message.clean_content
            # Remove the specific mention (adjust if bot name changes or has nickname)
            mention_string = f"@{bot.user.name}"
            if bot.user.discriminator != "0": # Handle older username#discriminator format if needed
                mention_string += f"#{bot.user.discriminator}"

            prompt_text = prompt_text.replace(mention_string, "").strip()

            if not prompt_text:
                print("Mention received but no prompt text found.")
                await message.reply("You mentioned me, but didn't provide a prompt!", mention_author=False, delete_after=10)
                return

            print(f"User prompt: '{prompt_text}'")

            # 5. Call the Gemini API
            try:
                print("Sending request to Gemini API...")
                # Prepend system prompt to user prompt
                full_prompt = f"{SYSTEM_PROMPT}\n\nUser: {prompt_text}\nAssistant:"

                response = await gemini_model.generate_content_async(
                    full_prompt # Send combined prompt
                    # Alternatively structure as a list if model prefers:
                    # [SYSTEM_PROMPT, prompt_text]
                )

                # 6. Process the response
                if response.parts:
                    gemini_reply = response.text
                    print(f"Gemini response received (length: {len(gemini_reply)})")

                    # 7. Send reply to Discord (handle length limit)
                    if len(gemini_reply) > 1990: # Discord limit is 2000, leave buffer
                        print("Response too long, sending truncated version.")
                        gemini_reply = gemini_reply[:1990] + "..."

                    await message.reply(gemini_reply, mention_author=False)

                else:
                    # Check for safety blocks or other issues
                    print(f"Gemini API returned no content. Feedback: {response.prompt_feedback}")
                    await message.reply(f"Sorry, I couldn't generate a response. It might have been blocked due to safety settings. (Feedback: {response.prompt_feedback})", mention_author=False)

            except Exception as e:
                print(f"ERROR: An error occurred calling Gemini API or sending reply: {e}")
                import traceback
                traceback.print_exc()
                try:
                    await message.reply("Sorry, an error occurred while processing your request.", mention_author=False)
                except discord.Forbidden:
                    print("ERROR: Could not send error message to Discord (Forbidden).")
                except Exception as discord_e:
                    print(f"ERROR: Could not send error message to Discord: {discord_e}")


# --- Run the Bot ---
if __name__ == "__main__":
    print("Attempting to start Gemini bot...")
    try:
        bot.run(DISCORD_TOKEN)
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