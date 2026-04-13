import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from carousel_generator import generate_carousel_artifact
from knowledge_retriever import KnowledgeRetriever, RetrievalResult


project_root = Path(__file__).resolve().parent
load_dotenv(project_root / ".env")

telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
openai_api_key = os.getenv("OPENAI_API_KEY")
openai_model = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")

retriever = KnowledgeRetriever(project_root / "knowledge_layer")
openai_client = OpenAI(api_key=openai_api_key) if openai_api_key else None

HELP_TEXT = "\n".join(
    [
        "Send a note request in plain English, for example:",
        '"Summarize my notes on Pomodoro Technique."',
        '"Create a LinkedIn carousel on Pomodoro Technique."',
        "",
        "Supported commands:",
        "/summarize <topic>",
        "/carousel <topic>",
        "/find <topic>",
        "/help",
    ]
)


def is_carousel_request(text: str) -> bool:
    normalized = text.lower()
    return "carousel" in normalized or "linkedin" in normalized


def build_fallback_response(result: RetrievalResult) -> str:
    lines = [f"Top notes for: {result.topic}", ""]
    for note in result.matches:
        lines.extend(
            [
                f"{note.title}",
                f"Summary: {note.excerpt or note.body[:220]}",
                f"Source file: {note.path.name}",
                "",
            ]
        )

    return "\n".join(lines).strip()


def generate_openai_summary(result: RetrievalResult) -> str:
    if openai_client is None:
        return build_fallback_response(result)

    prompt = "\n\n".join(
        [
            f"User request: {result.request}",
            f"Resolved topic: {result.topic}",
            "Use only the retrieved notes below. If the notes are partial, say so instead of inventing details.",
            result.as_prompt_context(),
        ]
    )

    system_prompt = (
        "You are a study assistant. Produce a concise revision-friendly answer. "
        "Return: 1) a short summary, 2) 3 key takeaways, 3) source note titles used."
    )

    response = openai_client.chat.completions.create(
        model=openai_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        max_completion_tokens=500,
    )
    message = response.choices[0].message.content or ""
    if message:
        return message.strip()

    return build_fallback_response(result)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    await update.message.reply_text(HELP_TEXT)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    await update.message.reply_text(HELP_TEXT)


async def summarize_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    topic = " ".join(context.args or []).strip()
    if not topic:
        await update.message.reply_text("Usage: /summarize <topic>")
        return

    await handle_summary_request(update, f"Summarize my notes on {topic}")


async def carousel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    topic = " ".join(context.args or []).strip()
    if not topic:
        await update.message.reply_text("Usage: /carousel <topic>")
        return

    await handle_carousel_request(update, f"Create a LinkedIn carousel on {topic}")


async def find_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    topic = " ".join(context.args or []).strip()
    if not topic:
        await update.message.reply_text("Usage: /find <topic>")
        return

    result = retriever.retrieve(topic)
    if not result.matches:
        await update.message.reply_text(f'No notes matched "{topic}".')
        return

    lines = [f"Matches for: {result.topic}", ""]
    for note in result.matches:
        lines.append(f"- {note.title} ({note.path.name})")

    await update.message.reply_text("\n".join(lines))


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or not update.message.text:
        return
    if is_carousel_request(update.message.text):
        await handle_carousel_request(update, update.message.text)
        return

    await handle_summary_request(update, update.message.text)


async def handle_summary_request(update: Update, request_text: str) -> None:
    if update.message is None:
        return

    await context_safe_chat_action(update)
    result = retriever.retrieve(request_text)

    if not result.matches:
        await update.message.reply_text(
            "I could not find a matching note in the knowledge layer. Try a more specific topic."
        )
        return

    try:
        response_text = await asyncio.to_thread(generate_openai_summary, result)
    except Exception:
        response_text = build_fallback_response(result)

    await update.message.reply_text(response_text)


async def handle_carousel_request(update: Update, request_text: str) -> None:
    if update.message is None:
        return

    await context_safe_chat_action(update)
    result = retriever.retrieve(request_text)

    if not result.matches:
        await update.message.reply_text(
            "I could not find a matching note for that carousel request. Try a more specific topic."
        )
        return

    try:
        artifact = await asyncio.to_thread(
            generate_carousel_artifact,
            result,
            openai_client,
            openai_model,
            project_root / "generated_carousels",
        )
    except Exception:
        await update.message.reply_text(
            "Carousel generation failed. Check the bot terminal for the detailed error."
        )
        raise

    await update.message.reply_text(
        f"Built a {artifact.slide_count}-slide LinkedIn carousel draft for {result.topic}. Review the attached HTML file in a browser before posting."
    )
    with artifact.path.open("rb") as document:
        await update.message.reply_document(
            document=document,
            filename=artifact.path.name,
            caption=artifact.caption[:1024],
        )


async def context_safe_chat_action(update: Update) -> None:
    if update.effective_chat is None or update.get_bot() is None:
        return
    await update.get_bot().send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING,
    )


def main() -> None:
    if not telegram_bot_token:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN in .env at the workspace root.")

    application = Application.builder().token(telegram_bot_token).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("summarize", summarize_command))
    application.add_handler(CommandHandler("carousel", carousel_command))
    application.add_handler(CommandHandler("find", find_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    application.run_polling()


if __name__ == "__main__":
    main()
