# KnowledgeEngine

KnowledgeEngine is a personal note pipeline that pulls structured notes from Notion, stores them locally as Markdown, retrieves the most relevant notes for a prompt, and delivers study summaries or LinkedIn carousel drafts through Telegram.

## Features

- Export Notion database rows into a local Markdown knowledge layer
- Build a machine-readable note index for retrieval
- Retrieve relevant notes from natural-language prompts
- Send study summaries to Telegram
- Generate LinkedIn carousel drafts as HTML and deliver them in Telegram
- Run a local sync job on a recurring schedule

## Project Structure

- `notion_connection.py`: exports Notion rows into `knowledge_layer/`
- `knowledge_retriever.py`: retrieves relevant notes from the local knowledge layer
- `carousel_generator.py`: converts retrieved notes into LinkedIn carousel HTML
- `telegram_bot.py`: handles Telegram commands and orchestrates summaries or carousels
- `scripts/run_notion_sync.sh`: local runner for periodic Notion syncs

## Setup

1. Create and activate a virtual environment.
2. Install dependencies with `uv add -r requirements.txt`.
3. Copy `.env.example` to `.env` and fill in your values.
4. Run `python notion_connection.py` once to build the initial `knowledge_layer/`.
5. Start the Telegram bot with `python telegram_bot.py`.

## Telegram Commands

- `/summarize <topic>`
- `/find <topic>`
- `/carousel <topic>`

Plain-English prompts also work, for example:

- `Summarize my notes on Pomodoro Technique.`
- `Create a LinkedIn carousel on Pomodoro Technique.`

## Local Cron

Use `scripts/run_notion_sync.sh` with cron if you want automated Notion syncs. The script is safe to run daily because it self-throttles to one successful sync every 72 hours.

## Privacy

This repository is designed so local secrets, generated outputs, and the local knowledge layer stay out of git via `.gitignore`.
