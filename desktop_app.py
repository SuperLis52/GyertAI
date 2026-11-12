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
        self.title("GyertAI — Desktop Intelligence")
        self.geometry("860x640")
        self.minsize(760, 560)
        self.configure(fg_color="#06080f")

        self.session_id = "windows_desktop_user"
        self.is_recording = False
        self.audio_frames = []
        self.sample_rate = 16000

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # === ЛЕВАЯ БОКОВАЯ ПАНЕЛЬ ===
        self.sidebar = ctk.CTkFrame(self, width=250, corner_radius=0, fg_color="#0b0e17", border_width=1, border_color="#161d2e")
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)

        self.logo_label = ctk.CTkLabel(
            self.sidebar, text="GYERT AI",
            font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"),
            text_color="#00d2ff"
        )
        self.logo_label.pack(pady=(28, 2))

        self.sub_label = ctk.CTkLabel(
            self.sidebar, text="DESKTOP SYSTEM v2.0",
            font=ctk.CTkFont(size=10, weight="bold"), text_color="#64748b"
        )
        self.sub_label.pack(pady=(0, 20))

        self.canvas = ctk.CTkCanvas(self.sidebar, width=160, height=160, bg="#0b0e17", highlightthickness=0)
        self.canvas.pack(pady=10)
        self.ring = self.canvas.create_oval(8, 8, 152, 152, outline="#1e293b", width=2)
        self.outer_glow = self.canvas.create_oval(20, 20, 140, 140, fill="#081c36", outline="#00d2ff", width=2)
        self.inner_orb = self.canvas.create_oval(42, 42, 118, 118, fill="#0066ff", outline="")

        self.status_label = ctk.CTkLabel(
            self.sidebar, text="● Система активна",
            font=ctk.CTkFont(size=12, weight="bold"), text_color="#38bdf8"
        )
        self.status_label.pack(pady=(8, 25))

        self.mic_btn = ctk.CTkButton(
            self.sidebar, text="🎙 Голосовой запрос", height=44, corner_radius=22,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#0066ff", hover_color="#0052cc", command=self.toggle_recording
        )
        self.mic_btn.pack(pady=8, padx=22, fill="x")

        self.clear_btn = ctk.CTkButton(
            self.sidebar, text="🧹 Очистить диалог", height=40, corner_radius=20,
            font=ctk.CTkFont(size=12), fg_color="#151b2b", hover_color="#1f293d",
            text_color="#94a3b8", command=self.on_clear
        )
        self.clear_btn.pack(pady=8, padx=22, fill="x")

        self.footer_label = ctk.CTkLabel(
            self.sidebar, text="Creators:\nE. Zamotaev & N. Boykovsky",
            font=ctk.CTkFont(size=11), text_color="#475569"
        )
        self.footer_label.pack(side="bottom", pady=20)

        # === ПРАВАЯ ОБЛАСТЬ ЧАТА ===
        self.main_area = ctk.CTkFrame(self, fg_color="transparent")
        self.main_area.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.main_area.grid_rowconfigure(0, weight=1)
        self.main_area.grid_columnconfigure(0, weight=1)

        self.chat_box = ctk.CTkTextbox(
            self.main_area, fg_color="#0d111c", border_color="#1a2234", border_width=1,
            corner_radius=18, font=ctk.CTkFont(family="Segoe UI", size=14), wrap="word",
            padx=15, pady=15
        )
        self.chat_box.grid(row=0, column=0, sticky="nsew", pady=(0, 15))
        self.chat_box.insert("end", "GyertAI: Приветствую! Ядро искусственного интеллекта готово к работе. Чем могу помочь?\n\n")
        self.chat_box.configure(state="disabled")

        self.input_frame = ctk.CTkFrame(self.main_area, fg_color="#111625", corner_radius=25, border_width=1, border_color="#1e293b")
        self.input_frame.grid(row=1, column=0, sticky="ew")
        self.input_frame.grid_columnconfigure(0, weight=1)

        self.entry = ctk.CTkEntry(
            self.input_frame, placeholder_text="Напишите сообщение для GyertAI...",
            height=48, border_width=0, fg_color="transparent", font=ctk.CTkFont(size=14)
        )
        self.entry.grid(row=0, column=0, sticky="ew", padx=(20, 10))
        self.entry.bind("<Return>", lambda e: self.on_send_text())

        self.send_btn = ctk.CTkButton(
            self.input_frame, text="➤", width=42, height=38, corner_radius=19,
            fg_color="#0066ff", hover_color="#0052cc", command=self.on_send_text
        )
        self.send_btn.grid(row=0, column=1, padx=(0, 8), pady=5)
    def set_orb_state(self, state: str, status_msg: str):
        self.status_label.configure(text=status_msg)
        if state == "listening":
            self.status_label.configure(text_color="#ff453a")
            self.canvas.itemconfig(self.outer_glow, fill="#3b0d11", outline="#ff3b30")
            self.canvas.itemconfig(self.inner_orb, fill="#ff2d55")
        elif state == "thinking":
            self.status_label.configure(text_color="#bf5af2")
            self.canvas.itemconfig(self.outer_glow, fill="#241336", outline="#bf5af2")
            self.canvas.itemconfig(self.inner_orb, fill="#af52de")
        elif state == "speaking":
            self.status_label.configure(text_color="#32d74b")
            self.canvas.itemconfig(self.outer_glow, fill="#0b3322", outline="#30d158")
            self.canvas.itemconfig(self.inner_orb, fill="#32d74b")
        else:
            self.status_label.configure(text_color="#38bdf8")
            self.canvas.itemconfig(self.outer_glow, fill="#081c36", outline="#00d2ff")
            self.canvas.itemconfig(self.inner_orb, fill="#0066ff")

    def append_chat(self, sender: str, text: str):
        self.chat_box.configure(state="normal")
        self.chat_box.insert("end", f"{sender}:\n{text}\n\n{'—'*35}\n\n")
        self.chat_box.see("end")
        self.chat_box.configure(state="disabled")

    def on_clear(self):
        clear_history(self.session_id)
        self.chat_box.configure(state="normal")
        self.chat_box.delete("1.0", "end")
        self.chat_box.insert("end", "GyertAI: Память диалога очищена. Готов к новым задачам!\n\n")
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
            self.mic_btn.configure(text="⏹ Остановить запись", fg_color="#ff2d55", hover_color="#d70015")
            self.set_orb_state("listening", "● Слушаю микрофон...")
            threading.Thread(target=self.record_audio_loop, daemon=True).start()
        else:
            self.is_recording = False
            self.mic_btn.configure(text="🎙 Голосовой запрос", fg_color="#0066ff", hover_color="#0052cc")
            self.set_orb_state("thinking", "● Распознавание речи...")

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
                self.set_orb_state("idle", "● Система активна")
                return
            self.append_chat("Вы (голос)", user_text)
            self.process_ai_pipeline(user_text)
        except Exception as e:
            self.append_chat("Система", f"Ошибка микрофона: {e}")
            self.set_orb_state("idle", "● Система активна")
        finally:
            if os.path.exists(wav_path):
                os.remove(wav_path)

    def process_ai_pipeline(self, user_text: str):
        self.set_orb_state("thinking", "● Обработка запроса...")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            reply = loop.run_until_complete(ask_gyert(self.session_id, user_text))
            self.append_chat("GyertAI", reply)

            os.makedirs("temp_audio", exist_ok=True)
            out_mp3 = os.path.join("temp_audio", f"jarvis_{uuid.uuid4()}.mp3")
            loop.run_until_complete(text_to_speech(reply, out_mp3))

            self.set_orb_state("speaking", "● GyertAI говорит...")
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
            self.set_orb_state("idle", "● Система активна")

if __name__ == "__main__":
    app = GyertDesktopApp()
    app.mainloop()
