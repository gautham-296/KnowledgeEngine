import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any

from knowledge_retriever import RetrievalResult


@dataclass(slots=True)
class CarouselArtifact:
    title: str
    path: Path
    caption: str
    slide_count: int


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "carousel"


def compact_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def split_sentences(text: str) -> list[str]:
    cleaned = compact_whitespace(text)
    if not cleaned:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", cleaned) if part.strip()]


def extract_json_object(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model output")
    return json.loads(text[start : end + 1])


def fallback_carousel_spec(result: RetrievalResult) -> dict[str, Any]:
    primary = result.matches[0]
    primary_sentences = split_sentences(primary.body or primary.excerpt)
    supporting = [note for note in result.matches[1:]]
    support_sentences = []
    for note in supporting:
        support_sentences.extend(split_sentences(note.body or note.excerpt))

    first_sentence = primary_sentences[0] if primary_sentences else primary.excerpt or primary.title
    second_sentence = primary_sentences[1] if len(primary_sentences) > 1 else "Work in focused sprints instead of waiting for perfect motivation."
    third_sentence = primary_sentences[2] if len(primary_sentences) > 2 else "Repeat the cycle until the task is done."

    slides = [
        {
            "eyebrow": "LinkedIn Carousel",
            "headline": f"{result.topic}: a practical system for better focus",
            "bullets": [
                "Turn scattered attention into a repeatable routine.",
                "Use short work intervals to make starting easier.",
                "Build momentum without burning out.",
            ],
            "footer": "Based on your note library",
        },
        {
            "eyebrow": "Why It Matters",
            "headline": "This method works because it lowers the friction of starting",
            "bullets": [first_sentence, second_sentence],
            "footer": primary.title,
        },
        {
            "eyebrow": "Core Method",
            "headline": "Run the Pomodoro loop with a timer and one clear task",
            "bullets": [
                third_sentence,
                "Choose one task, remove distractions, and commit to the sprint.",
                "When attention drifts, reset and continue instead of restarting the day.",
            ],
            "footer": "Keep the workflow simple enough to repeat",
        },
        {
            "eyebrow": "Execution",
            "headline": "Treat each sprint as a focused unit of progress",
            "bullets": [
                "Work deeply for the session you planned.",
                "Take a short recovery break immediately after the sprint.",
                "After several rounds, take a bigger break to reset.",
            ],
            "footer": supporting[0].title if supporting else primary.title,
        },
        {
            "eyebrow": "Common Mistakes",
            "headline": "What weakens the method",
            "bullets": [
                "Trying to multitask during the sprint.",
                "Letting interruptions erase your progress state.",
                "Skipping breaks and turning the routine into a grind.",
            ],
            "footer": "Protect the structure if you want the result",
        },
        {
            "eyebrow": "Takeaway",
            "headline": "Use structure to make consistency easier than procrastination",
            "bullets": [
                "Start small, focus hard, rest deliberately.",
                "Repeat often enough that concentration becomes a habit.",
                support_sentences[0] if support_sentences else "Refine the method based on what your work actually demands.",
            ],
            "footer": "Save this as a review card before your next deep-work block",
        },
    ]

    return {
        "title": f"{result.topic}: a simple system for focused work",
        "theme": "editorial-focus",
        "audience": "LinkedIn professionals and students",
        "slides": slides,
        "caption": (
            f"A concise LinkedIn carousel built from notes on {result.topic}. "
            "Useful if you want a practical way to start work, focus better, and reduce procrastination."
        ),
        "hashtags": ["#Productivity", "#Learning", "#DeepWork", "#LinkedInCarousel"],
    }


def generate_carousel_spec(
    result: RetrievalResult,
    openai_client: Any,
    model: str,
) -> dict[str, Any]:
    if openai_client is None:
        return fallback_carousel_spec(result)

    prompt = "\n\n".join(
        [
            f"User request: Create a LinkedIn carousel about {result.topic}.",
            "Use only the retrieved note content below.",
            "Create a 6-slide carousel for LinkedIn.",
            "Return a JSON object with keys: title, theme, audience, slides, caption, hashtags.",
            "Each slide must contain: eyebrow, headline, bullets, footer.",
            "Each slide bullets field must be an array of 2 to 3 short bullets.",
            "Keep the writing crisp, practical, and suitable for professionals.",
            "Do not invent facts that are not present in the notes.",
            result.as_prompt_context(),
        ]
    )

    system_prompt = (
        "You create LinkedIn carousel copy from study notes. "
        "Return only valid JSON with no markdown fences."
    )

    response = openai_client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        max_completion_tokens=1200,
    )
    message = response.choices[0].message.content or ""
    if not message:
        return fallback_carousel_spec(result)

    try:
        spec = extract_json_object(message)
    except Exception:
        return fallback_carousel_spec(result)

    if not isinstance(spec.get("slides"), list) or not spec["slides"]:
        return fallback_carousel_spec(result)

    return spec


def render_carousel_html(spec: dict[str, Any], result: RetrievalResult) -> str:
    title = str(spec.get("title") or f"{result.topic} carousel")
    caption = str(spec.get("caption") or "")
    hashtags = spec.get("hashtags") or []
    slides = spec.get("slides") or []
    slide_markup: list[str] = []
    palette = ["sand", "ink", "teal", "clay", "paper", "forest"]

    for index, raw_slide in enumerate(slides, start=1):
        bullets = raw_slide.get("bullets") or []
        bullet_items = "".join(
            f"<li>{escape(str(bullet))}</li>" for bullet in bullets[:3]
        )
        palette_name = palette[(index - 1) % len(palette)]
        slide_markup.append(
            f"""
            <section class=\"slide theme-{palette_name}\">
              <div class=\"frame\">
                <div class=\"slide-top\">
                  <p class=\"eyebrow\">{escape(str(raw_slide.get('eyebrow') or 'LinkedIn Carousel'))}</p>
                  <span class=\"page-no\">{index:02d}</span>
                </div>
                <div class=\"slide-body\">
                  <h2>{escape(str(raw_slide.get('headline') or title))}</h2>
                  <ul>{bullet_items}</ul>
                </div>
                <div class=\"slide-bottom\">
                  <p>{escape(str(raw_slide.get('footer') or result.topic))}</p>
                  <p class=\"brand\">KnowledgeEngine</p>
                </div>
              </div>
            </section>
            """.strip()
        )

    source_list = "".join(
        f"<li>{escape(note.title)}</li>" for note in result.matches
    )
    hashtags_text = " ".join(str(tag) for tag in hashtags)

    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{escape(title)}</title>
  <style>
    :root {{
      --ink: #162025;
      --sand: #f3e8d4;
      --paper: #fbf7ef;
      --teal: #2d7a73;
      --clay: #c96f4a;
      --forest: #2f5d50;
      --gold: #d2a33a;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "IBM Plex Sans", "Aptos", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(210, 163, 58, 0.16), transparent 28%),
        linear-gradient(180deg, #efe4cf 0%, #f7f2e7 100%);
      padding: 32px;
    }}
    .intro {{
      max-width: 1100px;
      margin: 0 auto 28px;
      background: rgba(251, 247, 239, 0.82);
      backdrop-filter: blur(8px);
      border: 1px solid rgba(22, 32, 37, 0.08);
      border-radius: 28px;
      padding: 28px 32px;
      box-shadow: 0 24px 80px rgba(22, 32, 37, 0.08);
    }}
    .intro h1 {{
      margin: 0 0 12px;
      font-family: "Fraunces", "Georgia", serif;
      font-size: 40px;
      line-height: 1.05;
      letter-spacing: -0.04em;
    }}
    .intro p {{ margin: 0 0 8px; font-size: 16px; line-height: 1.6; }}
    .deck {{
      display: grid;
      gap: 28px;
      justify-content: center;
    }}
    .slide {{
      width: 1080px;
      min-height: 1350px;
      border-radius: 40px;
      padding: 24px;
      position: relative;
      overflow: hidden;
      box-shadow: 0 30px 90px rgba(22, 32, 37, 0.14);
    }}
    .frame {{
      height: 100%;
      border-radius: 28px;
      border: 1px solid rgba(22, 32, 37, 0.08);
      background: rgba(255,255,255,0.72);
      padding: 44px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      position: relative;
      z-index: 1;
    }}
    .slide::before {{
      content: "";
      position: absolute;
      inset: 0;
      background:
        linear-gradient(145deg, rgba(255,255,255,0.42), transparent 42%),
        radial-gradient(circle at 85% 15%, rgba(255,255,255,0.42), transparent 22%),
        repeating-linear-gradient(135deg, rgba(22,32,37,0.025) 0, rgba(22,32,37,0.025) 2px, transparent 2px, transparent 16px);
    }}
    .theme-sand {{ background: linear-gradient(180deg, #ead9bb 0%, #f5eedf 100%); }}
    .theme-ink {{ background: linear-gradient(180deg, #20343b 0%, #30474d 100%); color: #f8f3e9; }}
    .theme-ink .frame {{ background: rgba(20, 25, 29, 0.30); border-color: rgba(248,243,233,0.12); }}
    .theme-ink .brand, .theme-ink .page-no, .theme-ink .eyebrow, .theme-ink li, .theme-ink h2, .theme-ink .slide-bottom p {{ color: #f8f3e9; }}
    .theme-teal {{ background: linear-gradient(180deg, #a6d2cb 0%, #eaf6f4 100%); }}
    .theme-clay {{ background: linear-gradient(180deg, #e8b19a 0%, #fff1e7 100%); }}
    .theme-paper {{ background: linear-gradient(180deg, #f5f0e7 0%, #ffffff 100%); }}
    .theme-forest {{ background: linear-gradient(180deg, #99b8aa 0%, #edf5f1 100%); }}
    .slide-top, .slide-bottom {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
    }}
    .eyebrow, .page-no, .slide-bottom p {{
      margin: 0;
      font-size: 20px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      opacity: 0.8;
    }}
    .slide-body {{ padding: 48px 0; }}
    .slide-body h2 {{
      margin: 0 0 32px;
      font-family: "Fraunces", "Georgia", serif;
      font-size: 86px;
      line-height: 0.98;
      letter-spacing: -0.05em;
      max-width: 900px;
    }}
    .slide-body ul {{
      margin: 0;
      padding-left: 28px;
      display: grid;
      gap: 22px;
      max-width: 860px;
      font-size: 34px;
      line-height: 1.3;
      font-weight: 500;
    }}
    .brand {{ font-weight: 700; }}
    .meta {{
      max-width: 1100px;
      margin: 28px auto 0;
      display: grid;
      gap: 8px;
      font-size: 15px;
      color: rgba(22, 32, 37, 0.88);
    }}
    .meta ul {{ margin: 0; padding-left: 20px; }}
    @media print {{
      body {{ background: #fff; padding: 0; }}
      .intro, .meta {{ display: none; }}
      .deck {{ gap: 0; }}
      .slide {{ box-shadow: none; border-radius: 0; page-break-after: always; }}
    }}
  </style>
</head>
<body>
  <section class=\"intro\">
    <h1>{escape(title)}</h1>
    <p>{escape(caption)}</p>
    <p><strong>How to review:</strong> open this file in a browser, review slide copy, then export to PDF or capture each slide as an image for LinkedIn posting.</p>
  </section>
  <main class=\"deck\">
    {''.join(slide_markup)}
  </main>
  <section class=\"meta\">
    <p><strong>Suggested caption:</strong> {escape(caption)}</p>
    <p><strong>Suggested hashtags:</strong> {escape(hashtags_text)}</p>
    <div>
      <strong>Source notes used:</strong>
      <ul>{source_list}</ul>
    </div>
  </section>
</body>
</html>
"""


def generate_carousel_artifact(
    result: RetrievalResult,
    openai_client: Any,
    model: str,
    output_dir: Path,
) -> CarouselArtifact:
    output_dir.mkdir(parents=True, exist_ok=True)
    spec = generate_carousel_spec(result, openai_client, model)
    html = render_carousel_html(spec, result)
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    filename = f"linkedin-carousel-{slugify(result.topic)}-{timestamp}.html"
    path = output_dir / filename
    path.write_text(html, encoding="utf-8")
    caption = str(spec.get("caption") or f"LinkedIn carousel draft for {result.topic}")
    slides = spec.get("slides") or []
    return CarouselArtifact(
        title=str(spec.get("title") or result.topic),
        path=path,
        caption=caption,
        slide_count=len(slides),
    )
