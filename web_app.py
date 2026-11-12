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
<title>GyertAI — независимый искусственный интеллект</title>
<style>
    :root {
        --bg: #05070d;
        --panel: #0b101a;
        --panel-2: #121a28;
        --border: #1e293b;
        --accent: #22d3ee;
        --accent-2: #0ea5e9;
        --text: #e6edf7;
        --muted: #7b8aa3;
        --user: #0ea5e9;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body { height: 100%; }
    body {
        background: var(--bg); color: var(--text);
        font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
        display: flex; flex-direction: column; overflow: hidden;
    }
    .bg-glow {
        position: fixed; inset: 0; pointer-events: none; z-index: 0;
        background:
            radial-gradient(600px 300px at 15% -5%, rgba(34, 211, 238, 0.12), transparent 70%),
            radial-gradient(700px 350px at 90% 0%, rgba(14, 165, 233, 0.10), transparent 70%);
    }

    /* Шапка */
    .topbar {
        position: relative; z-index: 2;
        display: flex; align-items: center; justify-content: space-between; gap: 16px;
        padding: 14px 26px; background: rgba(11, 16, 26, 0.85);
        border-bottom: 1px solid var(--border); backdrop-filter: blur(12px);
    }
    .brand { display: flex; align-items: center; gap: 13px; }
    .brand-orb {
        width: 40px; height: 40px; border-radius: 50%;
        background: radial-gradient(circle at 32% 30%, #67e8f9, #22d3ee 40%, #0369a1 100%);
        box-shadow: 0 0 22px rgba(34, 211, 238, 0.55);
        animation: breathe 4s ease-in-out infinite;
    }
    .brand-name { font-size: 1.15rem; font-weight: 700; letter-spacing: 2px; color: var(--accent); }
    .brand-tag { font-size: 0.72rem; color: var(--muted); letter-spacing: 0.4px; }
    .top-btns { display: flex; gap: 10px; }
    .btn {
        border: none; cursor: pointer; border-radius: 22px; padding: 10px 18px;
        font-size: 0.86rem; font-weight: 600; font-family: inherit; transition: 0.2s;
    }
    .btn-live { background: linear-gradient(135deg, #22d3ee, #0369a1); color: #04121a; }
    .btn-live:hover { filter: brightness(1.12); }
    .btn-clear { background: var(--panel-2); color: var(--muted); border: 1px solid var(--border); }
    .btn-clear:hover { color: var(--text); }

    /* Лента диалога */
    .chat-area {
        position: relative; z-index: 1; flex: 1; overflow-y: auto;
        padding: 26px 20px 12px; display: flex; flex-direction: column; gap: 16px;
        scroll-behavior: smooth;
    }
    .chat-inner { width: 100%; max-width: 820px; margin: 0 auto; display: flex; flex-direction: column; gap: 16px; }
    .row { display: flex; gap: 12px; align-items: flex-end; animation: rise 0.28s ease; }
    .row.user { flex-direction: row-reverse; }
    .avatar {
        flex: 0 0 34px; width: 34px; height: 34px; border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        font-size: 0.68rem; font-weight: 700; letter-spacing: 0.5px;
    }
    .row.ai .avatar { background: radial-gradient(circle at 32% 30%, #67e8f9, #0ea5e9 70%); color: #04121a; }
    .row.user .avatar { background: var(--panel-2); border: 1px solid var(--border); color: var(--muted); }
    .bubble {
        max-width: 76%; padding: 13px 17px; border-radius: 16px; line-height: 1.55;
        font-size: 0.96rem; white-space: pre-wrap; word-break: break-word;
    }
    .row.ai .bubble {
        background: var(--panel); border: 1px solid var(--border);
        border-bottom-left-radius: 5px;
    }
    .row.user .bubble {
        background: linear-gradient(135deg, #0ea5e9, #0369a1); color: #f0f9ff;
        border-bottom-right-radius: 5px;
    }
    .typing span {
        display: inline-block; width: 7px; height: 7px; margin-right: 5px; border-radius: 50%;
        background: var(--accent); opacity: 0.4; animation: blink 1.2s infinite;
    }
    .typing span:nth-child(2) { animation-delay: 0.2s; }
    .typing span:nth-child(3) { animation-delay: 0.4s; margin-right: 0; }

    /* Панель ввода */
    .composer {
        position: relative; z-index: 2;
        padding: 14px 20px 16px; background: rgba(11, 16, 26, 0.9);
        border-top: 1px solid var(--border); backdrop-filter: blur(12px);
    }
    .composer-inner {
        max-width: 820px; margin: 0 auto; display: flex; gap: 10px; align-items: center;
        background: var(--panel-2); border: 1px solid var(--border); border-radius: 26px;
        padding: 6px 6px 6px 20px;
    }
    .composer-inner:focus-within { border-color: rgba(34, 211, 238, 0.5); box-shadow: 0 0 0 3px rgba(34, 211, 238, 0.08); }
    #text-input {
        flex: 1; background: transparent; border: none; outline: none;
        color: var(--text); font-size: 0.98rem; font-family: inherit; padding: 10px 0;
    }
    #text-input::placeholder { color: #55627a; }
    .icon-btn {
        flex: 0 0 42px; width: 42px; height: 42px; border-radius: 50%; border: none; cursor: pointer;
        background: linear-gradient(135deg, #22d3ee, #0369a1); color: #04121a;
        font-size: 1rem; font-weight: 700; transition: 0.2s;
    }
    .icon-btn:hover { filter: brightness(1.12); }
    .authors { max-width: 820px; margin: 10px auto 0; text-align: center; font-size: 0.7rem; color: #3f4b60; letter-spacing: 0.5px; }

    /* Полноэкранный Live-режим */
    .live-overlay {
        display: none; position: fixed; inset: 0; z-index: 100;
        background: radial-gradient(circle at 50% 40%, #081521, #030509 70%);
        flex-direction: column; align-items: center; justify-content: space-between;
        padding: 46px 20px 36px;
    }
    .live-overlay.active { display: flex; }
    .live-header { text-align: center; }
    .live-header h2 { letter-spacing: 5px; color: var(--accent); font-size: 1.5rem; font-weight: 700; }
    .live-header p { color: var(--muted); font-size: 0.74rem; margin-top: 6px; letter-spacing: 1.5px; }
    .orb-stage { display: flex; flex-direction: column; align-items: center; gap: 26px; }
    .orb {
        width: 190px; height: 190px; border-radius: 50%; cursor: pointer;
        background: radial-gradient(circle at 32% 30%, #67e8f9, #22d3ee 42%, #0369a1 82%, #02060f 100%);
        box-shadow: 0 0 70px rgba(34, 211, 238, 0.45);
        transition: 0.4s ease; animation: breathe 4s ease-in-out infinite;
    }
    .orb.listening { background: radial-gradient(circle at 32% 30%, #fecdd3, #fb7185 55%, #7f1d1d 100%); box-shadow: 0 0 90px rgba(251, 113, 133, 0.7); animation: pulse 1s infinite alternate; }
    .orb.thinking { background: radial-gradient(circle at 32% 30%, #e9d5ff, #a855f7 60%, #3b0764 100%); box-shadow: 0 0 80px rgba(168, 85, 247, 0.65); animation: spin 1.6s infinite linear; }
    .orb.speaking { background: radial-gradient(circle at 32% 30%, #d1fae5, #10b981 60%, #064e3b 100%); box-shadow: 0 0 95px rgba(16, 185, 129, 0.7); animation: pulse 0.45s infinite alternate; }
    .live-status { color: var(--muted); font-size: 0.98rem; text-align: center; }
    .live-subtitles { max-width: 720px; text-align: center; font-size: 1.15rem; line-height: 1.6; }
    .btn-close-live {
        background: rgba(255, 255, 255, 0.06); color: var(--text);
        border: 1px solid var(--border); padding: 13px 30px; border-radius: 26px;
        cursor: pointer; font-size: 0.95rem; font-family: inherit; transition: 0.2s;
    }
    .btn-close-live:hover { background: rgba(255, 255, 255, 0.12); }

    @keyframes breathe { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.06); } }
    @keyframes pulse { 0% { transform: scale(1.04); } 100% { transform: scale(1.2); } }
    @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    @keyframes blink { 0%, 100% { opacity: 0.25; } 50% { opacity: 1; } }
    @keyframes rise { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }

    @media (max-width: 620px) {
        .topbar { padding: 12px 14px; }
        .brand-tag { display: none; }
        .bubble { max-width: 84%; }
        .chat-area { padding: 18px 12px 8px; }
    }
</style>
</head>
<body>
<div class="bg-glow"></div>

<header class="topbar">
    <div class="brand">
        <div class="brand-orb"></div>
        <div>
            <div class="brand-name">GYERT AI</div>
            <div class="brand-tag">Независимый искусственный интеллект</div>
        </div>
    </div>
    <div class="top-btns">
        <button class="btn btn-clear" onclick="clearChat()">🧹 Очистить</button>
        <button class="btn btn-live" onclick="openLive()">🎙 Live-сфера</button>
    </div>
</header>

<main class="chat-area" id="chat-box">
    <div class="chat-inner" id="chat-inner">
        <div class="row ai">
            <div class="avatar">AI</div>
            <div class="bubble">Привет! Я GyertAI. Задай любой вопрос текстом или включи <b>Live-сферу</b> в правом верхнем углу для голосового общения.</div>
        </div>
    </div>
</main>

<div class="composer">
    <div class="composer-inner">
        <input type="text" id="text-input" placeholder="Напишите сообщение для GyertAI..." onkeypress="if(event.key==='Enter') sendText()">
        <button class="icon-btn" onclick="sendText()">➤</button>
    </div>
    <div class="authors">Елисей Замотаев · Никита Бойковский · Gyert Ecosystem</div>
</div>

<div class="live-overlay" id="live-overlay">
    <div class="live-header">
        <h2>GYERT AI</h2>
        <p>LIVE VOICE ASSISTANT</p>
    </div>
    <div class="orb-stage">
        <div class="orb" id="orb" onclick="toggleRecording()"></div>
        <div class="live-status" id="live-status">Нажмите на сферу, чтобы начать говорить</div>
    </div>
    <div class="live-subtitles" id="live-subtitles">Ожидаю голосовую команду...</div>
    <button class="btn-close-live" onclick="closeLive()">✕ Вернуться в чат</button>
</div>

<audio id="audio-player"></audio>

<script>
    const chatInner = document.getElementById('chat-inner');
    const liveOverlay = document.getElementById('live-overlay');
    const orb = document.getElementById('orb');
    const liveStatus = document.getElementById('live-status');
    const liveSubtitles = document.getElementById('live-subtitles');
    const audioPlayer = document.getElementById('audio-player');
    const textInput = document.getElementById('text-input');

    const sessionId = "web_" + Math.random().toString(36).substring(7);
    let mediaRecorder, audioChunks = [], isRecording = false, typingRow = null;

    function scrollDown() {
        const area = document.getElementById('chat-box');
        area.scrollTop = area.scrollHeight;
    }

    function addMessage(text, sender) {
        const row = document.createElement('div');
        row.className = 'row ' + sender;
        const avatar = document.createElement('div');
        avatar.className = 'avatar';
        avatar.innerText = sender === 'user' ? 'ВЫ' : 'AI';
        const bubble = document.createElement('div');
        bubble.className = 'bubble';
        bubble.innerText = text;
        row.appendChild(avatar);
        row.appendChild(bubble);
        chatInner.appendChild(row);
        scrollDown();
    }

    function showTyping() {
        if (typingRow) return;
        typingRow = document.createElement('div');
        typingRow.className = 'row ai';
        typingRow.innerHTML = '<div class="avatar">AI</div>'
            + '<div class="bubble typing"><span></span><span></span><span></span></div>';
        chatInner.appendChild(typingRow);
        scrollDown();
    }

    function hideTyping() {
        if (typingRow) { typingRow.remove(); typingRow = null; }
    }

    function setInputEnabled(enabled) {
        textInput.disabled = !enabled;
    }

    async function clearChat() {
        const fd = new FormData();
        fd.append('session_id', sessionId);
        await fetch('/api/clear', { method: 'POST', body: fd });
        chatInner.innerHTML = '<div class="row ai"><div class="avatar">AI</div>'
            + '<div class="bubble">Память диалога очищена. Готов к новой теме!</div></div>';
    }

    async function sendText() {
        const text = textInput.value.trim();
        if (!text) return;
        textInput.value = '';
        addMessage(text, 'user');
        showTyping();
        setInputEnabled(false);

        const fd = new FormData();
        fd.append('text', text);
        fd.append('session_id', sessionId);
        try {
            const res = await fetch('/api/chat_text', { method: 'POST', body: fd });
            const data = await res.json();
            hideTyping();
            addMessage(data.reply || ("Ошибка: " + (data.error || "нет ответа")), 'ai');
        } catch (e) {
            hideTyping();
            addMessage("Ошибка соединения: " + e, 'ai');
        } finally {
            setInputEnabled(true);
            textInput.focus();
        }
    }

    function openLive() { liveOverlay.classList.add('active'); }
    function closeLive() {
        if (isRecording && mediaRecorder) mediaRecorder.stop();
        isRecording = false;
        audioPlayer.pause();
        liveOverlay.classList.remove('active');
    }

    function setOrb(state, text) {
        orb.className = 'orb ' + state;
        liveStatus.innerText = text;
    }
    audioPlayer.onplay = () => setOrb('speaking', 'GyertAI говорит...');
    audioPlayer.onended = () => setOrb('', 'Нажмите на сферу, чтобы ответить');

    async function toggleRecording() {
        if (!isRecording) {
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                mediaRecorder = new MediaRecorder(stream);
                audioChunks = [];
                mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
                mediaRecorder.onstop = async () => {
                    await sendVoice(new Blob(audioChunks, { type: 'audio/webm' }));
                };
                mediaRecorder.start();
                isRecording = true;
                setOrb('listening', 'Слушаю вас... (нажмите на сферу для отправки)');
            } catch (e) {
                alert("Разрешите доступ к микрофону в браузере!");
            }
        } else {
            mediaRecorder.stop();
            isRecording = false;
            setOrb('thinking', 'Обработка речи и генерация ответа...');
        }
    }

    async function sendVoice(blob) {
        const fd = new FormData();
        fd.append('file', blob, 'voice.webm');
        fd.append('session_id', sessionId);
        try {
            const res = await fetch('/api/voice', { method: 'POST', body: fd });
            const data = await res.json();
            if (data.error) {
                liveSubtitles.innerText = "Ошибка: " + data.error;
                setOrb('', 'Сбой');
                return;
            }
            liveSubtitles.innerText = data.reply;
            if (data.audio_url) {
                audioPlayer.src = data.audio_url;
                audioPlayer.play();
            }
        } catch (e) {
            liveSubtitles.innerText = "Ошибка соединения: " + e;
            setOrb('', 'Сбой');
        }
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
