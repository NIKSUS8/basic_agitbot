import asyncio
import aiohttp
import re
import time
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import CommandStart, Command
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# ─────────────────────────────────────────────
#  КОНФИГУРАЦИЯ
# ─────────────────────────────────────────────

BOT_TOKEN = "8605998311:AAHFbAuSrCRndQ6KC_WCtj0rnFAry3K9qrY"

PROVIDERS = [
    {
        "name": "Qwen (aikit)",
        "type": "openai",
        "url": "https://qwen.aikit.club/v1/chat/completions",
        "key": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6ImU2ZWQwYzdlLWFkM2ItNDdhYS05M2U3LWNiNjMxN2NiNWI5OSIsImxhc3RfcGFzc3dvcmRfY2hhbmdlIjoxNzc4MzYyOTE2LCJleHAiOjE3ODE2MDcyNzh9.Jstu9yX81hCLJh3OQwmekaNFimtLfIkl3DrDJoEVVwg",
        "model": "qwen-turbo",
    },
    {
        "name": "DeepSeek",
        "type": "openai",
        "url": "https://api.deepseek.com/v1/chat/completions",
        "key": "sxEjxPEmmkNQfTtSyI9Z/XAvVAggJub54dmBtKZ7fb4LVO4WaXesbFbESzfXoK/P",
        "model": "deepseek-chat",
    },
    {
        "name": "Llama 70b (OpenRouter fallback)",
        "type": "openai",
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "key": "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",
        "model": "meta-llama/llama-3.3-70b-instruct:free",
    },
]

# ─────────────────────────────────────────────
#  СИСТЕМНЫЙ ПРОМПТ
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """Ты — аналитический бот-энциклопедист. Твоя задача — помогать пользователям разбираться в вопросах истории, политической экономии, философии и общественных науках.

Принципы работы:
- Используй марксистский понятийный аппарат как инструмент анализа: классовые интересы, производственные отношения, прибавочная стоимость, исторический материализм.
- При разборе исторических событий опирайся на конкретные источники и архивные данные, а не на клише любой стороны.
- Ключевой вопрос при анализе: «Каковы материальные интересы сторон?»
- Объясняй механизмы, а не декларируй выводы. Пользователь должен понять логику, а не просто получить готовый ответ.
- Если тема дискуссионна в историографии — говори об этом прямо, указывай на разные позиции и их аргументы.
- Не придумывай факты и цитаты. Если не уверен — скажи об этом.
- Отвечай на русском языке. Будь точным и конкретным."""

# ─────────────────────────────────────────────
#  ФОРМАТЫ ОТВЕТА
# ─────────────────────────────────────────────

MODE_INSTRUCTIONS = {
    "short":  "Ответь кратко — 2–3 предложения, только суть.",
    "full":   "Ответь развёрнуто — 3–4 абзаца с аргументами и примерами.",
    "thesis": "Ответь списком из 5 пронумерованных тезисов.",
    "source": "Ответь с указанием конкретных источников, авторов, архивных данных где возможно.",
    "simple": "Объясни максимально простыми словами, без терминов, как для человека без специальной подготовки.",
    "shorts": "Преврати тему в сценарий для 45-секундного видео: хук (3 сек), основная мысль (30 сек), вопрос зрителю (12 сек). Дай текст для озвучки.",
    "script": "Сгенерируй 3 варианта скрипта разговора по этой ситуации: нейтральный (информационный), твёрдый (отстаивание позиции), короткий (быстрое решение). Добавь фразу для самонастроя перед разговором.",
}

MODE_LABELS = {
    "short":  "Кратко",
    "full":   "Развёрнуто",
    "thesis": "Тезисы",
    "source": "С источниками",
    "simple": "Простыми словами",
    "shorts": "Сценарий Shorts",
    "script": "Скрипт разговора",
}

PRAXIS_TIMEOUT = 15 * 60  # 15 минут бездействия → команда к действию

# ─────────────────────────────────────────────
#  СОСТОЯНИЕ ПОЛЬЗОВАТЕЛЕЙ
# ─────────────────────────────────────────────

user_state: dict[int, dict] = {}
# user_state[uid] = {
#   "question": str,
#   "last_active": float,
#   "praxis_warned": bool,
#   "products_this_week": int,
# }

def get_state(uid: int) -> dict:
    if uid not in user_state:
        user_state[uid] = {
            "question": "",
            "last_active": time.time(),
            "praxis_warned": False,
            "products_this_week": 0,
        }
    return user_state[uid]

def touch(uid: int):
    get_state(uid)["last_active"] = time.time()
    get_state(uid)["praxis_warned"] = False

# ─────────────────────────────────────────────
#  УТИЛИТЫ
# ─────────────────────────────────────────────

def clean_markdown(text: str) -> str:
    text = re.sub(r'#{1,6}\s*', '', text)
    text = re.sub(r'\*\*(.*?)\*\*', '<b>\\1</b>', text)
    text = re.sub(r'\*(.*?)\*', '<i>\\1</i>', text)
    text = re.sub(r'`(.*?)`', '<code>\\1</code>', text)
    return text.strip()

def praxis_check(uid: int) -> str | None:
    """Возвращает сообщение-пинок если пользователь завис, иначе None."""
    state = get_state(uid)
    elapsed = time.time() - state["last_active"]
    if elapsed > PRAXIS_TIMEOUT and not state["praxis_warned"]:
        state["praxis_warned"] = True
        return (
            "⏱ <b>Праксис-контроль:</b> ты думаешь уже больше 15 минут.\n\n"
            "Напиши прямо сейчас:\n"
            "1. Один конкретный вывод из этого разговора.\n"
            "2. Одно действие, которое сделаешь сегодня.\n"
            "3. Один продукт (пост, сценарий, тезис), который оформишь на основе этого.\n\n"
            "<i>Время пошло. Анализ продолжится после ответа.</i>"
        )
    return None

# ─────────────────────────────────────────────
#  ПРОВАЙДЕРЫ
# ─────────────────────────────────────────────

async def ask_openai_compat(provider: dict, messages: list) -> str | None:
    headers = {
        "Authorization": f"Bearer {provider['key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": provider["model"],
        "messages": messages,
        "max_tokens": 1500,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                provider["url"], headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                text = await resp.text()
                print(f"[{provider['name']}] статус={resp.status} | {text[:200]}")
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    return data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[{provider['name']}] ошибка: {type(e).__name__}: {e}")
    return None


async def ask_ai(question: str, mode: str = "full") -> str:
    instruction = MODE_INSTRUCTIONS.get(mode, MODE_INSTRUCTIONS["full"])
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"{instruction}\n\nТема / вопрос: {question}"},
    ]
    for provider in PROVIDERS:
        result = await ask_openai_compat(provider, messages)
        if result:
            print(f"[OK] Ответил: {provider['name']}")
            return clean_markdown(result)
        print(f"[FAIL] {provider['name']} — пробую следующий")
    return "⚠️ Все провайдеры недоступны. Попробуй позже."

# ─────────────────────────────────────────────
#  КЛАВИАТУРЫ
# ─────────────────────────────────────────────

def main_kb():
    kb = InlineKeyboardBuilder()
    for cb, label in MODE_LABELS.items():
        kb.button(text=label, callback_data=f"mode_{cb}")
    kb.button(text="✏️ Новый вопрос", callback_data="new_question")
    kb.button(text="📊 Аудит недели", callback_data="audit")
    kb.adjust(2, 2, 2, 2)
    return kb.as_markup()

def after_answer_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Продукт создан", callback_data="product_done")
    kb.button(text="✏️ Новый вопрос", callback_data="new_question")
    kb.button(text="🔄 Другой формат", callback_data="change_format")
    kb.adjust(2, 1)
    return kb.as_markup()

def format_kb():
    kb = InlineKeyboardBuilder()
    for cb, label in MODE_LABELS.items():
        kb.button(text=label, callback_data=f"mode_{cb}")
    kb.adjust(2, 2, 2, 1)
    return kb.as_markup()

# ─────────────────────────────────────────────
#  БОТ
# ─────────────────────────────────────────────

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


@dp.message(CommandStart())
async def cmd_start(message: Message):
    touch(message.from_user.id)
    await message.answer(
        "<b>Аналитический бот — История, экономия, философия</b>\n\n"
        "Разбираю вопросы через анализ материальных интересов и исторических механизмов.\n\n"
        "<b>Что умею:</b>\n"
        "• Объяснять понятия (прибавочная стоимость, формации, империализм и др.)\n"
        "• Анализировать исторические события с опорой на источники\n"
        "• Генерировать сценарии для видео (Shorts/Reels)\n"
        "• Составлять скрипты для сложных разговоров\n"
        "• Выдавать пинок, если ты завис в рефлексии >15 минут\n\n"
        "Напиши вопрос или тему — и выбери формат ответа.",
        reply_markup=main_kb()
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "<b>Команды:</b>\n"
        "/start — главное меню\n"
        "/audit — аудит недели\n"
        "/help — эта справка\n\n"
        "<b>Форматы ответа:</b>\n"
        "• <b>Кратко</b> — 2–3 предложения\n"
        "• <b>Развёрнуто</b> — 3–4 абзаца\n"
        "• <b>Тезисы</b> — 5 пронумерованных тезисов\n"
        "• <b>С источниками</b> — с указанием авторов и данных\n"
        "• <b>Простыми словами</b> — без терминов\n"
        "• <b>Сценарий Shorts</b> — скрипт для 45-сек видео\n"
        "• <b>Скрипт разговора</b> — 3 варианта диалога для реальной ситуации\n\n"
        "<b>Праксис-контроль:</b> если ты думаешь >15 минут без результата — бот напомнит зафиксировать вывод и действие."
    )


@dp.message(Command("audit"))
async def cmd_audit(message: Message):
    uid = message.from_user.id
    state = get_state(uid)
    products = state.get("products_this_week", 0)
    await message.answer(
        f"<b>📊 Аудит недели</b>\n\n"
        f"Продуктов создано (по твоим отметкам): <b>{products}</b>\n\n"
        f"{'✅ Хороший темп.' if products >= 2 else '⚠️ Меньше 2 продуктов за неделю. Что завершить сегодня?'}\n\n"
        "<i>Используй кнопку «Продукт создан» после каждого поста, сценария или тезисной справки.</i>"
    )


@dp.callback_query(F.data == "audit")
async def cb_audit(callback: CallbackQuery):
    await cmd_audit(callback.message)
    await callback.answer()


@dp.callback_query(F.data == "new_question")
async def cb_new_question(callback: CallbackQuery):
    touch(callback.from_user.id)
    await callback.message.answer(
        "Напиши вопрос или тему для анализа.\n\n"
        "<i>Примеры:</i>\n"
        "• Что такое прибавочная стоимость?\n"
        "• Каковы причины кризиса 1929 года?\n"
        "• Объясни роль государства при капитализме\n"
        "• Рабочий страх: завтра нужно поговорить с бригадиром об изменении графика"
    )
    await callback.answer()


@dp.callback_query(F.data == "change_format")
async def cb_change_format(callback: CallbackQuery):
    await callback.message.answer("Выбери другой формат для того же вопроса:", reply_markup=format_kb())
    await callback.answer()


@dp.callback_query(F.data == "product_done")
async def cb_product_done(callback: CallbackQuery):
    uid = callback.from_user.id
    state = get_state(uid)
    state["products_this_week"] = state.get("products_this_week", 0) + 1
    count = state["products_this_week"]
    await callback.message.answer(
        f"✅ Зафиксировано. Продуктов на этой неделе: <b>{count}</b>\n\n"
        f"{'Отличный темп — продолжай.' if count >= 2 else 'Ещё один — и недельная норма выполнена.'}"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("mode_"))
async def cb_mode(callback: CallbackQuery):
    uid = callback.from_user.id
    mode = callback.data.replace("mode_", "")
    state = get_state(uid)
    question = state.get("question", "")

    if not question:
        await callback.message.answer(
            "Сначала напиши вопрос или тему, затем выбери формат."
        )
        await callback.answer()
        return

    # Праксис-пинок если завис
    poke = praxis_check(uid)
    if poke:
        await callback.message.answer(poke)
        await callback.answer()
        return

    touch(uid)
    thinking = await callback.message.answer("⏳ Анализирую...")
    answer = await ask_ai(question, mode)
    await thinking.delete()
    await callback.message.answer(answer, reply_markup=after_answer_kb())
    await callback.answer()


@dp.message(F.text)
async def handle_text(message: Message):
    uid = message.from_user.id
    text = message.text.strip()
    state = get_state(uid)
    state["question"] = text
    touch(uid)

    await message.answer(
        f"Вопрос принят:\n<i>{text}</i>\n\nВыбери формат ответа:",
        reply_markup=format_kb()
    )


# ─────────────────────────────────────────────
#  ЗАПУСК
# ─────────────────────────────────────────────

async def main():
    print("Бот запущен.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
