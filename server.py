import os
import asyncio
import uvicorn
from web_app import app
from tg_bot import bot, dp

async def run_all():
    port = int(os.environ.get("PORT", 8000))
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)

    await bot.delete_webhook(drop_pending_updates=True)
    print("🚀 Запуск единого сервера GyertAI (Сайт + Telegram-бот)...")
    
    await asyncio.gather(
        server.serve(),
        dp.start_polling(bot, skip_updates=True)
    )

if __name__ == "__main__":
    asyncio.run(run_all())
