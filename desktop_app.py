import os
import sys

# Установленное приложение живёт в Program Files, куда писать нельзя, поэтому
# база памяти и временные аудиофайлы хранятся в профиле пользователя.
if getattr(sys, "frozen", False):
    _data_dir = os.path.join(
        os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "GyertAI"
    )
    os.makedirs(_data_dir, exist_ok=True)
    os.chdir(_data_dir)

import uuid
import asyncio
import threading
import queue
import webbrowser
import tkinter as tk
import customtkinter as ctk
import sounddevice as sd
import soundfile as sf
import numpy as np
import pygame
from PIL import Image
from ai_core import (
    ask_gyert,
    image_url,
    speech_to_text,
    text_to_speech,
    clear_history,
    logo_path,
)

pygame.mixer.init()

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# --- Палитра GyertAI: та же, что на сайте gyertai.onrender.com ---
C_BG = "#05070d"
C_PANEL = "#0b101a"
C_PANEL_2 = "#121a28"
C_PANEL_3 = "#1c2740"
C_BORDER = "#1e293b"
C_LINE = "#16233a"
C_ACCENT = "#22d3ee"
C_TEXT = "#e6edf7"
C_MUTED = "#7b8aa3"
C_FAINT = "#3f4b60"
C_USER = "#0ea5e9"
C_USER_TEXT = "#f0f9ff"
C_AI = "#e6edf7"
C_DANGER = "#f43f5e"

MONO = "Consolas"
UI = "Segoe UI"

# Логотип: PNG с прозрачным фоном, тот же файл, что на сайте и в боте.
LOGO_FILE = logo_path()

# Контакт поддержки: тот же, что в Telegram и на сайте.
SUPPORT_URL = "https://t.me/skyp_t0n"
SUPPORT_HANDLE = "@skyp_t0n"

HELP_TEXT = "\n".join([
    "GyertAI — команды и поддержка",
    "",
    "/draw описание — нарисовать картинку, например /draw закат над городом",
    "🎙 у поля ввода — голосовое общение",
    "🔊 Голосовые ответы — ползунок в строке ниже: ответ приходит голосовым сообщением",
    "🧹 Очистить — сбросить память диалога",
    "",
    f"Поддержка: {SUPPORT_HANDLE} — {SUPPORT_URL}",
    "Пишите туда, если возникла ошибка или вопрос по подписке.",
])

# Цвет статуса в нижней HUD-строке — по состоянию ядра.
STATUS_COLORS = {
    "idle": C_ACCENT,
    "listening": "#fb7185",
    "thinking": "#c084fc",
    "speaking": "#34d399",
}


class GyertDesktopApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("GyertAI — Desktop")
        self.geometry("680x900")
        self.minsize(600, 760)
        self.configure(fg_color=C_BG)

        self.session_id = "windows_desktop_user"
        self.is_recording = False
        self.is_busy = False
        self.audio_frames = []
        self.sample_rate = 16000
        # Ползунок «голосовые ответы»: включён — ответ приходит голосовым сообщением.
        self.voice_replies = False

        # Очередь сообщений из рабочих потоков: tkinter нельзя трогать не из главного.
        self._ui_queue = queue.Queue()
        self._row_index = 0

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_topbar()
        self._build_chat()
        self._build_composer()

        self.after(60, self._drain_ui_queue)

    # ---------- Интерфейс ----------

    def _build_topbar(self):
        bar = ctk.CTkFrame(self, fg_color=C_PANEL, corner_radius=0)
        bar.grid(row=0, column=0, sticky="ew")
        bar.grid_columnconfigure(0, weight=1)

        inner = ctk.CTkFrame(bar, fg_color="transparent")
        inner.grid(row=0, column=0, sticky="ew", padx=18, pady=12)
        inner.grid_columnconfigure(0, weight=1)

        brand = ctk.CTkFrame(inner, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="w")

        logo = self._load_logo()
        if logo is not None:
            self._logo_image = logo
            ctk.CTkLabel(brand, image=logo, text="").pack(side="left", padx=(0, 12))

        names = ctk.CTkFrame(brand, fg_color="transparent")
        names.pack(side="left")
        ctk.CTkLabel(
            names, text="GYERT AI", font=ctk.CTkFont(family=MONO, size=20, weight="bold"),
            text_color=C_ACCENT
        ).pack(anchor="w")
        ctk.CTkLabel(
            names, text="ИИ-ЯДРО  ·  ЭКОСИСТЕМА GYERT",
            font=ctk.CTkFont(family=MONO, size=9), text_color=C_MUTED
        ).pack(anchor="w")

        buttons = ctk.CTkFrame(inner, fg_color="transparent")
        buttons.grid(row=0, column=1, sticky="e")

        ctk.CTkButton(
            buttons, text="🧹  Очистить", height=32, corner_radius=16, width=118,
            fg_color=C_PANEL_2, hover_color=C_PANEL_3, text_color=C_MUTED,
            border_width=1, border_color=C_BORDER,
            font=ctk.CTkFont(family=MONO, size=11, weight="bold"),
            command=self.on_clear
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            buttons, text="🆘  Support", height=32, corner_radius=16, width=112,
            fg_color=C_PANEL_2, hover_color=C_PANEL_3, text_color=C_MUTED,
            border_width=1, border_color=C_BORDER,
            font=ctk.CTkFont(family=MONO, size=11, weight="bold"),
            command=lambda: webbrowser.open(SUPPORT_URL)
        ).pack(side="left")

        # Тонкая светящаяся линия под шапкой — как на сайте
        ctk.CTkFrame(bar, height=1, fg_color=C_LINE).grid(row=1, column=0, sticky="ew")

    def _build_chat(self):
        self.chat_area = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        self.chat_area.grid(row=1, column=0, sticky="nsew", padx=12, pady=(14, 6))
        self.chat_area.grid_columnconfigure(0, weight=1)

        self._add_bubble(
            "Привет! Я GyertAI. Задайте любой вопрос текстом, нажмите 🎙 у поля ввода "
            "для голосового общения или нарисуйте картинку командой /draw.",
            "ai"
        )

    def _build_composer(self):
        composer = ctk.CTkFrame(self, fg_color=C_PANEL, corner_radius=0)
        composer.grid(row=2, column=0, sticky="ew")
        composer.grid_columnconfigure(0, weight=1)

        ctk.CTkFrame(composer, height=1, fg_color=C_LINE).grid(row=0, column=0, sticky="ew")

        hud = ctk.CTkFrame(composer, fg_color="transparent")
        hud.grid(row=1, column=0, sticky="ew", padx=20, pady=(10, 6))
        hud.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            hud, text="● СИСТЕМА ОНЛАЙН   ·   /DRAW ОПИСАНИЕ — КАРТИНКА   ·   /HELP — КОМАНДЫ",
            font=ctk.CTkFont(family=MONO, size=8), text_color=C_FAINT
        ).grid(row=0, column=0, sticky="w")

        self.status_label = ctk.CTkLabel(
            hud, text="🎙 ГОЛОСОВОЙ РЕЖИМ",
            font=ctk.CTkFont(family=MONO, size=8, weight="bold"), text_color=C_ACCENT
        )
        self.status_label.grid(row=0, column=2, sticky="e")

        # Ползунок голосовых ответов — как на сайте: ответ приходит голосовым, без автоплея.
        self.voice_switch = ctk.CTkSwitch(
            hud, text="🔊 ГОЛОСОВЫЕ ОТВЕТЫ",
            font=ctk.CTkFont(family=MONO, size=8, weight="bold"),
            text_color=C_MUTED, progress_color=C_ACCENT,
            button_color=C_FAINT, button_hover_color=C_ACCENT,
            fg_color=C_PANEL_3, width=42, command=self._on_voice_toggle
        )
        self.voice_switch.grid(row=0, column=1, sticky="e", padx=(0, 16))
        self.voice_switch.deselect()

        pill = ctk.CTkFrame(
            composer, fg_color=C_PANEL_2, corner_radius=24,
            border_width=1, border_color=C_BORDER
        )
        pill.grid(row=2, column=0, sticky="ew", padx=20)
        pill.grid_columnconfigure(0, weight=1)

        self.entry = ctk.CTkEntry(
            pill, placeholder_text="Напишите сообщение или команду /draw...", height=44,
            corner_radius=0, border_width=0, fg_color="transparent",
            text_color=C_TEXT, font=ctk.CTkFont(family=UI, size=14)
        )
        self.entry.grid(row=0, column=0, sticky="ew", padx=(18, 8), pady=4)
        self.entry.bind("<Return>", lambda e: self.on_send_text())

        self.mic_btn = ctk.CTkButton(
            pill, text="🎙", width=40, height=40, corner_radius=20,
            fg_color=C_PANEL_3, hover_color=C_ACCENT, text_color=C_TEXT,
            font=ctk.CTkFont(family=UI, size=15),
            command=self.toggle_recording
        )
        self.mic_btn.grid(row=0, column=1, padx=(0, 6))

        self.send_btn = ctk.CTkButton(
            pill, text="➤", width=40, height=40, corner_radius=20,
            fg_color=C_ACCENT, hover_color="#0e9bb5", text_color="#04121a",
            font=ctk.CTkFont(family=UI, size=16, weight="bold"),
            command=self.on_send_text
        )
        self.send_btn.grid(row=0, column=2, padx=(0, 6))

        authors = ctk.CTkFrame(composer, fg_color="transparent")
        authors.grid(row=3, column=0, pady=(8, 12))

        ctk.CTkLabel(
            authors, text="GYERT ETC.  ·  GYERT ECOSYSTEM  ·  ПОДДЕРЖКА",
            font=ctk.CTkFont(family=MONO, size=9), text_color=C_FAINT
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            authors, text=SUPPORT_HANDLE, width=78, height=20, corner_radius=6,
            fg_color="transparent", hover_color=C_PANEL_2, text_color=C_MUTED,
            font=ctk.CTkFont(family=MONO, size=9),
            command=lambda: webbrowser.open(SUPPORT_URL)
        ).pack(side="left")

    def _load_logo(self):
        """Готовит логотип для окна и шапки. Файла нет — возвращает None."""
        if not os.path.exists(LOGO_FILE):
            return None
        try:
            # Значок окна и панели задач: держим ссылку, иначе Tk потеряет картинку.
            self._win_icon = tk.PhotoImage(file=LOGO_FILE)
            self.iconphoto(True, self._win_icon)
            # Высота фиксированная, ширина по пропорции логотипа — так он не сплющится.
            image = Image.open(LOGO_FILE)
            width = max(1, round(image.width * 40 / image.height))
            return ctk.CTkImage(image, size=(width, 40))
        except Exception as e:
            print("Логотип не загрузился:", e)
            return None

    # ---------- Сообщения в ленте ----------

    def _add_bubble(self, text: str, kind: str):
        """Добавляет строку диалога: пузырь AI слева, пузырь пользователя справа."""
        row = ctk.CTkFrame(self.chat_area, fg_color="transparent")
        row.grid(row=self._row_index, column=0, sticky="ew", pady=(0, 12))
        self._row_index += 1

        is_user = kind == "user"
        avatar = ctk.CTkLabel(
            row, text="ВЫ" if is_user else "AI", width=34, height=34, corner_radius=17,
            fg_color=C_USER if not is_user else C_PANEL_2,
            text_color="#04121a" if not is_user else C_MUTED,
            font=ctk.CTkFont(family=MONO, size=10, weight="bold")
        )

        bubble = ctk.CTkLabel(
            row, text=text, wraplength=440, justify="left", anchor="w",
            corner_radius=14, padx=15, pady=11,
            fg_color=C_USER if is_user else C_PANEL_2,
            text_color=C_USER_TEXT if is_user else C_AI,
            border_width=1, border_color=C_USER if is_user else C_BORDER,
            font=ctk.CTkFont(family=UI, size=14)
        )

        side = "right" if is_user else "left"
        avatar.pack(side=side)
        bubble.pack(side=side, padx=(8, 0) if is_user else (0, 8))

        self._scroll_bottom()

    def _add_voice_bubble(self, audio_path: str, text: str):
        """Голосовой ответ: пузырь с кнопкой ▶ и расшифровкой — как голосовое в Telegram.

        Ничего не проигрывается само: файл ждёт нажатия, поэтому удаляем его после
        воспроизведения, а не сразу.
        """
        row = ctk.CTkFrame(self.chat_area, fg_color="transparent")
        row.grid(row=self._row_index, column=0, sticky="ew", pady=(0, 12))
        self._row_index += 1

        avatar = ctk.CTkLabel(
            row, text="AI", width=34, height=34, corner_radius=17,
            fg_color=C_PANEL_2, text_color=C_MUTED,
            font=ctk.CTkFont(family=MONO, size=10, weight="bold")
        )

        bubble = ctk.CTkFrame(
            row, fg_color=C_PANEL_2, corner_radius=14,
            border_width=1, border_color=C_BORDER
        )

        top = ctk.CTkFrame(bubble, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(10, 6))

        play_btn = ctk.CTkButton(
            top, text="▶", width=34, height=34, corner_radius=17,
            fg_color=C_ACCENT, hover_color="#0e9bb5", text_color="#04121a",
            font=ctk.CTkFont(family=UI, size=12, weight="bold")
        )
        play_btn.configure(command=lambda: self._play_voice(audio_path, play_btn))
        play_btn.pack(side="left")

        ctk.CTkLabel(
            top, text="▁▃▅▇▅▃▁▃▅▇▅▃▁▃▅▇▅▃▁▃▅",
            font=ctk.CTkFont(family=MONO, size=13), text_color=C_ACCENT
        ).pack(side="left", padx=10)

        ctk.CTkLabel(
            bubble, text=text, wraplength=420, justify="left", anchor="w",
            text_color=C_AI, font=ctk.CTkFont(family=UI, size=13)
        ).pack(fill="x", padx=14, pady=(0, 11))

        avatar.pack(side="left")
        bubble.pack(side="left", padx=(0, 8))

        self._scroll_bottom()

    def _play_voice(self, audio_path: str, button):
        """Проигрывает голосовое по нажатию ▶ и убирает файл после прослушивания."""
        if not os.path.exists(audio_path):
            return
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
        self.set_status("speaking")
        pygame.mixer.music.load(audio_path)
        pygame.mixer.music.play()
        button.configure(text="⏸")

        def wait_until_done():
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)
            pygame.mixer.music.unload()
            self._ui(lambda: button.configure(text="▶"))
            self._ui(self.set_status, "idle")
            try:
                os.remove(audio_path)
            except OSError:
                pass

        threading.Thread(target=wait_until_done, daemon=True).start()

    def _on_voice_toggle(self):
        self.voice_replies = bool(self.voice_switch.get())

    def _scroll_bottom(self):
        self.chat_area.update_idletasks()
        self.chat_area._parent_canvas.yview_moveto(1.0)

    # ---------- Логика чата ----------

    def set_status(self, state: str, text: str = None):
        """Обновляет HUD-строку под лентой: состояние ядра и подпись к нему."""
        defaults = {
            "idle": "🎙 ГОЛОСОВОЙ РЕЖИМ",
            "listening": "🎙 СЛУШАЮ ВАС",
            "thinking": "⏳ GYERTAI ДУМАЕТ...",
            "speaking": "🔊 GYERTAI ГОВОРИТ...",
        }
        self.status_label.configure(
            text=text or defaults.get(state, defaults["idle"]),
            text_color=STATUS_COLORS.get(state, C_ACCENT),
        )

    def on_clear(self):
        clear_history(self.session_id)
        for child in self.chat_area.winfo_children():
            child.destroy()
        self._row_index = 0
        self._add_bubble("Память диалога очищена. Готов к новой теме!", "ai")
        self.set_status("idle")

    def on_send_text(self):
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        self._add_bubble(text, "user")

        # Локальные команды: /help и /draw (как в Telegram-боте и на сайте)
        lowered = text.lower()
        if lowered in ("/help", "help", "помощь"):
            self._add_bubble(HELP_TEXT, "ai")
            return
        if lowered.startswith("/draw"):
            prompt = text[len("/draw"):].strip(" :,-—")
            if not prompt:
                self._add_bubble(
                    "Опишите картинку после команды, например: /draw закат над городом", "ai"
                )
                return
            self._add_bubble(f"🎨 Рисую: {prompt} — открываю картинку в браузере.", "ai")
            webbrowser.open(image_url(prompt))
            return

        threading.Thread(target=self.process_ai_pipeline, args=(text,), daemon=True).start()

    # ---------- Голосовой ввод ----------

    def toggle_recording(self):
        if self.is_busy:
            return
        if not self.is_recording:
            self.is_recording = True
            self.audio_frames = []
            self.mic_btn.configure(fg_color=C_DANGER, text_color="#1a0509")
            self.set_status("listening", "🎙 СЛУШАЮ… НАЖМИТЕ 🎙 ЕЩЁ РАЗ")
            threading.Thread(target=self.record_audio_loop, daemon=True).start()
        else:
            self.is_recording = False
            self.is_busy = True
            self.mic_btn.configure(fg_color=C_PANEL_3, text_color=C_TEXT)
            self.set_status("thinking", "⏳ ОБРАБАТЫВАЮ РЕЧЬ…")

    def record_audio_loop(self):
        def callback(indata, frames, time, status):
            if self.is_recording:
                self.audio_frames.append(indata.copy())

        with sd.InputStream(samplerate=self.sample_rate, channels=1, callback=callback):
            while self.is_recording:
                sd.sleep(50)

        if self.audio_frames:
            audio_data = np.concatenate(self.audio_frames, axis=0)
            os.makedirs("temp_audio", exist_ok=True)
            temp_wav = os.path.join("temp_audio", f"mic_{uuid.uuid4()}.wav")
            sf.write(temp_wav, audio_data, self.sample_rate)
            self.process_voice_pipeline(temp_wav)
        else:
            self._ui(self.set_status, "idle")
            self._ui(self._finish_voice)

    def process_voice_pipeline(self, wav_path: str):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            user_text = loop.run_until_complete(speech_to_text(wav_path))
            if not user_text:
                self._ui(self.set_status, "idle", "Речь не распознана")
                return
            self._ui(self._add_bubble, user_text, "user")
            # Ответ на голос всегда голосовой — как в мессенджере.
            self.process_ai_pipeline(user_text, force_voice=True)
        except Exception as e:
            self._ui(self._add_bubble, f"Ошибка микрофона: {e}", "ai")
            self._ui(self.set_status, "idle", "Ошибка распознавания")
        finally:
            if os.path.exists(wav_path):
                os.remove(wav_path)

    # ---------- Основной конвейер ----------

    def process_ai_pipeline(self, user_text: str, force_voice: bool = False):
        self._ui(self.set_status, "thinking")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            reply = loop.run_until_complete(ask_gyert(self.session_id, user_text))

            if self.voice_replies or force_voice:
                # Голосовые ответы включены: отдаём пузырь с ▶, а не читаем сразу.
                os.makedirs("temp_audio", exist_ok=True)
                out_mp3 = os.path.join("temp_audio", f"jarvis_{uuid.uuid4()}.mp3")
                loop.run_until_complete(text_to_speech(reply, out_mp3))
                self._ui(self._add_voice_bubble, out_mp3, reply)
            else:
                self._ui(self._add_bubble, reply, "ai")
        except Exception as e:
            self._ui(self._add_bubble, f"Ошибка ядра: {e}", "ai")
        finally:
            self._ui(self.set_status, "idle")
            self._ui(self._finish_voice)

    def _finish_voice(self):
        self.is_busy = False
        self.is_recording = False
        self.mic_btn.configure(fg_color=C_PANEL_3, text_color=C_TEXT)

    # ---------- Мост с рабочими потоками ----------

    def _ui(self, func, *args):
        """Ставит обновление интерфейса в очередь: tkinter работает только в главном потоке."""
        self._ui_queue.put((func, args))

    def _drain_ui_queue(self):
        try:
            while True:
                func, args = self._ui_queue.get_nowait()
                func(*args)
        except queue.Empty:
            pass
        self.after(60, self._drain_ui_queue)


if __name__ == "__main__":
    app = GyertDesktopApp()
    app.mainloop()
