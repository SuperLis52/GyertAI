import os
import uuid
import asyncio
import threading
import customtkinter as ctk
import sounddevice as sd
import soundfile as sf
import numpy as np
import pygame
from ai_core import ask_gyert, speech_to_text, text_to_speech, clear_history

pygame.mixer.init()

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class GyertDesktopApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("GyertAI — GyertStation Desktop OS")
        self.geometry("540x720")
        self.configure(fg_color="#07070c")

        self.session_id = "windows_desktop_user"
        self.is_recording = False
        self.audio_frames = []
        self.sample_rate = 16000

        # Заголовок
        self.header = ctk.CTkLabel(
            self, text="GYERT STATION", 
            font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"),
            text_color="#00d2ff"
        )
        self.header.pack(pady=(20, 2))

        self.sub_header = ctk.CTkLabel(
            self, text="CORE AI SYSTEM • СМТЛ EDITION",
            font=ctk.CTkFont(size=11), text_color="#64748b"
        )
        self.sub_header.pack(pady=(0, 15))

        # Световая сфера Джарвиса (Canvas)
        self.canvas = ctk.CTkCanvas(self, width=140, height=140, bg="#07070c", highlightthickness=0)
        self.canvas.pack(pady=5)
        self.outer_glow = self.canvas.create_oval(10, 10, 130, 130, fill="#0a2540", outline="#00d2ff", width=2)
        self.inner_orb = self.canvas.create_oval(30, 30, 110, 110, fill="#0077ff", outline="")

        self.status_label = ctk.CTkLabel(self, text="Система готова к работе", text_color="#94a3b8", font=ctk.CTkFont(size=13))
        self.status_label.pack(pady=(5, 10))

        # Поле истории чата
        self.chat_box = ctk.CTkTextbox(
            self, width=480, height=320, fg_color="#0f111a", 
            border_color="#1e293b", border_width=1, corner_radius=15,
            font=ctk.CTkFont(size=14), wrap="word"
        )
        self.chat_box.pack(pady=10, padx=20)
        self.chat_box.insert("end", "GyertAI: Приветствую! Ядро GyertStation запущено. Чем могу помочь?\n\n")
        self.chat_box.configure(state="disabled")

        # Панель ввода
        self.input_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.input_frame.pack(pady=10, padx=20, fill="x")

        self.entry = ctk.CTkEntry(
            self.input_frame, placeholder_text="Введите запрос для GyertAI...",
            height=45, corner_radius=22, fg_color="#131622", border_color="#2d3748"
        )
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.entry.bind("<Return>", lambda e: self.on_send_text())

        self.send_btn = ctk.CTkButton(
            self.input_frame, text="➤", width=45, height=45, corner_radius=22,
            fg_color="#0077ff", hover_color="#005bb5", command=self.on_send_text
        )
        self.send_btn.pack(side="right")

        # Нижние кнопки управления
        self.bottom_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.bottom_frame.pack(pady=(5, 20), padx=20, fill="x")

        self.mic_btn = ctk.CTkButton(
            self.bottom_frame, text="🎙 Говорить", height=42, corner_radius=20,
            fg_color="#1e293b", hover_color="#334155", command=self.toggle_recording
        )
        self.mic_btn.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.clear_btn = ctk.CTkButton(
            self.bottom_frame, text="🧹 Очистить память", height=42, corner_radius=20,
            fg_color="#1e293b", hover_color="#334155", command=self.on_clear
        )
        self.clear_btn.pack(side="right")
    def set_orb_state(self, state: str, status_msg: str):
        self.status_label.configure(text=status_msg)
        if state == "listening":
            self.canvas.itemconfig(self.outer_glow, fill="#3b0d11", outline="#ff3b30")
            self.canvas.itemconfig(self.inner_orb, fill="#ff2d55")
        elif state == "thinking":
            self.canvas.itemconfig(self.outer_glow, fill="#241336", outline="#bf5af2")
            self.canvas.itemconfig(self.inner_orb, fill="#af52de")
        elif state == "speaking":
            self.canvas.itemconfig(self.outer_glow, fill="#0b3322", outline="#30d158")
            self.canvas.itemconfig(self.inner_orb, fill="#32d74b")
        else:
            self.canvas.itemconfig(self.outer_glow, fill="#0a2540", outline="#00d2ff")
            self.canvas.itemconfig(self.inner_orb, fill="#0077ff")

    def append_chat(self, sender: str, text: str):
        self.chat_box.configure(state="normal")
        self.chat_box.insert("end", f"{sender}: {text}\n\n")
        self.chat_box.see("end")
        self.chat_box.configure(state="disabled")

    def on_clear(self):
        clear_history(self.session_id)
        self.chat_box.configure(state="normal")
        self.chat_box.delete("1.0", "end")
        self.chat_box.insert("end", "GyertAI: Память диалога очищена. Готов к новой теме!\n\n")
        self.chat_box.configure(state="disabled")

    def on_send_text(self):
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        self.append_chat("Вы", text)
        threading.Thread(target=self.process_ai_pipeline, args=(text,), daemon=True).start()

    def toggle_recording(self):
        if not self.is_recording:
            self.is_recording = True
            self.audio_frames = []
            self.mic_btn.configure(text="⏹ Стоп (Отправить)", fg_color="#ff2d55", hover_color="#d70015")
            self.set_orb_state("listening", "Слушаю вас... Говорите в микрофон")
            threading.Thread(target=self.record_audio_loop, daemon=True).start()
        else:
            self.is_recording = False
            self.mic_btn.configure(text="🎙 Говорить", fg_color="#1e293b", hover_color="#334155")
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
            self.append_chat("Вы (голос)", user_text)
            self.process_ai_pipeline(user_text)
        except Exception as e:
            self.append_chat("Система", f"Ошибка микрофона: {e}")
            self.set_orb_state("idle", "Ошибка распознавания")
        finally:
            if os.path.exists(wav_path):
                os.remove(wav_path)

    def process_ai_pipeline(self, user_text: str):
        self.set_orb_state("thinking", "GyertAI думает...")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            reply = loop.run_until_complete(ask_gyert(self.session_id, user_text))
            self.append_chat("GyertAI", reply)

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
            self.append_chat("Система", f"Ошибка ядра: {e}")
        finally:
            self.set_orb_state("idle", "Система готова к работе")

if __name__ == "__main__":
    app = GyertDesktopApp()
    app.mainloop()
