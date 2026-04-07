# Detailed Setup Guide (Onboarding) 🚀

Welcome! If you are here, it means you want to launch your personal financial AI assistant on Telegram.
This document is a highly detailed, step-by-step tutorial for beginners. We will cover everything from creating a bot to configuring Google Cloud and AI models.

---

## 🗺️ How does the bot work? (Briefly)

1. You send a text message to the bot in **Telegram** (e.g., *"Spent 5 $ on coffee and 15 on groceries"*).
2. The bot sends your text to **OpenRouter** (an AI aggregator where the smart agent runs).
3. The AI understands your expenses, categorizes them, and returns structured data.
4. The bot records this data into your personal **Google Spreadsheet** (Google Sheets).

To achieve this, we need to link these three services together.

---

## Step 1: Create a Telegram Bot and get your ID

We need to create the bot itself and find out your personal ID so that strangers cannot write expenses into your spreadsheet.

### 1.1 Get the bot token
1. Open Telegram and search for **@BotFather** (with a blue tick).
2. Click `Start` (or type `/start`).
3. Send the command `/newbot`.
4. BotFather will ask you to think of a **name** (e.g., `My Financier`).
5. Then it will ask for a **username** — it must end in `_bot` or `Bot` (e.g., `Ivan_FinanceBot`).
6. In reply, you will receive a long message. Find the string that looks like this: `1234567890:AAH_XXXXXXXXXXXXXXX` — this is your **TELEGRAM_BOT_TOKEN**. Copy it and save it somewhere safe (like a notepad).

### 1.2 Find out your Telegram ID
1. In the Telegram search, find a bot like **@userinfobot** or **@GetIDs Bot**.
2. Click `Start`.
3. The bot will send you a message with your ID (a number, e.g., `123456789`).
4. Copy it — this will be your **ALLOWED_USERS** (so that only you can use your bot).

---

## Step 2: Set up Google Cloud and Google Sheets 🔥

*This is the most complex but most important step. Pay attention.*
The bot cannot simply modify any of your spreadsheets. It needs a special invisible robot account (Service Account), and you will grant it access to a specific spreadsheet.

### 2.1 Create a project and enable APIs
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Log in to your Google account and go to the console.
3. In the top left corner (next to the Google Cloud logo), click **"Select a project"** -> click **"New Project"**.
4. Name it, e.g., `FinanceBot`. Click **Create**.
5. Wait a few seconds for the project to be created, then select it.
6. In the left sidebar, find **APIs & Services** -> **Library**.
7. In the search bar, type `Google Sheets API`. Select it and click **Enable**.
8. Go back to the **Library**, type `Google Drive API` and also click **Enable**. *(Without the Drive API, the bot won't be able to find and interact with spreadsheets properly).*

### 2.2 Create a Service Account (Bot account)
1. Go back to the sidebar and select **APIs & Services** -> **Credentials**.
2. Click the blue **+ CREATE CREDENTIALS** button at the top.
3. Select **Service account**.
4. Set a name, e.g., `bot-sheets`. Click **Create and Continue**.
5. You can skip steps 2 and 3 (leave them empty). Just click **Done**.

### 2.3 Get the `credentials.json` key file
1. You will return to the Credentials page. At the bottom, under **Service Accounts**, you will see your newly created account. Click on its Email (it looks like `bot-sheets@financebot-123.iam.gserviceaccount.com`).
2. At the top, switch to the **KEYS** tab.
3. Click **Add Key** -> **Create new key**.
4. Choose the **JSON** format and click **Create**.
5. The file will automatically download to your computer! **Rename this file strictly to `credentials.json`** and place it in the project folder (in the project root).

### 2.4 CRITICAL: Grant the bot access to the Spreadsheet
Your service account has an email address (you saw it in step 2.3).
1. Open Google Sheets using your regular account.
2. Create a new spreadsheet (or open the one where you want your expenses recorded). Note its EXACT title (e.g., `Finance Tracker`).
3. Click the green **"Share"** button in the top right corner.
4. Paste the email of your service account (e.g., `bot-sheets@financebot-12345.iam.gserviceaccount.com`) and give it **"Editor"** rights.
5. Click Send/Share. That's it! Now the bot can write to this spreadsheet.

---

## Step 3: Set up the AI (OpenRouter) 🧠

We use OpenRouter because it provides access to dozens of AI models (GPT-4, Claude, Gemini, etc.) through a single API key, and many good models are entirely free.

1. Sign up at [OpenRouter.ai](https://openrouter.ai/).
2. Go to the **Keys** section ([open link](https://openrouter.ai/keys)).
3. Click **Create Key**. Enter any name (e.g., `FinanceBot`) and create it.
4. A long key will appear: `sk-or-v1-xxxxxxxxxxxx...`. **Copy it immediately**, it is only shown once! This is your **OPENROUTER_API_KEY**.

> **Which model should I choose?**
> The bot uses `openai/gpt-4o-mini` by default (it's fast, smart, and cheap).
> If you want a fully **free** model without adding a credit card, you can use: `google/gemini-2.5-flash` or `meta-llama/llama-3-8b-instruct:free`.

---

## Step 4: Run the project (Deploying) 💻

Now we put everything together on your computer or server. You need to have Python installed (version 3.10 or higher).

### 4.1. Prepare the folder
1. Open the terminal (or command prompt).
2. Navigate to the project folder: `cd path/to/folder/finance-bot`
3. Create a virtual environment: `python -m venv venv`
4. Activate it:
   - Mac/Linux: `source venv/bin/activate`
   - Windows: `venv\Scripts\activate`
5. Install dependencies: `pip install -r requirements.txt`

### 4.2. Configure the `.env` environment variables file
1. In the project folder, create a file named `.env` (just a dot and env) or copy from the template `cp .env.example .env`.
2. Open `.env` in any text editor.
3. Fill it with the data we collected in the previous steps:

```env
# Telegram bot token from Step 1
TELEGRAM_BOT_TOKEN=1234567890:AAH_xxxxxxxxxxxxx

# AI Key from Step 3
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxx

# Your model (recommended free one)
AI_MODEL=google/gemini-2.5-flash 

# Keys filename (downloaded in Step 2)
GOOGLE_CREDENTIALS_FILE=credentials.json

# Your Google Sheets spreadsheet title (where you granted access)
SPREADSHEET_NAME=Finance Tracker

# Default currency (e.g., USD, EUR, RUB)
CURRENCY=USD

# Your Telegram ID from Step 1 (so the bot ignores other people)
ALLOWED_USERS=123456789

# (Optional) Voice message support
TRANSCRIBE_API_KEY=sk-xxxxxxxxxxxxxxxx
TRANSCRIBE_MODEL=whisper-1
VOICE_DIRECT_MODE=false
VOICE_DIRECT_MODEL=google/gemini-2.5-flash
DOCUMENT_MODEL=google/gemini-2.5-flash
```

*Make sure that the `credentials.json` file is placed in the project root next to `.env`!*

### 4.3. Run it!
In your terminal, type:
```bash
python -m app
```
If everything is done correctly, there will be no red errors in the terminal, and the bot will start replying to your commands in Telegram (send it `/start` or just type "bought a coffee for 2 dollars").

If you close your terminal, the bot will stop working. To make it run 24/7, proceed to Step 5.

---

## Step 5: How to run the bot 24/7 for free (Deploy to Railway) ☁️

**Railway** is a cloud hosting service. We have specifically prepared our codebase so you can deploy your bot in just a few clicks without technical hassle!

1. Sign up at **[Railway.app](https://railway.app)** (you can use your GitHub account).
2. Click **New Project** -> **Deploy from GitHub repo** and select your copy of the bot repository (make sure you've forked the original repo).
3. Railway will download your code and try to run it.
4. **Important:** The bot will crash on the first run because it doesn't have your keys yet.
5. In the Railway dashboard, open your started service (`findo-bot`), and go to the **Variables** tab.
6. Create all variables from your local `.env` file (Token, API Key, Spreadsheet Name, Model).
7. **What about `credentials.json`?** 
   You shouldn't upload password files to the cloud repo directly. Create a special variable called **`GOOGLE_CREDENTIALS_JSON`**. Open your local `credentials.json` file in a text editor, copy **ALL** of its text (including the `{ }` brackets), and paste it into the value of this new variable.
8. Once you save all variables, Railway will automatically restart the build, and your bot will come alive 24/7!

---

## What to do if something doesn't work? (Common Issues)

1. **The bot ignores my messages:**
   Check if you entered your ID correctly into `ALLOWED_USERS` in the `.env` file. If you started the bot before adding your ID, restart it (`Ctrl+C` in the terminal, then run `python -m app` again).

2. **`SpreadsheetNotFound` error or the bot can't find the spreadsheet:**
   You forgot to share the spreadsheet with the service email (see **Step 2.4**). Make sure the spreadsheet title in `.env` (`SPREADSHEET_NAME`) matches letter-for-letter exactly what it is in Google Sheets.

3. **`File credentials.json not found` error:**
   You didn't put the keys file from Google Cloud into your project folder, or you named it differently (e.g., `project-keys-123.json`). Rename it strictly to `credentials.json`.

4. **The bot reports an OpenRouter / API error:**
   You run out of balance/limits (if using a paid model) or the `OPENROUTER_API_KEY` is incorrect. Change the `AI_MODEL` to a free one, like `google/gemini-2.5-flash`.

---

🎉 **Done!** Your personal finance assistant is now running.
You can type messages to it, and it will automatically categorize expenses and build beautiful analytics in your spreadsheet. Stay wealthy and financially savvy! 💸
