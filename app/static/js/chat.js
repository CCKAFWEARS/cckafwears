(() => {
  const root = document.getElementById('cckChat');
  if (!root) return;
  const panel = document.getElementById('cckChatPanel');
  const body = document.getElementById('cckChatBody');
  const oldForm = document.getElementById('cckChatForm');
  if (!panel || !body || !oldForm) return;

  const form = oldForm.cloneNode(true); oldForm.replaceWith(form);
  const field = form.querySelector('#cckChatInput');
  const quickButtons = [...root.querySelectorAll('[data-chat]')];
  quickButtons.forEach(button => button.replaceWith(button.cloneNode(true)));

  let conversationId = null;
  let lastMessageId = 0;
  let humanRequested = false;
  let timer = null;

  const add = message => {
    if (!message || !message.body) return;
    const d = document.createElement('div');
    d.className = 'cck-chat-msg ' + (message.sender === 'customer' ? 'user' : message.sender === 'admin' ? 'agent' : 'bot');
    if (message.sender === 'admin') {
      const name = document.createElement('strong'); name.textContent = (message.name || 'CCKAFWEARS Team') + ': ';
      d.appendChild(name);
    }
    d.appendChild(document.createTextNode(message.body)); body.appendChild(d); body.scrollTop = body.scrollHeight;
    lastMessageId = Math.max(lastMessageId, Number(message.id || 0));
  };

  const showHuman = () => {
    if (humanRequested) return;
    humanRequested = true;
    const wrap = document.createElement('div'); wrap.className = 'cck-chat-human';
    const button = document.createElement('button'); button.type = 'button'; button.textContent = '👤 Speak to a person';
    button.addEventListener('click', async () => {
      button.disabled = true; button.textContent = 'Connecting…';
      try {
        const r = await fetch('/api/chat/human', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
        const data = await r.json(); conversationId = data.conversation_id;
        add({sender:'system', body:'You’re in the live-chat queue. A CCKAFWEARS team member will reply here.'});
        if (timer) clearInterval(timer); timer = setInterval(poll, 2000); poll();
      } catch (_) { button.disabled = false; button.textContent = '👤 Speak to a person'; }
    });
    wrap.appendChild(button); body.appendChild(wrap);
  };

  async function start() {
    try {
      const r = await fetch('/api/chat/start', {method:'POST'}); const data = await r.json();
      conversationId = data.conversation_id; (data.messages || []).forEach(add); showHuman();
    } catch (_) {}
  }

  async function poll() {
    if (!conversationId) return;
    try {
      const r = await fetch('/api/chat/messages?after=' + encodeURIComponent(lastMessageId), {headers:{Accept:'application/json'}});
      if (!r.ok) return;
      const data = await r.json(); (data.messages || []).forEach(add);
    } catch (_) {}
  }

  async function sendMessage(text) {
    text = (text || '').trim(); if (!text) return;
    add({sender:'customer', body:text});
    try {
      const r = await fetch('/api/chat/message', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({message:text})});
      const data = await r.json();
      if (data.reply) add({sender:'bot', body:data.reply});
      if (data.status === 'active' || data.status === 'waiting') { if (timer) clearInterval(timer); timer = setInterval(poll, 2000); poll(); }
    } catch (_) { add({sender:'bot', body:'Sorry, I could not send that message. Please try again.'}); }
  }

  form.addEventListener('submit', e => { e.preventDefault(); const text = field.value; field.value=''; sendMessage(text); });
  root.querySelectorAll('[data-chat]').forEach(button => button.addEventListener('click', () => {
    const type = button.dataset.chat;
    if (type === 'shop') window.location.href = '/shop';
    else if (type === 'track') window.location.href = '/track-order';
    else sendMessage(type === 'delivery' ? 'How does delivery work?' : 'What is your return policy?');
  }));

  start();
  timer = setInterval(poll, 2500);
})();
