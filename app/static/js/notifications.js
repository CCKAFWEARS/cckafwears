(() => {
  const button = document.querySelector('[data-notification-toggle]');
  const count = document.querySelector('[data-notification-count]');
  const installButtons = [...document.querySelectorAll('[data-install-app]')];
  let deferredInstallPrompt = null;

  function setButton(text, disabled = false) {
    if (!button) return;
    button.textContent = text;
    button.disabled = disabled;
  }

  function setInstallVisible(visible) {
    installButtons.forEach(btn => { btn.hidden = !visible; });
  }

  async function registerServiceWorker() {
    if (!('serviceWorker' in navigator)) return null;
    try { return await navigator.serviceWorker.register('/service-worker.js', { scope: '/' }); }
    catch (_) { return null; }
  }

  function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    const rawData = atob(base64);
    return Uint8Array.from([...rawData].map(char => char.charCodeAt(0)));
  }

  async function saveSubscription(subscription) {
    if (!subscription) return;
    await fetch('/api/push/subscribe', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(subscription.toJSON())
    });
  }

  async function enableNotifications() {
    if (!('Notification' in window) || !('PushManager' in window)) {
      setButton('Notifications unavailable', true); return;
    }
    setButton('Enabling…', true);
    try {
      const permission = await Notification.requestPermission();
      if (permission !== 'granted') {
        setButton(permission === 'denied' ? 'Notifications blocked' : 'Enable notifications'); return;
      }
      const registration = await registerServiceWorker();
      if (!registration) throw new Error('Service worker unavailable');
      const response = await fetch('/api/push/public-key');
      const config = await response.json();
      if (!config.publicKey) throw new Error('Push notifications are not configured yet');
      let subscription = await registration.pushManager.getSubscription();
      if (!subscription) subscription = await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(config.publicKey) });
      await saveSubscription(subscription);
      setButton('Notifications on'); updateUnreadCount();
    } catch (error) {
      console.error(error); setButton('Enable notifications');
      alert('Notifications are not ready yet. Please try again later.');
    } finally { if (button) button.disabled = false; }
  }

  async function syncExistingSubscription() {
    try {
      const registration = await registerServiceWorker();
      const subscription = registration && await registration.pushManager.getSubscription();
      if (subscription) await saveSubscription(subscription);
    } catch (_) {}
  }

  async function updateUnreadCount() {
    if (!count) return;
    try {
      const response = await fetch('/api/notifications/unread-count', { headers: { Accept: 'application/json' } });
      if (!response.ok) return;
      const data = await response.json(); count.textContent = data.count || ''; count.hidden = !data.count;
    } catch (_) {}
  }

  if (button) button.addEventListener('click', enableNotifications);
  if ('serviceWorker' in navigator) syncExistingSubscription();
  updateUnreadCount();

  window.addEventListener('beforeinstallprompt', event => {
    event.preventDefault(); deferredInstallPrompt = event; setInstallVisible(true);
  });

  const isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent);
  const isStandalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
  if (isStandalone) setInstallVisible(false);
  else if (isIOS) setInstallVisible(true);

  installButtons.forEach(installButton => installButton.addEventListener('click', async () => {
    if (deferredInstallPrompt) {
      deferredInstallPrompt.prompt(); await deferredInstallPrompt.userChoice;
      deferredInstallPrompt = null; setInstallVisible(false); return;
    }
    if (isIOS) alert('On iPhone/iPad: tap the Share button in Safari, then choose “Add to Home Screen”.');
    else alert('To install CCKAFWEARS, open your browser menu and choose “Install app” or “Add to Home screen”.');
  }));
})();
