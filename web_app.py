import os
import uuid
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from ai_core import ask_gyert, speech_to_text, text_to_speech, clear_history

app = FastAPI(title="GyertAI")
os.makedirs("temp_audio", exist_ok=True)
app.mount("/audio", StaticFiles(directory="temp_audio"), name="audio")

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GyertAI — Искусственный интеллект нового поколения</title>
    <link href="https://googleapis.com" rel="stylesheet">
    <style>
        :root {
            --bg-main: #06080f;
            --bg-panel: rgba(16, 20, 32, 0.75);
            --border-glass: rgba(255, 255, 255, 0.08);
            --accent-blue: #00d2ff;
            --accent-deep: #005bea;
            --text-primary: #f8fafc;
            --text-muted: #94a3b8;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', -apple-system, sans-serif; }
        body {
            background: radial-gradient(circle at 50% 0%, #0d162c 0%, var(--bg-main) 65%);
            color: var(--text-primary); height: 100vh; display: flex; flex-direction: column; overflow: hidden;
        }
        
        /* Премиальная шапка */
        .topbar {
            display: flex; justify-content: space-between; align-items: center;
            padding: 16px 32px; background: var(--bg-panel); backdrop-filter: blur(16px);
            border-bottom: 1px solid var(--border-glass); z-index: 20;
        }
        .brand { display: flex; align-items: center; gap: 12px; }
        .brand-dot {
            width: 10px; height: 10px; border-radius: 50%; background: var(--accent-blue);
            box-shadow: 0 0 12px var(--accent-blue);
        }
        .logo {
            font-size: 1.3rem; font-weight: 700; letter-spacing: 1.5px;
            background: linear-gradient(90deg, #ffffff, #00d2ff);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        }
        .badge {
            font-size: 0.7rem; padding: 3px 8px; border-radius: 6px;
            background: rgba(0, 210, 255, 0.1); color: var(--accent-blue); border: 1px solid rgba(0, 210, 255, 0.25);
            font-weight: 600; letter-spacing: 0.5px;
        }
        .top-btns { display: flex; gap: 12px; }
        .btn-live {
            background: linear-gradient(135deg, #00d2ff 0%, #005bea 100%); color: white; border: none;
            padding: 10px 20px; border-radius: 24px; font-weight: 600; font-size: 0.9rem; cursor: pointer;
            display: flex; align-items: center; gap: 8px; box-shadow: 0 4px 20px rgba(0, 119, 255, 0.35);
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .btn-live:hover { transform: translateY(-1px); box-shadow: 0 6px 25px rgba(0, 210, 255, 0.5); }
        .btn-clear {
            background: rgba(255, 255, 255, 0.05); color: var(--text-muted); border: 1px solid var(--border-glass);
            padding: 10px 16px; border-radius: 24px; font-size: 0.9rem; cursor: pointer; transition: all 0.2s;
        }
        .btn-clear:hover { background: rgba(255, 255, 255, 0.1); color: white; }

        /* Область чата */
        .chat-wrapper { flex: 1; overflow-y: auto; padding: 30px 20px; scroll-behavior: smooth; }
        .chat-container { max-width: 820px; width: 100%; margin: 0 auto; display: flex; flex-direction: column; gap: 18px; }
        .msg {
            padding: 16px 22px; border-radius: 20px; max-width: 78%; line-height: 1.6; font-size: 0.98rem;
            white-space: pre-wrap; animation: fadeIn 0.25s ease;
        }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
        .msg.user {
            background: linear-gradient(135deg, #0066ff, #0044cc); color: white;
            align-self: flex-end; border-bottom-right-radius: 6px; box-shadow: 0 4px 15px rgba(0, 85, 255, 0.25);
        }
        .msg.ai {
            background: var(--bg-panel); border: 1px solid var(--border-glass);
            align-self: flex-start; border-bottom-left-radius: 6px; backdrop-filter: blur(10px);
        }

        /* Панель ввода */
        .input-area {
            padding: 20px; background: linear-gradient(to top, var(--bg-main) 70%, transparent);
            display: flex; justify-content: center;
        }
        .input-box {
            max-width: 820px; width: 100%; display: flex; gap: 12px; align-items: center;
            background: rgba(22, 27, 42, 0.9); border: 1px solid rgba(255, 255, 255, 0.12);
            padding: 8px 8px 8px 22px; border-radius: 32px; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4);
        }
        input[type="text"] {
            flex: 1; border: none; background: transparent; color: white; font-size: 1rem; outline: none;
        }
        .send-btn {
            width: 44px; height: 44px; border-radius: 50%; border: none;
            background: linear-gradient(135deg, #00d2ff, #005bea); color: white;
            font-size: 1.1rem; cursor: pointer; display: flex; align-items: center; justify-content: center;
            transition: transform 0.2s;
        }
        .send-btn:hover { transform: scale(1.05); }
        /* Полноэкранный голосовой Live-режим */
        .live-overlay {
            display: none; position: fixed; inset: 0;
            background: radial-gradient(circle at 50% 45%, #0c1833 0%, #030408 75%);
            z-index: 100; flex-direction: column; align-items: center; justify-content: space-between;
            padding: 45px 20px;
        }
        .live-overlay.active { display: flex; }
        .live-header { text-align: center; }
        .live-header h2 {
            letter-spacing: 5px; font-size: 1.6rem; font-weight: 700;
            background: linear-gradient(90deg, #ffffff, #00d2ff);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        }
        .live-header p { color: #64748b; font-size: 0.8rem; letter-spacing: 2px; margin-top: 6px; text-transform: uppercase; }

        .orb-stage { position: relative; width: 260px; height: 260px; display: flex; align-items: center; justify-content: center; cursor: pointer; }
        .orb-ring {
            position: absolute; inset: 0; border-radius: 50%; border: 1px solid rgba(0, 210, 255, 0.2);
            animation: rotateRing 12s linear infinite;
        }
        .orb-ring::before {
            content: ''; position: absolute; top: -4px; left: 50%; width: 8px; height: 8px;
            border-radius: 50%; background: #00d2ff; box-shadow: 0 0 15px #00d2ff;
        }
        .orb {
            width: 170px; height: 170px; border-radius: 50%;
            background: radial-gradient(circle at 32% 28%, #70e1f5, #00d2ff 35%, #005bea 75%, #020617 100%);
            box-shadow: 0 0 70px rgba(0, 210, 255, 0.45), inset 0 0 35px rgba(255, 255, 255, 0.45);
            transition: all 0.4s cubic-bezier(0.22, 1, 0.36, 1);
            animation: breathe 4s infinite ease-in-out;
        }
        .orb.listening {
            background: radial-gradient(circle at 32% 28%, #ff9a9e, #ff416c 45%, #8b0000 85%);
            box-shadow: 0 0 90px rgba(255, 65, 108, 0.75), inset 0 0 35px rgba(255, 255, 255, 0.6);
            animation: pulse 0.9s infinite alternate;
        }
        .orb.thinking {
            background: radial-gradient(circle at 32% 28%, #e0c3fc, #8ec5fc 50%, #2b1055 90%);
            box-shadow: 0 0 85px rgba(142, 197, 252, 0.7);
            animation: spin 1.6s infinite linear;
        }
        .orb.speaking {
            background: radial-gradient(circle at 32% 28%, #a8ff78, #00f2fe 50%, #004d40 90%);
            box-shadow: 0 0 100px rgba(0, 242, 254, 0.85), inset 0 0 40px rgba(255, 255, 255, 0.75);
            animation: pulse 0.35s infinite alternate;
        }

        @keyframes rotateRing { 100% { transform: rotate(360deg); } }
        @keyframes breathe { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.06); } }
        @keyframes pulse { 0% { transform: scale(1.06); } 100% { transform: scale(1.22); } }
        @keyframes spin { 0% { transform: rotate(0deg) scale(1.05); } 50% { transform: rotate(180deg) scale(0.96); } 100% { transform: rotate(360deg) scale(1.05); } }

        .live-status { color: #94a3b8; margin-top: 24px; font-size: 0.95rem; letter-spacing: 0.5px; text-align: center; }
        .live-subtitles {
            max-width: 760px; width: 100%; text-align: center; font-size: 1.15rem; line-height: 1.6;
            color: #f1f5f9; padding: 20px 28px; border-radius: 20px;
            background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.08);
            backdrop-filter: blur(12px); max-height: 220px; overflow-y: auto; white-space: pre-wrap;
        }
        .btn-close-live {
            background: rgba(255, 255, 255, 0.07); color: #e2e8f0; border: 1px solid rgba(255, 255, 255, 0.15);
            padding: 12px 30px; border-radius: 30px; cursor: pointer; font-size: 0.95rem; transition: all 0.2s;
        }
        .btn-close-live:hover { background: rgba(255, 255, 255, 0.15); color: white; }
    </style>
</head>
<body>
    <div class="topbar">
        <div class="brand">
            <div class="brand-dot"></div>
            <div class="logo">GyertAI</div>
            <span class="badge">CORE v2.0</span>
        </div>
        <div class="top-btns">
            <button class="btn-clear" onclick="clearChat()">🧹 Очистить</button>
            <button class="btn-live" onclick="openLive()">🎙 Live-режим</button>
        </div>
    </div>

    <div class="chat-wrapper" id="chat-wrapper">
        <div class="chat-container" id="chat-box">
            <div class="msg ai">Приветствую! Я GyertAI — полноценный искусственный интеллект. Задавайте любые вопросы текстом или переключитесь в голосовой Live-режим.</div>
        </div>
    </div>

    <div class="input-area">
        <div class="input-box">
            <input type="text" id="text-input" placeholder="Спросите GyertAI о чём угодно..." onkeypress="if(event.key==='Enter') sendText()">
            <button class="send-btn" onclick="sendText()">➤</button>
        </div>
    </div>

    <div class="live-overlay" id="live-overlay">
        <div class="live-header"><h2>GYERT AI</h2><p>VOICE INTERFACE SYSTEM</p></div>
        <div style="display:flex; flex-direction:column; align-items:center;">
            <div class="orb-stage" onclick="toggleRecording()">
                <div class="orb-ring"></div>
                <div class="orb" id="orb"></div>
            </div>
            <div class="live-status" id="live-status">Нажмите на сферу, чтобы начать говорить</div>
        </div>
        <div class="live-subtitles" id="live-subtitles">Система готова к голосовому взаимодействию.</div>
        <button class="btn-close-live" onclick="closeLive()">✕ Вернуться в текстовый чат</button>
    </div>

    <audio id="audio-player"></audio>
    <script>
        const chatWrapper = document.getElementById('chat-wrapper');
        const chatBox = document.getElementById('chat-box');
        const liveOverlay = document.getElementById('live-overlay');
        const orb = document.getElementById('orb');
        const liveStatus = document.getElementById('live-status');
        const liveSubtitles = document.getElementById('live-subtitles');
        const audioPlayer = document.getElementById('audio-player');

        const sessionId = "web_" + Math.random().toString(36).substring(7);
        let mediaRecorder, audioChunks = [], isRecording = false;

        function addMessage(text, sender) {
            const div = document.createElement('div');
            div.className = 'msg ' + sender;
            div.innerText = text;
            chatBox.appendChild(div);
            chatWrapper.scrollTop = chatWrapper.scrollHeight;
        }

        async function clearChat() {
            const fd = new FormData(); fd.append('session_id', sessionId);
            await fetch('/api/clear', { method: 'POST', body: fd });
            chatBox.innerHTML = '<div class="msg ai">Память диалога очищена. Готов к новым задачам!</div>';
        }

        async function sendText() {
            const input = document.getElementById('text-input');
            const text = input.value.trim();
            if (!text) return;
            input.value = '';
            addMessage(text, 'user');

            const fd = new FormData(); fd.append('text', text); fd.append('session_id', sessionId);
            const res = await fetch('/api/chat_text', { method: 'POST', body: fd });
            const data = await res.json();
            addMessage(data.reply || ("Ошибка: " + data.error), 'ai');
        }

        function openLive() { liveOverlay.classList.add('active'); }
        function closeLive() {
            if (isRecording && mediaRecorder) mediaRecorder.stop();
            isRecording = false;
            audioPlayer.pause();
            liveOverlay.classList.remove('active');
        }

        function setOrb(state, text) { orb.className = 'orb ' + state; liveStatus.innerText = text; }
        audioPlayer.onplay = () => setOrb('speaking', 'GyertAI говорит...');
        audioPlayer.onended = () => setOrb('', 'Нажмите на сферу, чтобы ответить');

        async function toggleRecording() {
            if (!isRecording) {
                try {
                    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                    mediaRecorder = new MediaRecorder(stream);
                    audioChunks = [];
                    mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
                    mediaRecorder.onstop = async () => { await sendVoice(new Blob(audioChunks, { type: 'audio/webm' })); };
                    mediaRecorder.start(); isRecording = true;
                    setOrb('listening', 'Слушаю вас... (Нажмите снова для отправки)');
                } catch (e) { alert("Разрешите доступ к микрофону в настройках браузера!"); }
            } else {
                mediaRecorder.stop(); isRecording = false;
                setOrb('thinking', 'Обработка речи...');
            }
        }

        async function sendVoice(blob) {
            const fd = new FormData(); fd.append('file', blob, 'voice.webm'); fd.append('session_id', sessionId);
            const res = await fetch('/api/voice', { method: 'POST', body: fd });
            const data = await res.json();
            if (data.error) { liveSubtitles.innerText = "Ошибка: " + data.error; setOrb('', 'Сбой'); return; }
            liveSubtitles.innerText = data.reply;
            if (data.audio_url) { audioPlayer.src = data.audio_url; audioPlayer.play(); }
        }
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def index(): return HTML_TEMPLATE

@app.post("/api/clear")
async def api_clear(session_id: str = Form("default")):
    clear_history(session_id)
    return {"status": "ok"}

@app.post("/api/chat_text")
async def api_chat_text(text: str = Form(...), session_id: str = Form("default")):
    try:
        reply = await ask_gyert(session_id, text)
        return {"reply": reply}
    except Exception as e: return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/voice")
async def api_voice(file: UploadFile = File(...), session_id: str = Form("default")):
    temp_in = os.path.join("temp_audio", f"in_{uuid.uuid4()}.webm")
    try:
        with open(temp_in, "wb") as f: f.write(await file.read())
        user_text = await speech_to_text(temp_in)
        reply = await ask_gyert(session_id, user_text)
        audio_filename = f"{uuid.uuid4()}.mp3"
        await text_to_speech(reply, os.path.join("temp_audio", audio_filename))
        return {"user_text": user_text, "reply": reply, "audio_url": f"/audio/{audio_filename}"}
    except Exception as e: return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        if os.path.exists(temp_in): os.remove(temp_in)

@app.post("/api/esp32_audio")
async def api_esp32(file: UploadFile = File(...)):
    temp_in = os.path.join("temp_audio", f"esp_{uuid.uuid4()}.wav")
    audio_out = os.path.join("temp_audio", f"esp_out_{uuid.uuid4()}.mp3")
    try:
        with open(temp_in, "wb") as f: f.write(await file.read())
        reply = await ask_gyert("esp32_hardware_station", await speech_to_text(temp_in))
        await text_to_speech(reply, audio_out)
        return FileResponse(audio_out, media_type="audio/mpeg")
    finally:
        if os.path.exists(temp_in): os.remove(temp_in)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
