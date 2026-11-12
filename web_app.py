import os
import uuid
import asyncio
from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from ai_core import ask_gyert, speech_to_text, text_to_speech, clear_history
import accounts

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

    /* Окно аккаунта */
    .modal-backdrop {
        display: none; position: fixed; inset: 0; z-index: 200; padding: 20px;
        background: rgba(2, 6, 12, 0.78); backdrop-filter: blur(6px);
        align-items: center; justify-content: center;
    }
    .modal-backdrop.active { display: flex; }
    .modal {
        width: 100%; max-width: 430px; max-height: 90vh; overflow-y: auto;
        background: var(--panel); border: 1px solid var(--border); border-radius: 18px;
        padding: 24px; box-shadow: 0 24px 60px rgba(0, 0, 0, 0.55);
    }
    .modal h3 { color: var(--accent); letter-spacing: 2px; font-size: 1rem; margin-bottom: 16px; }
    .tabs { display: flex; gap: 8px; margin-bottom: 14px; }
    .tab {
        flex: 1; padding: 9px; border-radius: 12px; cursor: pointer; font-family: inherit;
        font-size: 0.85rem; color: var(--muted); background: transparent; border: 1px solid var(--border);
    }
    .tab.active { color: #04121a; background: linear-gradient(135deg, #22d3ee, #0369a1); border-color: transparent; font-weight: 600; }
    .field {
        width: 100%; margin-bottom: 10px; padding: 12px 14px; border-radius: 12px;
        border: 1px solid var(--border); background: var(--panel-2); color: var(--text);
        font-family: inherit; font-size: 0.92rem; outline: none;
    }
    .field:focus { border-color: rgba(34, 211, 238, 0.5); }
    .modal .btn { width: 100%; margin-bottom: 8px; }
    .acc-line {
        display: flex; justify-content: space-between; gap: 12px; font-size: 0.88rem;
        padding: 8px 0; border-bottom: 1px solid var(--border);
    }
    .acc-line b { color: var(--accent); font-weight: 600; }
    .hint { font-size: 0.76rem; color: var(--muted); line-height: 1.5; margin-bottom: 8px; }
    .acc-msg { font-size: 0.82rem; color: #fca5a5; min-height: 18px; margin-bottom: 6px; }
    .acc-msg.good { color: #6ee7b7; }

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
        <button class="btn btn-clear" onclick="openAccount()">👤 Аккаунт</button>
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

<div class="modal-backdrop" id="acc-modal">
    <div class="modal">
        <h3>АККАУНТ GYERT AI</h3>

        <div id="acc-guest">
            <div class="tabs">
                <button class="tab active" id="tab-login" onclick="accTab('login')">Вход</button>
                <button class="tab" id="tab-reg" onclick="accTab('reg')">Регистрация</button>
            </div>

            <div id="pane-login">
                <input class="field" id="l-login" placeholder="Логин">
                <input class="field" id="l-pass" type="password" placeholder="Пароль">
                <button class="btn btn-live" onclick="accLogin()">Войти</button>
            </div>

            <div id="pane-reg" style="display: none;">
                <input class="field" id="r-user" placeholder="Юзернейм в Telegram (без @)">
                <button class="btn btn-clear" onclick="accSendCode()">Получить код в Telegram</button>
                <input class="field" id="r-code" placeholder="6-значный код из Telegram">
                <input class="field" id="r-login" placeholder="Придумайте логин">
                <input class="field" id="r-pass" type="password" placeholder="Придумайте пароль">
                <button class="btn btn-live" onclick="accRegister()">Создать аккаунт</button>
                <div class="hint">
                    Код приходит от нашего бота подтверждений в Telegram, поэтому сначала
                    напишите ему любое сообщение, а затем укажите свой юзернейм здесь.
                </div>
            </div>
        </div>

        <div id="acc-user" style="display: none;">
            <div class="acc-line"><span>Логин</span><b id="acc-login">—</b></div>
            <div class="acc-line"><span>Подписка</span><b id="acc-sub">—</b></div>
            <div class="acc-line"><span>Промокод</span><b id="acc-promo-used">—</b></div>
            <div class="acc-line"><span>Без подписки</span><b>20 запросов в день</b></div>

            <div style="margin-top: 16px;">
                <input class="field" id="acc-promo" placeholder="Промокод">
                <button class="btn btn-clear" onclick="accPromo()">Активировать промокод</button>
            </div>
            <div style="margin-top: 10px;">
                <button class="btn btn-live" onclick="accBuy('week')">💳 Неделя — 1.5 GRAM</button>
                <button class="btn btn-live" onclick="accBuy('month')">💳 Месяц — 4 GRAM</button>
            </div>
            <button class="btn btn-clear" style="margin-top: 12px;" onclick="accLogout()">Выйти</button>
        </div>

        <div class="acc-msg" id="acc-msg"></div>
        <button class="btn btn-clear" onclick="closeAccount()">Закрыть</button>
    </div>
</div>

<script>
    const chatInner = document.getElementById('chat-inner');
    const liveOverlay = document.getElementById('live-overlay');
    const orb = document.getElementById('orb');
    const liveStatus = document.getElementById('live-status');
    const liveSubtitles = document.getElementById('live-subtitles');
    const audioPlayer = document.getElementById('audio-player');
    const textInput = document.getElementById('text-input');

    // Идентификатор хранится в браузере: иначе перезагрузка страницы сбрасывала бы
    // дневной лимит запросов для тех, у кого нет аккаунта.
    let sessionId = localStorage.getItem('gyert_sid');
    if (!sessionId) {
        sessionId = "web_" + Math.random().toString(36).substring(7);
        localStorage.setItem('gyert_sid', sessionId);
    }
    let mediaRecorder, audioChunks = [], isRecording = false, typingRow = null;
    let mediaStream = null, isBusy = false;

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
        fd.append('token', accToken);
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

    function openLive() {
        liveOverlay.classList.add('active');
        resetLive();
    }

    function closeLive() {
        if (isRecording && mediaRecorder) { try { mediaRecorder.stop(); } catch (e) {} }
        isRecording = false;
        isBusy = false;
        stopStream();
        audioPlayer.pause();
        audioPlayer.removeAttribute('src');
        liveOverlay.classList.remove('active');
    }

    function stopStream() {
        if (mediaStream) {
            mediaStream.getTracks().forEach(t => t.stop());
            mediaStream = null;
        }
    }

    function resetLive() {
        setOrb('', 'Нажмите на сферу, чтобы начать говорить');
        liveSubtitles.innerText = 'Ожидаю голосовую команду...';
    }

    function setOrb(state, text) {
        orb.className = 'orb ' + state;
        liveStatus.innerText = text;
    }

    audioPlayer.onplay = () => setOrb('speaking', 'GyertAI говорит...');
    audioPlayer.onended = () => {
        if (liveOverlay.classList.contains('active')) resetLive();
    };

    async function toggleRecording() {
        if (isBusy) return;

        if (!isRecording) {
            try {
                mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
                const mime = MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : '';
                mediaRecorder = new MediaRecorder(mediaStream, mime ? { mimeType: mime } : undefined);
                audioChunks = [];
                mediaRecorder.ondataavailable = e => { if (e.data && e.data.size) audioChunks.push(e.data); };
                mediaRecorder.onstop = async () => {
                    stopStream();
                    const type = mediaRecorder.mimeType || 'audio/webm';
                    const blob = new Blob(audioChunks, { type });
                    audioChunks = [];
                    await sendVoice(blob);
                };
                mediaRecorder.start();
                isRecording = true;
                setOrb('listening', 'Слушаю вас... нажмите на сферу, чтобы отправить');
            } catch (e) {
                stopStream();
                liveSubtitles.innerText = 'Нет доступа к микрофону. Разрешите его в браузере.';
                setOrb('', 'Микрофон недоступен');
            }
        } else {
            isRecording = false;
            isBusy = true;
            setOrb('thinking', 'Обрабатываю речь и готовлю ответ...');
            try { mediaRecorder.stop(); } catch (e) {}
        }
    }

    async function sendVoice(blob) {
        const fd = new FormData();
        fd.append('file', blob, 'voice.webm');
        fd.append('session_id', sessionId);
        fd.append('token', accToken);
        try {
            const res = await fetch('/api/voice', { method: 'POST', body: fd });
            const data = await res.json();
            if (data.error) {
                liveSubtitles.innerText = 'Ошибка: ' + data.error;
                setOrb('', 'Сбой — нажмите на сферу и повторите');
                return;
            }
            liveSubtitles.innerText = data.reply;
            if (data.audio_url) {
                audioPlayer.src = data.audio_url;
                try {
                    await audioPlayer.play();
                } catch (e) {
                    setOrb('', 'Ответ не воспроизвёлся — нажмите на сферу ещё раз');
                }
            } else {
                setOrb('', 'Нажмите на сферу, чтобы продолжить');
            }
        } catch (e) {
            liveSubtitles.innerText = 'Ошибка соединения: ' + e;
            setOrb('', 'Сбой — нажмите на сферу и повторите');
        } finally {
            isBusy = false;
        }
    }

    // --- Аккаунт, подписка и промокоды ------------------------------------
    let accToken = localStorage.getItem('gyert_token') || '';

    function accMsg(text, good) {
        const box = document.getElementById('acc-msg');
        box.innerText = text || '';
        box.className = 'acc-msg' + (good ? ' good' : '');
    }

    function openAccount() {
        document.getElementById('acc-modal').classList.add('active');
        accMsg('');
        loadAccount();
    }

    function closeAccount() {
        document.getElementById('acc-modal').classList.remove('active');
    }

    function accTab(name) {
        const isLogin = name === 'login';
        document.getElementById('tab-login').classList.toggle('active', isLogin);
        document.getElementById('tab-reg').classList.toggle('active', !isLogin);
        document.getElementById('pane-login').style.display = isLogin ? '' : 'none';
        document.getElementById('pane-reg').style.display = isLogin ? 'none' : '';
    }

    async function accPost(url, body) {
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body || {}),
        });
        return res.json();
    }

    function accShowUser(state) {
        document.getElementById('acc-guest').style.display = 'none';
        document.getElementById('acc-user').style.display = '';
        document.getElementById('acc-login').innerText = state.login || '—';
        document.getElementById('acc-sub').innerText = state.subscribed ? ('активна до ' + state.until) : 'не оформлена';
        document.getElementById('acc-promo-used').innerText = state.promo_used || 'не использован';
    }

    function accShowGuest() {
        document.getElementById('acc-user').style.display = 'none';
        document.getElementById('acc-guest').style.display = '';
    }

    async function loadAccount() {
        if (!accToken) { accShowGuest(); return; }
        try {
            const data = await accPost('/api/account/state', { token: accToken });
            if (data.username) { accShowUser(data); } else { accForget(); }
        } catch (e) {
            accShowGuest();
        }
    }

    function accForget() {
        accToken = '';
        localStorage.removeItem('gyert_token');
        accShowGuest();
    }

    async function accSendCode() {
        accMsg('Отправляю код в Telegram...', true);
        const data = await accPost('/api/account/send_code', {
            username: document.getElementById('r-user').value.trim(),
        });
        accMsg(data.ok ? data.message : data.error, !!data.ok);
    }

    async function accRegister() {
        const data = await accPost('/api/account/register', {
            username: document.getElementById('r-user').value.trim(),
            code: document.getElementById('r-code').value.trim(),
            login: document.getElementById('r-login').value.trim(),
            password: document.getElementById('r-pass').value,
        });
        if (!data.ok) { accMsg(data.error, false); return; }
        accToken = data.token;
        localStorage.setItem('gyert_token', accToken);
        accMsg('Аккаунт создан — добро пожаловать!', true);
        loadAccount();
    }

    async function accLogin() {
        const data = await accPost('/api/account/login', {
            login: document.getElementById('l-login').value.trim(),
            password: document.getElementById('l-pass').value,
        });
        if (!data.ok) { accMsg(data.error, false); return; }
        accToken = data.token;
        localStorage.setItem('gyert_token', accToken);
        accMsg('Вы вошли в аккаунт.', true);
        loadAccount();
    }

    async function accPromo() {
        const data = await accPost('/api/account/promo', {
            token: accToken,
            promo: document.getElementById('acc-promo').value.trim(),
        });
        accMsg(data.ok ? data.message : data.error, !!data.ok);
        if (data.ok) loadAccount();
    }

    async function accBuy(plan) {
        accMsg('Создаю счёт в xRocket...', true);
        const data = await accPost('/api/account/subscribe', { token: accToken, plan });
        if (!data.ok) { accMsg(data.error, false); return; }
        accMsg('Оплатите счёт по открывшейся ссылке.', true);
        window.open(data.link, '_blank');
    }

    async function accLogout() {
        await accPost('/api/account/logout', { token: accToken });
        accForget();
        accMsg('Вы вышли из аккаунта.');
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
async def api_chat_text(
    text: str = Form(...), session_id: str = Form("default"), token: str = Form("")
):
    identity = accounts.resolve_identity(accounts.username_by_token(token), session_id)
    allowed, left = accounts.consume_request(identity)
    if not allowed:
        return JSONResponse(status_code=429, content={"error": limit_message()})
    try:
        reply = await ask_gyert(session_id, text)
        return {"reply": reply, "left": left}
    except Exception as e: return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/voice")
async def api_voice(
    file: UploadFile = File(...), session_id: str = Form("default"), token: str = Form("")
):
    identity = accounts.resolve_identity(accounts.username_by_token(token), session_id)
    allowed, left = accounts.consume_request(identity)
    if not allowed:
        return JSONResponse(status_code=429, content={"error": limit_message()})
    temp_in = os.path.join("temp_audio", f"in_{uuid.uuid4()}.webm")
    try:
        with open(temp_in, "wb") as f: f.write(await file.read())
        user_text = await speech_to_text(temp_in)
        reply = await ask_gyert(session_id, user_text)
        audio_filename = f"{uuid.uuid4()}.mp3"
        await text_to_speech(reply, os.path.join("temp_audio", audio_filename))
        return {
            "user_text": user_text,
            "reply": reply,
            "audio_url": f"/audio/{audio_filename}",
            "left": left,
        }
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

# --- Аккаунт, подписка и промокоды -------------------------------------------

def limit_message() -> str:
    return (
        f"Бесплатный лимит — {accounts.FREE_DAILY_LIMIT} запросов в день — исчерпан. "
        "Оформите подписку в разделе «👤 Аккаунт»: неделя — 1.5 GRAM, месяц — 4 GRAM, "
        "или активируйте промокод."
    )

def _deny(reason: str):
    return {"ok": False, "error": reason}

@app.post("/api/account/send_code")
async def api_account_send_code(request: Request):
    data = await request.json()
    ok, message = await asyncio.to_thread(accounts.send_login_code, data.get("username", ""))
    return {"ok": ok, "message": message} if ok else _deny(message)

@app.post("/api/account/register")
async def api_account_register(request: Request):
    data = await request.json()
    ok, message = await asyncio.to_thread(
        accounts.register,
        data.get("username", ""), data.get("code", ""),
        data.get("login", ""), data.get("password", ""),
    )
    if not ok:
        return _deny(message)
    username = accounts.normalize_username(data.get("username", ""))
    return {"ok": True, "token": accounts.issue_token(username), "username": username}

@app.post("/api/account/login")
async def api_account_login(request: Request):
    data = await request.json()
    username = accounts.authenticate(data.get("login", ""), data.get("password", ""))
    if not username:
        return _deny("Неверный логин или пароль.")
    return {"ok": True, "token": accounts.issue_token(username), "username": username}

@app.post("/api/account/logout")
async def api_account_logout(request: Request):
    data = await request.json()
    accounts.drop_token(data.get("token", ""))
    return {"ok": True}

@app.post("/api/account/state")
async def api_account_state(request: Request):
    data = await request.json()
    username = accounts.username_by_token(data.get("token", ""))
    state = accounts.account_state(username) if username else None
    return state or {"error": "not authorized"}

@app.post("/api/account/promo")
async def api_account_promo(request: Request):
    data = await request.json()
    username = accounts.username_by_token(data.get("token", ""))
    if not username:
        return _deny("Сначала войдите в аккаунт.")
    ok, message = accounts.redeem_promo(username, data.get("promo", ""))
    return {"ok": ok, "message": message} if ok else _deny(message)

@app.post("/api/account/subscribe")
async def api_account_subscribe(request: Request):
    data = await request.json()
    username = accounts.username_by_token(data.get("token", ""))
    if not username:
        return _deny("Сначала войдите в аккаунт.")
    ok, link = await asyncio.to_thread(accounts.create_invoice, username, data.get("plan", ""))
    return {"ok": True, "link": link} if ok else _deny(link)

@app.post("/api/xrocket/webhook")
async def api_xrocket_webhook(request: Request):
    raw = await request.body()
    headers = {key.lower(): value for key, value in request.headers.items()}
    code, reason = await asyncio.to_thread(accounts.apply_webhook, raw, headers)
    return JSONResponse(status_code=code, content={"status": reason})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
