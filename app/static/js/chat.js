(() => {
  const root = document.getElementById('cckChat');
  if (!root || root.dataset.chatInitialized === '1') return;
  root.dataset.chatInitialized = '1';

  const panel = document.getElementById('cckChatPanel');
  const body = document.getElementById('cckChatBody');
  const form = document.getElementById('cckChatForm');
  const field = document.getElementById('cckChatInput');
  if (!panel || !body || !form || !field) return;

  if (!document.querySelector('link[data-cck-chat-css]')) {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = '/static/css/chat.css';
    link.dataset.cckChatCss = '1';
    document.head.appendChild(link);
  }

  // Replace the legacy form/buttons so the old demo chatbot cannot intercept messages.
  const cleanForm = form.cloneNode(true);
  form.replaceWith(cleanForm);
  const chatForm = cleanForm;
  const chatField = chatForm.querySelector('#cckChatInput');
  root.querySelectorAll('[data-chat]').forEach(button => {
    const cleanButton = button.cloneNode(true);
    button.replaceWith(cleanButton);
  });

  let conversationId = null;
  let lastMessageId = 0;
  let humanRequested = false;
  let timer = null;

  const add = message => {
    if (!message || !message.body) return;
    const d = document.createElement('div');
    const sender = message.sender || 'bot';
    d.className = 'cck-chat-msg ' + (sender === 'customer' ? 'user' : sender === 'admin' ? 'agent' : 'bot');
    if (sender === 'admin') {
      const name = document.createElement('strong');
      name.textContent = (message.name || 'CCKAFWEARS Team') + ': ';
      d.appendChild(name);
    }
    d.appendChild(document.createTextNode(message.body));
    body.appendChild(d);
    body.scrollTop = body.scrollHeight;
    if (message.id) lastMessageId = Math.max(lastMessageId, Number(message.id));
  };

  const showError = text => {
    add({ sender: 'bot', body: text });
  };

  const showHuman = () => {
    if (humanRequested) return;
    humanRequested = true;
    const wrap = document.createElement('div');
    wrap.className = 'cck-chat-human';
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = '👤 Speak to a person';
    button.addEventListener('click', async () => {
      button.disabled = true;
      button.textContent = 'Connecting…';
      try {
        const r = await fetch('/api/chat/human', { method: 'POST', headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' }, body: '{}' });
        const data = await r.json().catch(() => ({}));
        if (!r.ok || !data.ok) throw new Error(data.error || 'Unable to connect');
        conversationId = data.conversation_id;
        add({ sender: 'system', body: 'You’re in the live-chat queue. A CCKAFWEARS team member will reply here.' });
        if (timer) clearInterval(timer);
        timer = setInterval(poll, 2000);
        poll();
      } catch (error) {
        console.error('CCK live chat:', error);
        button.disabled = false;
        button.textContent = '👤 Speak to a person';
        showError('I could not connect you to our team right now. Please try again.');
      }
    });
    wrap.appendChild(button);
    body.appendChild(wrap);
  };

  async function start() {
    try {
      const r = await fetch('/api/chat/start', { method: 'POST', headers: { 'Accept': 'application/json' } });
      const data = await r.json().catch(() => ({}));
      if (!r.ok || !data.conversation_id) throw new Error(data.error || 'Chat service unavailable');
      conversationId = data.conversation_id;
      (data.messages || []).forEach(add);
      showHuman();
    } catch (error) {
      console.error('CCK live chat start:', error);
      showError('Live chat is temporarily unavailable. Please refresh and try again.');
    }
  }

  async function poll() {
    if (!conversationId) return;
    try {
      const r = await fetch('/api/chat/messages?after=' + encodeURIComponent(lastMessageId), { headers: { Accept: 'application/json' } });
      if (!r.ok) return;
      const data = await r.json();
      (data.messages || []).forEach(add);
    } catch (error) {
      console.debug('CCK live chat poll:', error);
    }
  }

  async function sendMessage(text) {
    text = (text || '').trim();
    if (!text) return;
    add({ sender: 'customer', body: text });
    try {
      const r = await fetch('/api/chat/message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify({ message: text })
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.error || 'Message could not be sent');
      if (data.reply) add({ sender: 'bot', body: data.reply });
      if (data.conversation_id) conversationId = data.conversation_id;
      if (data.status === 'active' || data.status === 'waiting') {
        if (timer) clearInterval(timer);
        timer = setInterval(poll, 2000);
        poll();
      }
    } catch (error) {
      console.error('CCK live chat message:', error);
      showError('Sorry, your message could not be sent. Please try again.');
    }
  }

  chatForm.addEventListener('submit', event => {
    event.preventDefault();
    const text = chatField.value;
    chatField.value = '';
    sendMessage(text);
  });

  root.querySelectorAll('[data-chat]').forEach(button => button.addEventListener('click', () => {
    const type = button.dataset.chat;
    if (type === 'shop') {
      window.location.href = '/shop';
    } else if (type === 'track') {
      window.location.href = '/track-order';
    } else {
      sendMessage(type === 'delivery' ? 'How does delivery work?' : 'What is your return policy?');
    }
  }));

  start();
  timer = setInterval(poll, 2500);
})();
