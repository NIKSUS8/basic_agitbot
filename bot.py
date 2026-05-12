import asyncio
import aiohttp
import re
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

BOT_TOKEN = "8605998311:AAHFbAuSrCRndQ6KC_WCtj0rnFAry3K9qrY"

PROVIDERS = [
    {
        "name": "GPT-OSS (OpenRouter)",
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "key": "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",
        "model": "openai/gpt-oss-20b:free",
    },
    {
        "name": "Llama 70b (OpenRouter)",
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "key": "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",
        "model": "meta-llama/llama-3.3-70b-instruct:free",
    },
    {
        "name": "Google AI",
        "url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
        "key": "AIzaSyDWgaey-FLHnyjdys5Zy51M-m7JjEk25Cw",
        "model": "gemini-2.0-flash",
    },
]

SYSTEM_PROMPT = """Ты — интеллектуальный бот-помощник по теме технического прогресса и общества.
Отвечай строго на основе марксистской и социальной философии.
Используй следующие ключевые идеи:
- Прогресс не является однозначным благом или злом — его ценность зависит от социальной системы
- При капитализме техника служит прибыли и усиливает эксплуатацию
- Автоматизация без социальных гарантий создаёт безработицу
- Цифровые платформы превращают активность пользователей в неоплачиваемый труд
- Истинная цель прогресса — освобождение труда и рост свободного времени
- Пример ГДР показывает возможность планомерной модернизации в интересах большинства
Отвечай на русском языке. Будь чётким и конкретным. Не придумывай факты."""

MODE_INSTRUCTIONS = {
    "short": "Ответь очень кратко — 2-3 предложения.",
    "full": "Ответь развёрнуто — 3-4 абзаца.",
    "thesis": "Ответь списком из 5 тезисов, пронумерованных.",
    "risk": "Перечисли только риски и опасности — списком.",
    "simple": "Объясни максимально простыми словами, без терминов.",

}

def clean_markdown(text: str) -> str:
    text = re.sub(r'#{1,6}\s*', '', text)
    text = re.sub(r'\*\*(.*?)\*\*', '<b>\\1</b>', text)
    text = re.sub(r'\*(.*?)\*', '<i>\\1</i>', text)
    return text.strip()

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
user_questions = {}
DEFAULT_QUESTION = "Стоит ли поддерживать технический прогресс?"


async def ask_openrouter(provider: dict, messages: list) -> str:
    async with aiohttp.ClientSession() as session:
        async with session.post(
            provider["url"],
            headers={
                "Authorization": f"Bearer {provider['key']}",
                "Content-Type": "application/json",
            },
            json={
                "model": provider["model"],
                "messages": messages,
                "max_tokens": 1500,
            },
        ) as resp:
            text = await resp.text()
            print(f"{provider['name']} статус: {resp.status}, ответ: {text[:200]}")
            if resp.status == 200:
                data = await resp.json(content_type=None)
                return data["choices"][0]["message"]["content"]
            return None


async def ask_google(provider: dict, messages: list) -> str:
    text = "\n".join(m["content"] for m in messages if m["role"] != "system")
    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    full_text = f"{system}\n\n{text}"

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{provider['url']}?key={provider['key']}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": full_text}]}],
                "generationConfig": {"maxOutputTokens": 1500},
            },
        ) as resp:
            text_resp = await resp.text()
            print(f"Google статус: {resp.status}, ответ: {text_resp[:300]}")
            if resp.status == 200:
                data = await resp.json(content_type=None)
                return data["candidates"][0]["content"]["parts"][0]["text"]
            return None


async def ask_ai(question: str, mode: str = "full") -> str:
    instruction = MODE_INSTRUCTIONS.get(mode, MODE_INSTRUCTIONS["full"])
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"{instruction}\n\nВопрос: {question}"},
    ]

    for provider in PROVIDERS:
        try:
            if provider["name"] == "Google AI":
                result = await ask_google(provider, messages)
            else:
                result = await ask_openrouter(provider, messages)

            if result:
                print(f"Ответил: {provider['name']}")
                return clean_markdown(result)
            else:
                print(f"Пустой ответ от: {provider['name']}")

        except Exception as e:
            print(f"Исключение {provider['name']}: {type(e).__name__}: {e}")
            continue

    return "Все провайдеры недоступны. Попробуй позже."


def main_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="Кратко", callback_data="short")
    kb.button(text="Развёрнуто", callback_data="full")
    kb.button(text="Тезисы", callback_data="thesis")
    kb.button(text="Риски", callback_data="risk")
    kb.button(text="Простыми словами", callback_data="simple")
    kb.button(text="Свой вопрос", callback_data="free")
    kb.adjust(2, 2, 2)
    return kb.as_markup()


def mode_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="Кратко", callback_data="mode_short")
    kb.button(text="Развёрнуто", callback_data="mode_full")
    kb.button(text="Тезисы", callback_data="mode_thesis")
    kb.button(text="Риски", callback_data="mode_risk")
    kb.button(text="Простыми словами", callback_data="mode_simple")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "<b>Бот: Прогресс и общество</b>\n\n"
        "Здесь можно разобраться, стоит ли поддерживать технический прогресс "
        "и каковы его риски с точки зрения марксистской философии.\n\n"
        "Выбери формат ответа или напиши свой вопрос:",
        reply_markup=main_kb()
    )


@dp.callback_query(F.data.in_({"short", "full", "thesis", "risk", "simple"}))
async def cb_mode(callback: CallbackQuery):
    mode = callback.data
    question = user_questions.get(callback.from_user.id, DEFAULT_QUESTION)
    await callback.message.answer("⏳ Думаю...")
    answer = await ask_ai(question, mode)
    await callback.message.answer(answer, reply_markup=main_kb())
    await callback.answer()


@dp.callback_query(F.data == "free")
async def cb_free(callback: CallbackQuery):
    await callback.message.answer(
        "Напиши свой вопрос.\n\n"
        "Например:\n"
        "• Стоит ли поддерживать прогресс?\n"
        "• Чем опасна автоматизация?\n"
        "• Как техника связана с капитализмом?\n\n"
        "После того как напишешь — выбери формат ответа."
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("mode_"))
async def cb_mode_after_question(callback: CallbackQuery):
    mode = callback.data.replace("mode_", "")
    question = user_questions.get(callback.from_user.id, DEFAULT_QUESTION)
    await callback.message.answer("⏳ Думаю...")
    answer = await ask_ai(question, mode)
    await callback.message.answer(answer, reply_markup=main_kb())
    await callback.answer()


@dp.message(F.text)
async def free_text(message: Message):
    user_questions[message.from_user.id] = message.text
    await message.answer(
        f"Вопрос принят:\n<i>{message.text}</i>\n\nВыбери формат ответа:",
        reply_markup=mode_kb()
    )


async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
