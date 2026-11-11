import os
import sys
import subprocess

def main():
    print("=========================================")
    print("   🚀 GYERT STATION — ЕДИНЫЙ ПУЛЬТ       ")
    print("=========================================")
    print("1. 💻 Запустить программу для Windows (Desktop OS)")
    print("2. 🌐 Запустить Веб-сферу для проектора (GyertStation Web)")
    print("3. 🤖 Запустить Telegram-бота (GyertAI Bot)")
    print("=========================================")
    
    choice = input("Выберите режим (1, 2 или 3): ").strip()
    if choice == "1":
        subprocess.run([sys.executable, "desktop_app.py"])
    elif choice == "2":
        print("\n🌍 Откройте в браузере: http://localhost:8000")
        subprocess.run([sys.executable, "web_app.py"])
    elif choice == "3":
        subprocess.run([sys.executable, "tg_bot.py"])
    else:
        print("Неверный выбор!")

if __name__ == "__main__":
    main()
