import os
import uuid
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from ai_core import ask_gyert, speech_to_text, text_to_speech, clear_history

app = FastAPI(title="GyertAI — Web & Station OS")
os.makedirs("temp_audio", exist_ok=True)
app.mount("/audio", StaticFiles(directory="temp_audio"), name="audio")

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GyertAI</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        body { background-color: #0b0d13; color: #e2e8f0; height: 100vh; display: flex; flex-direction: column; }
        
        /* Шапка сайта */
        .topbar {
            display: flex; justify-content: space-between; align-items: center;
            padding: 15px 25px; background: #11141d; border-bottom: 1px solid #1e293b;
        }
        .logo { font-size: 1.25rem; font-weight: 700; color: #00d2ff; letter-spacing: 1px; }
        .top-btns { display: flex; gap: 10px; }
        .btn-live {
            background: linear-gradient(135deg, #00d2ff, #005bea); color: white; border: none;
            padding: 8px 16px; border-radius: 20px; font-weight: 600; cursor: pointer; display: flex; align-items: center; gap: 6px;
        }
        .btn-clear {
            background: #1e293b; color: #94a3b8; border: none; padding: 8px 14px; border-radius: 20px; cursor: pointer;
        }

        /* Обычный чат (Режим ChatGPT) */
        .chat-container {
            flex: 1; overflow-y: auto; padding: 20px; max-width: 800px; width: 100%; margin: 0 auto;
            display: flex; flex-direction: column; gap: 15px;
        }
        .msg { padding: 14px 18px; border-radius: 16px; max-width: 80%; line-height: 1.5; font-size: 0.98rem; }
        .msg.user { background: #005bea; color: white; align-self: flex-end; border-bottom-right-radius: 4px; }
        .msg.ai { background: #161b26; border: 1px solid #262f40; align-self: flex-start; border-bottom-left-radius: 4px; }

        .input-area {
            padding: 15px 20px; background: #11141d; border-top: 1px solid #1e293b;
            display: flex; justify-content: center;
        }
        .input-box { max-width: 800px; width: 100%; display: flex; gap: 10px; }
        input[type="text"] {
            flex: 1; padding: 14px 18px; border-radius: 25px; border: 1px solid #2d3748;
            background: #1a202c; color: white; font-size: 1rem; outline: none;
        }
        .send-btn {
            padding: 14px 24px; border-radius: 25px; border: none; background: #0077ff;
            color: white; font-weight: 600; cursor: pointer;
        }
        /* Полноэкранный оверлей для голосового Live-режима (Сфера Джарвиса) */
        .live-overlay {
            display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: #050508; z-index: 100; flex-direction: column;
            align-items: center; justify-content: space-between; padding: 40px 20px;
        }
        .live-overlay.active { display: flex; }
        .live-header { text-align: center; }
        .live-header h2 { letter-spacing: 3px; color: #00d2ff; font-size: 1.4rem; }
        .live-header p { color: #64748b; font-size: 0.8rem; margin-top: 4px; }

        .orb {
            width: 180px; height: 180px; border-radius: 50%; cursor: pointer;
            background: radial-gradient(circle at 30% 30%, #00f2fe, #4facfe 40%, #005bea 80%, #020024 100%);
            box-shadow: 0 0 60px rgba(0, 210, 255, 0.5); transition: all 0.4s ease;
            animation: breathe 4s infinite ease-in-out;
        }
        .orb.listening { background: radial-gradient(circle at 30% 30%, #ff416c, #ff4b2b 70%, #240000 100%); box-shadow: 0 0 80px rgba(255, 65, 108, 0.8); animation: pulse 1s infinite alternate; }
        .orb.thinking { background: radial-gradient(circle at 30% 30%, #a18cd1, #fbc2eb 60%, #301860 100%); box-shadow: 0 0 70px rgba(161, 140, 209, 0.7); animation: spin 1.5s infinite linear; }
        .orb.speaking { background: radial-gradient(circle at 30% 30%, #00f2fe, #00ff87 60%, #004d40 100%); box-shadow: 0 0 90px rgba(0, 255, 135, 0.8); animation: pulse 0.4s infinite alternate; }

        @keyframes breathe { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.06); } }
        @keyframes pulse { 0% { transform: scale(1.05); } 100% { transform: scale(1.22); } }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }

        .live-status { color: #94a3b8; margin-top: 20px; font-size: 1rem; text-align: center; }
        .live-subtitles { max-width: 700px; text-align: center; font-size: 1.2rem; color: #f8fafc; min-height: 60px; }
        .btn-close-live {
            background: rgba(255, 255, 255, 0.1); color: white; border: 1px solid rgba(255, 255, 255, 0.2);
            padding: 12px 28px; border-radius: 30px; cursor: pointer; font-size: 1rem;
        }
    </style>
</head>
<body>
    <div class="topbar">
        <div class="logo">GyertAI</div>
        <div class="top-btns">
            <button class="btn-clear" onclick="clearChat()">🧹 Очистить</button>
            <button class="btn-live" onclick="openLive()">🎙 Live-сфера</button>
        </div>
    </div>

    <div class="chat-container" id="chat-box">
        <div class="msg ai">Привет! Я GyertAI. Задавай любые вопросы текстом или включи <b>Live-сферу</b> в правом верхнем углу для голосового общения.</div>
    </div>

    <div class="input-area">
        <div class="input-box">
            <input type="text" id="text-input" placeholder="Напишите сообщение для GyertAI..." onkeypress="if(event.key==='Enter') sendText()">
            <button class="send-btn" onclick="sendText()">➤</button>
        </div>
    </div>

    <!-- Полноэкранный Live-режим -->
    <div class="live-overlay" id="live-overlay">
        <div class="live-header"><h2>GYERT AI</h2><p>LIVE VOICE ASSISTANT</p></div>
        <div style="display:flex; flex-direction:column; align-items:center;">
            <div class="orb" id="orb" onclick="toggleRecording()"></div>
            <div class="live-status" id="live-status">Нажмите на сферу, чтобы начать говорить</div>
        </div>
        <div class="live-subtitles" id="live-subtitles">Ожидаю голосовую команду...</div>
        <button class="btn-close-live" onclick="closeLive()">✕ Вернуться в чат</button>
    </div>

    <audio id="audio-player"></audio>

    <script>
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
            chatBox.scrollTop = chatBox.scrollHeight;
        }

        async function clearChat() {
            const fd = new FormData(); fd.append('session_id', sessionId);
            await fetch('/api/clear', { method: 'POST', body: fd });
            chatBox.innerHTML = '<div class="msg ai">Память диалога очищена!</div>';
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
                    setOrb('listening', 'Слушаю вас... (Нажмите на сферу для отправки)');
                } catch (e) { alert("Разрешите доступ к микрофону в браузере!"); }
            } else {
                mediaRecorder.stop(); isRecording = false;
                setOrb('thinking', 'Обработка речи и генерация ответа...');
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

