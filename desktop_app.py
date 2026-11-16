import os
import uuid
import math
import asyncio
import threading
import webbrowser
import customtkinter as ctk
import sounddevice as sd
import soundfile as sf
import numpy as np
import pygame
from ai_core import ask_gyert, image_url, speech_to_text, text_to_speech, clear_history

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
C_USER = "#67e8f9"
C_AI = "#c7d2fe"
C_SYS = "#fda4af"
C_DANGER = "#f43f5e"

MONO = "Consolas"
UI = "Segoe UI"

# Контакт поддержки: тот же, что в Telegram и на сайте.
SUPPORT_URL = "https://t.me/skyp_t0n"
SUPPORT_HANDLE = "@skyp_t0n"

HELP_TEXT = "\n".join([
    "GyertAI — команды и поддержка",
    "",
    "/draw описание — нарисовать картинку, например /draw закат над городом",
    "🎙 ГОВОРИТЬ — голосовое общение",
    "🧹 ОЧИСТИТЬ — сбросить память диалога",
    "",
    f"Поддержка: {SUPPORT_HANDLE} — {SUPPORT_URL}",
    "Пишите туда, если возникла ошибка или вопрос по подписке.",
])

# Размер HUD-полотна со сферой
ORB_W, ORB_H = 260, 232

ORB_PALETTE = {
    "idle": {"ring": "#22d3ee", "core": "#0ea5e9", "glow": "#08283a", "status": "Система готова к работе"},
    "listening": {"ring": "#fb7185", "core": "#f43f5e", "glow": "#3b1018", "status": "Слушаю вас... Говорите в микрофон"},
    "thinking": {"ring": "#c084fc", "core": "#a855f7", "glow": "#2a1145", "status": "GyertAI думает..."},
    "speaking": {"ring": "#34d399", "core": "#10b981", "glow": "#08301f", "status": "GyertAI говорит..."},
}
ORB_SPEED = {"idle": 0.09, "listening": 0.34, "thinking": 0.22, "speaking": 0.45}


class GyertDesktopApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("GyertAI — Desktop")
        self.geometry("600x900")
        self.minsize(560, 820)
        self.configure(fg_color=C_BG)

        self.session_id = "windows_desktop_user"
        self.is_recording = False
        self.audio_frames = []
        self.sample_rate = 16000

        # Состояние «сферы Джарвиса»
        self._orb_state = "idle"
        self._phase = 0.0
        self._spin = 0.0
        self._cx, self._cy = ORB_W // 2, ORB_H // 2

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self._build_header()
        self._build_orb()
        self._build_chat()
        self._build_input()
        self._build_controls()
        self._build_footer()

        self.after(50, self._animate_orb)

    # ---------- Интерфейс ----------

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=22, pady=(16, 0))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header, text="G Y E R T   A I",
            font=ctk.CTkFont(family=MONO, size=24, weight="bold"),
            text_color=C_ACCENT
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header, text="ИИ-ЯДРО  ·  ЭКОСИСТЕМА GYERT",
            font=ctk.CTkFont(family=MONO, size=9),
            text_color=C_MUTED
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))

        pills = ctk.CTkFrame(header, fg_color="transparent")
        pills.grid(row=0, column=1, rowspan=2, sticky="e")

        self.state_pill = ctk.CTkLabel(
            pills, text="● ONLINE",
            font=ctk.CTkFont(family=MONO, size=11, weight="bold"),
            text_color=C_ACCENT, fg_color=C_PANEL_2, corner_radius=12, padx=12, pady=4
        )
        self.state_pill.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            pills, text="🆘 SUPPORT", width=112, height=28, corner_radius=14,
            fg_color=C_PANEL_2, hover_color=C_PANEL_3, text_color=C_MUTED,
            border_width=1, border_color=C_BORDER,
            font=ctk.CTkFont(family=MONO, size=10, weight="bold"),
            command=lambda: webbrowser.open(SUPPORT_URL)
        ).pack(side="left")

        # Тонкая светящаяся линия под шапкой — как на сайте
        ctk.CTkFrame(header, height=1, fg_color=C_LINE).grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0)
        )

    def _build_orb(self):
        orb_frame = ctk.CTkFrame(self, fg_color="transparent")
        orb_frame.grid(row=1, column=0, pady=(6, 0))

        self.canvas = ctk.CTkCanvas(orb_frame, width=ORB_W, height=ORB_H, bg=C_BG, highlightthickness=0)
        self.canvas.pack()

        self._draw_hud_backdrop()

        # Внешние кольца и бегущие дуги — «живой» HUD вокруг сферы
        self.canvas.create_oval(
            self._cx - 102, self._cy - 102, self._cx + 102, self._cy + 102,
            outline=C_LINE, width=1
        )
        self._draw_ticks()
        self.hud_arc_a = self.canvas.create_arc(
            self._cx - 112, self._cy - 112, self._cx + 112, self._cy + 112,
            start=0, extent=96, style="arc", outline=C_ACCENT, width=2
        )
        self.hud_arc_b = self.canvas.create_arc(
            self._cx - 112, self._cy - 112, self._cx + 112, self._cy + 112,
            start=200, extent=52, style="arc", outline=C_ACCENT, width=2
        )

        self.orb_glow = self.canvas.create_oval(0, 0, 0, 0, fill=ORB_PALETTE["idle"]["glow"], outline="")
        self.orb_ring = self.canvas.create_oval(0, 0, 0, 0, fill="", outline=ORB_PALETTE["idle"]["ring"], width=2)
        self.orb_core = self.canvas.create_oval(0, 0, 0, 0, fill=ORB_PALETTE["idle"]["core"], outline="")

        self.status_label = ctk.CTkLabel(
            self, text=ORB_PALETTE["idle"]["status"],
            font=ctk.CTkFont(family=MONO, size=11), text_color=C_MUTED
        )
        self.status_label.grid(row=2, column=0, pady=(2, 8))

    def _draw_hud_backdrop(self):
        """Техносетка, перекрестие и уголки-скобки — футуристичный фон сферы."""
        for x in range(0, ORB_W, 26):
            self.canvas.create_line(x, 0, x, ORB_H, fill="#0a121d")
        for y in range(0, ORB_H, 26):
            self.canvas.create_line(0, y, ORB_W, y, fill="#0a121d")
        self.canvas.create_line(self._cx, 0, self._cx, ORB_H, fill=C_LINE)
        self.canvas.create_line(0, self._cy, ORB_W, self._cy, fill=C_LINE)

        pad, leng = 6, 22
        corners = (
            (pad, pad, 1, 1),
            (ORB_W - pad, pad, -1, 1),
            (pad, ORB_H - pad, 1, -1),
            (ORB_W - pad, ORB_H - pad, -1, -1),
        )
        for x, y, dx, dy in corners:
            self.canvas.create_line(x, y, x + leng * dx, y, fill=C_BORDER)
            self.canvas.create_line(x, y, x, y + leng * dy, fill=C_BORDER)

    def _draw_ticks(self):
        """Риски по кругу: каждая шестая — длиннее и ярче."""
        for i in range(36):
            angle = math.radians(i * 10)
            long_tick = i % 6 == 0
            start = 92 if long_tick else 96
            end = 102
            color = C_FAINT if long_tick else "#22304a"
            self.canvas.create_line(
                self._cx + start * math.cos(angle), self._cy + start * math.sin(angle),
                self._cx + end * math.cos(angle), self._cy + end * math.sin(angle),
                fill=color
            )

    def _build_chat(self):
        wrap = ctk.CTkFrame(self, fg_color=C_PANEL, corner_radius=16, border_width=1, border_color=C_BORDER)
        wrap.grid(row=3, column=0, sticky="nsew", padx=22, pady=(0, 10))
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            wrap, text="// ДИАЛОГ", font=ctk.CTkFont(family=MONO, size=10, weight="bold"),
            text_color=C_MUTED
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 4))

        self.chat_box = ctk.CTkTextbox(
            wrap, fg_color="transparent", border_width=0, wrap="word",
            font=ctk.CTkFont(family=UI, size=14), text_color=C_TEXT
        )
        self.chat_box.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 10))

        # В CTkTextbox для тегов запрещено менять шрифт, поэтому различаем отправителей цветом
        self.chat_box.tag_config("name_user", foreground=C_USER)
        self.chat_box.tag_config("name_ai", foreground=C_ACCENT)
        self.chat_box.tag_config("name_sys", foreground=C_SYS)
        self.chat_box.tag_config("body_user", foreground=C_TEXT)
        self.chat_box.tag_config("body_ai", foreground=C_AI)
        self.chat_box.tag_config("body_sys", foreground=C_MUTED)

        self._append("GyertAI", "Приветствую! Система GyertAI запущена. Задайте вопрос текстом, "
                                "включите микрофон или нарисуйте картинку командой /draw.", "ai")

    def _build_input(self):
        hud = ctk.CTkFrame(self, fg_color="transparent")
        hud.grid(row=4, column=0, sticky="ew", padx=22, pady=(0, 4))
        ctk.CTkLabel(
            hud, text="● СИСТЕМА ОНЛАЙН   ·   /DRAW ОПИСАНИЕ — КАРТИНКА   ·   /HELP — ПОДДЕРЖКА",
            font=ctk.CTkFont(family=MONO, size=8), text_color=C_FAINT
        ).pack()

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.grid(row=5, column=0, sticky="ew", padx=22, pady=(0, 8))
        row.grid_columnconfigure(0, weight=1)

        self.entry = ctk.CTkEntry(
            row, placeholder_text="Введите запрос или команду /draw...", height=46, corner_radius=23,
            fg_color=C_PANEL_2, border_color=C_BORDER, border_width=1,
            text_color=C_TEXT, font=ctk.CTkFont(family=UI, size=14)
        )
        self.entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.entry.bind("<Return>", lambda e: self.on_send_text())

        self.send_btn = ctk.CTkButton(
            row, text="➤", width=46, height=46, corner_radius=23,
            fg_color=C_ACCENT, hover_color="#0e9bb5", text_color="#04121a",
            font=ctk.CTkFont(family=UI, size=18, weight="bold"),
            command=self.on_send_text
        )
        self.send_btn.grid(row=0, column=1)

    def _build_controls(self):
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.grid(row=6, column=0, sticky="ew", padx=22, pady=(0, 10))
        row.grid_columnconfigure(0, weight=1)

        self.mic_btn = ctk.CTkButton(
            row, text="🎙  ГОВОРИТЬ", height=44, corner_radius=22,
            fg_color=C_PANEL_2, hover_color=C_PANEL_3, text_color=C_TEXT,
            border_width=1, border_color=C_BORDER,
            font=ctk.CTkFont(family=MONO, size=12, weight="bold"),
            command=self.toggle_recording
        )
        self.mic_btn.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        self.clear_btn = ctk.CTkButton(
            row, text="🧹  ОЧИСТИТЬ", height=44, corner_radius=22, width=140,
            fg_color=C_PANEL_2, hover_color=C_PANEL_3, text_color=C_MUTED,
            border_width=1, border_color=C_BORDER,
            font=ctk.CTkFont(family=MONO, size=12, weight="bold"),
            command=self.on_clear
        )
        self.clear_btn.grid(row=0, column=1)

    def _build_footer(self):
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=7, column=0, pady=(0, 14))

        ctk.CTkLabel(
            footer, text="GYERT ETC.  ·  GYERT ECOSYSTEM  ·  ПОДДЕРЖКА",
            font=ctk.CTkFont(family=MONO, size=9), text_color=C_FAINT
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            footer, text=SUPPORT_HANDLE, width=78, height=20, corner_radius=6,
            fg_color="transparent", hover_color=C_PANEL_2, text_color=C_MUTED,
            font=ctk.CTkFont(family=MONO, size=9),
            command=lambda: webbrowser.open(SUPPORT_URL)
        ).pack(side="left")

    # ---------- Анимация сферы ----------

    def _animate_orb(self):
        self._phase += ORB_SPEED[self._orb_state]
        # Медленное встречное вращение дуг вокруг сферы
        self._spin = (self._spin + 0.9 + ORB_SPEED[self._orb_state] * 2) % 360
        scale = 1.0 + 0.045 * math.sin(self._phase)
        self._set_oval(self.orb_glow, 88 * scale)
        self._set_oval(self.orb_ring, 66 * scale)
        self._set_oval(self.orb_core, 44 * scale)
        self.canvas.itemconfig(self.hud_arc_a, start=self._spin)
        self.canvas.itemconfig(self.hud_arc_b, start=(200 - self._spin * 0.7) % 360)
        self.after(45, self._animate_orb)

    def _set_oval(self, item, radius):
        self.canvas.coords(item, self._cx - radius, self._cy - radius, self._cx + radius, self._cy + radius)

    def set_orb_state(self, state: str, status_msg: str = None):
        self._orb_state = state if state in ORB_PALETTE else "idle"
        palette = ORB_PALETTE[self._orb_state]
        self.canvas.itemconfig(self.orb_glow, fill=palette["glow"])
        self.canvas.itemconfig(self.orb_ring, outline=palette["ring"])
        self.canvas.itemconfig(self.orb_core, fill=palette["core"])
        self.canvas.itemconfig(self.hud_arc_a, outline=palette["ring"])
        self.canvas.itemconfig(self.hud_arc_b, outline=palette["core"])
        self.status_label.configure(text=status_msg or palette["status"])
        self.state_pill.configure(text_color=palette["ring"])

    # ---------- Логика чата ----------

    def _append(self, sender: str, text: str, kind: str):
        self.chat_box.configure(state="normal")
        self.chat_box.insert("end", f"{sender}\n", f"name_{kind}")
        self.chat_box.insert("end", f"{text}\n\n", f"body_{kind}")
        self.chat_box.see("end")
        self.chat_box.configure(state="disabled")

    def on_clear(self):
        clear_history(self.session_id)
        self.chat_box.configure(state="normal")
        self.chat_box.delete("1.0", "end")
        self.chat_box.configure(state="disabled")
        self._append("Система", "Память диалога очищена. Готов к новой теме!", "sys")
        self.set_orb_state("idle")

    def on_send_text(self):
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        self._append("Вы", text, "user")

        # Локальные команды: /help и /draw (как в Telegram-боте и на сайте)
        lowered = text.lower()
        if lowered in ("/help", "help", "помощь"):
            self._append("GyertAI", HELP_TEXT, "ai")
            return
        if lowered.startswith("/draw"):
            prompt = text[len("/draw"):].strip(" :,-—")
            if not prompt:
                self._append("GyertAI", "Опишите картинку после команды, например: "
                                        "/draw закат над городом", "ai")
                return
            self._append("GyertAI", f"🎨 Рисую: {prompt} — открываю картинку в браузере.", "ai")
            webbrowser.open(image_url(prompt))
            return

        threading.Thread(target=self.process_ai_pipeline, args=(text,), daemon=True).start()

    # ---------- Голосовой ввод ----------

    def toggle_recording(self):
        if not self.is_recording:
            self.is_recording = True
            self.audio_frames = []
            self.mic_btn.configure(text="⏹  СТОП", fg_color=C_DANGER, hover_color="#d92b4b", text_color="#1a0509")
            self.set_orb_state("listening", "Слушаю вас... Говорите в микрофон")
            threading.Thread(target=self.record_audio_loop, daemon=True).start()
        else:
            self.is_recording = False
            self.mic_btn.configure(text="🎙  ГОВОРИТЬ", fg_color=C_PANEL_2, hover_color="#1c2740", text_color=C_TEXT)
            self.set_orb_state("thinking", "Распознаю голос...")

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

    def process_voice_pipeline(self, wav_path: str):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            user_text = loop.run_until_complete(speech_to_text(wav_path))
            if not user_text:
                self.set_orb_state("idle", "Речь не распознана")
                return
            self._append("Вы (голос)", user_text, "user")
            self.process_ai_pipeline(user_text)
        except Exception as e:
            self._append("Система", f"Ошибка микрофона: {e}", "sys")
            self.set_orb_state("idle", "Ошибка распознавания")
        finally:
            if os.path.exists(wav_path):
                os.remove(wav_path)

    # ---------- Основной конвейер ----------

    def process_ai_pipeline(self, user_text: str):
        self.set_orb_state("thinking", "GyertAI думает...")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            reply = loop.run_until_complete(ask_gyert(self.session_id, user_text))
            self._append("GyertAI", reply, "ai")

            os.makedirs("temp_audio", exist_ok=True)
            out_mp3 = os.path.join("temp_audio", f"jarvis_{uuid.uuid4()}.mp3")
            loop.run_until_complete(text_to_speech(reply, out_mp3))

            self.set_orb_state("speaking", "GyertAI говорит...")
            pygame.mixer.music.load(out_mp3)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)
            pygame.mixer.music.unload()

            if os.path.exists(out_mp3):
                os.remove(out_mp3)
        except Exception as e:
            self._append("Система", f"Ошибка ядра: {e}", "sys")
        finally:
            self.set_orb_state("idle", "Система готова к работе")


if __name__ == "__main__":
    app = GyertDesktopApp()
    app.mainloop()
