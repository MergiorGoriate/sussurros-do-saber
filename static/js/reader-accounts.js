(() => {
  const dialog = document.getElementById('reader-dialog');
  const form = document.getElementById('reader-auth-form');
  if (!dialog || !form) return;
  const status = document.getElementById('reader-auth-status');
  const googleArea = document.getElementById('reader-google');
  const googleStatus = document.getElementById('reader-google-status');
  let mode = 'login', csrf = '', pending = null, opener = null;
  let stateRequest = null, googleRequest = null, googleBusy = false, importRequest = null;
  let authenticated = false, articleIds = new Set();
  const root = document.querySelector('[data-reader-journal]');
  const slug = root?.dataset.readerJournal;
  const save = root?.querySelector('.journal-save-btn');
  const alert = root?.querySelector('.journal-alert-btn');
  const message = document.getElementById('journal-action-status');
  let values = {saved: false, following: false};
  const api = async (path, data) => {
    const response = await fetch(path, {method: data ? 'POST' : 'GET', body: data,
      credentials: 'same-origin', headers: {Accept: 'application/json'}});
    const result = await response.json().catch(() => ({ok: false, message: 'Não foi possível concluir. Tente novamente.'}));
    if (!response.ok || !result.ok) {
      const error = new Error(result.message || 'Não foi possível concluir. Tente novamente.');
      error.code = response.status; throw error;
    }
    return result;
  };
  const post = (path, fields = {}) => {
    const data = new FormData(); data.set('csrf_token', csrf);
    for (const [key, value] of Object.entries(fields)) data.set(key, String(value));
    return api(path, data);
  };
  const render = () => {
    document.querySelectorAll('.bookmark').forEach(button => {
      const saved = articleIds.has(String(button.dataset.id));
      button.textContent = saved ? '♥' : '♡'; button.classList.toggle('saved', saved);
      button.setAttribute('aria-pressed', String(saved));
    });
    for (const [button, key, icon] of [[save, 'saved', 'bookmark'], [alert, 'following', 'bell']]) {
      button?.setAttribute('aria-pressed', String(values[key]));
      const image = button?.querySelector('i');
      if (image) image.className = (values[key] ? 'fa-solid' : 'fa-regular') + ' fa-' + icon;
    }
    document.querySelectorAll('.reader-header-login').forEach(button => {button.textContent = authenticated ? 'Conta' : 'Entrar';});
  };
  const sessionState = () => {
    if (!stateRequest) stateRequest = api('/conta/sessao').then(state => {
      csrf = state.csrf; authenticated = state.authenticated;
      articleIds = new Set((state.saved_articles || []).map(String)); render(); return state;
    }).finally(() => {stateRequest = null;});
    return stateRequest;
  };
  const setMode = value => {
    mode = value; const register = mode === 'register';
    document.getElementById('reader-name-label').hidden = !register;
    form.elements.name.required = register; form.elements.password.minLength = register ? 12 : 1;
    form.elements.password.autocomplete = register ? 'new-password' : 'current-password';
    document.getElementById('reader-password-help').hidden = !register;
    document.getElementById('reader-submit').textContent = register ? 'Criar conta' : 'Entrar';
    dialog.querySelectorAll('[data-reader-mode]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.readerMode === mode)));
    status.textContent = '';
  };
  const readLegacy = key => {
    try {const value = JSON.parse(localStorage.getItem(key) || '[]'); return Array.isArray(value) ? value : [];}
    catch {return [];}
  };
  const importLegacy = () => {
    if (importRequest) return importRequest;
    importRequest = (async () => {
      const ids = [...new Set(readLegacy('savedArticles').map(String))];
      const slugs = [...new Set(readLegacy('savedJournalArticles').filter(v => v && typeof v.slug === 'string').map(v => v.slug))];
      const entries = ids.map(value => ['article_ids', value]).concat(slugs.map(value => ['journal_slugs', value]));
      for (let i = 0; i < entries.length; i += 100) {
        const data = new FormData(); data.set('csrf_token', csrf);
        entries.slice(i, i + 100).forEach(([key, value]) => data.append(key, value));
        await api('/conta/importar-favoritos', data);
      }
      // Remove the old browser copy only after the server saved every batch.
      if (entries.length) try {localStorage.removeItem('savedArticles'); localStorage.removeItem('savedJournalArticles');} catch {}
    })().finally(() => {importRequest = null;});
    return importRequest;
  };
  const refresh = async () => {
    const state = await sessionState();
    if (state.authenticated && slug) values = await api('/conta/revistas/' + encodeURIComponent(slug));
    else values = {saved: false, following: false};
    render(); return state;
  };
  const finishLogin = async result => {
    csrf = result.csrf;
    try {await importLegacy();} catch {status.textContent = 'A conta está activa. Os favoritos antigos serão importados na próxima visita.';}
    await refresh();
    const callback = pending; pending = null;
    if (dialog.open) dialog.close();
    if (callback) await callback();
    else if (location.pathname === '/conta/biblioteca' || location.pathname === '/conta/notificacoes') location.reload();
  };
  const acceptGoogle = async response => {
    if (googleBusy) return;
    googleBusy = true; googleStatus.textContent = 'A validar a conta...';
    try {await finishLogin(await post('/conta/google/entrar', {credential: response.credential})); googleStatus.textContent = '';}
    catch (error) {googleStatus.textContent = error.message; googleRequest = null;}
    finally {googleBusy = false;}
  };
  const loadGoogle = () => {
    if (window.google?.accounts?.id) return Promise.resolve(window.google.accounts.id);
    return new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = 'https://accounts.google.com/gsi/client'; script.async = true;
      const timeout = setTimeout(() => {script.remove(); reject(new Error('Google indisponível. Pode continuar a ler ou usar a sua conta existente.'));}, 10000);
      script.onload = () => {clearTimeout(timeout); if (window.google?.accounts?.id) resolve(window.google.accounts.id); else reject(new Error('Google indisponível.'));};
      script.onerror = () => {clearTimeout(timeout); script.remove(); reject(new Error('Google indisponível. Pode continuar a ler ou usar a sua conta existente.'));};
      document.head.append(script);
    });
  };
  const prepareGoogle = () => {
    if (!googleArea?.dataset.clientId) return Promise.resolve(null);
    if (!googleRequest) googleRequest = (async () => {
      await sessionState();
      const challenge = await post('/conta/google/preparar');
      const gis = await loadGoogle();
      gis.initialize({client_id: googleArea.dataset.clientId, nonce: challenge.nonce,
        callback: acceptGoogle, auto_select: false, button_auto_select: false,
        use_fedcm_for_button: true, cancel_on_tap_outside: true});
      const button = document.getElementById('reader-google-button'); button.replaceChildren();
      gis.renderButton(button, {type: 'standard', theme: 'outline', size: 'large', text: 'signin_with',
        locale: 'pt-PT', width: Math.min(340, Math.max(200, window.innerWidth - 80))});
      return gis;
    })().catch(error => {googleRequest = null; throw error;});
    return googleRequest;
  };
  const open = async (button, callback = null) => {
    opener = button; pending = callback; setMode('login'); dialog.showModal();
    window.google?.accounts?.id?.cancel();
    try {
      const state = await sessionState();
      document.getElementById('reader-password-panel').hidden = state.authenticated;
      const panel = document.getElementById('reader-account-panel'); panel.hidden = !state.authenticated;
      document.getElementById('reader-account-name').textContent = 'Olá, ' + state.name;
      panel.querySelector('[name="csrf_token"]').value = csrf;
      if (!state.authenticated) form.elements.email.focus();
      googleRequest = null; await prepareGoogle();
    } catch (error) {googleStatus.textContent = error.message; status.textContent = error.message;}
  };
  dialog.querySelectorAll('[data-reader-mode]').forEach(button => button.addEventListener('click', () => setMode(button.dataset.readerMode)));
  dialog.querySelector('[data-reader-close]').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => {form.elements.password.value = ''; pending = null; window.google?.accounts?.id?.cancel(); opener?.focus();});
  document.querySelectorAll('[data-reader-open]').forEach(button => button.addEventListener('click', () => open(button)));
  form.addEventListener('submit', async event => {
    event.preventDefault(); const submit = document.getElementById('reader-submit'); submit.disabled = true;
    status.textContent = 'A processar...'; dialog.querySelectorAll('[data-reader-mode]').forEach(button => {button.disabled = true;});
    try {
      if (!csrf) await sessionState();
      const data = new FormData(form); data.set('csrf_token', csrf); const submittedMode = mode;
      const result = await api('/conta/' + (submittedMode === 'register' ? 'criar-conta' : 'entrar'), data);
      form.elements.password.value = '';
      if (submittedMode === 'register') {setMode('login'); status.textContent = result.message; return;}
      await finishLogin(result);
    } catch (error) {status.textContent = error.message;}
    finally {submit.disabled = false; dialog.querySelectorAll('[data-reader-mode]').forEach(button => {button.disabled = false;});}
  });
  const withAccount = async (button, action) => {
    button.disabled = true;
    try {const state = await refresh(); const complete = action(state.authenticated); if (!state.authenticated) await open(button, complete); else await complete();}
    catch (error) {if (message) message.textContent = error.message; button.title = error.message;}
    finally {button.disabled = false;}
  };
  document.querySelectorAll('.bookmark').forEach(button => button.addEventListener('click', () => withAccount(button, signedIn => {
    const id = String(button.dataset.id); const enabled = signedIn ? !articleIds.has(id) : true;
    return async () => {
    const result = await post('/conta/artigos/' + encodeURIComponent(id), {enabled});
    if (result.saved) articleIds.add(id); else articleIds.delete(id); render();
    button.title = result.saved ? 'Artigo guardado na sua conta.' : 'Artigo removido dos favoritos.';
    };
  })));
  for (const [button, key] of [[save, 'saved'], [alert, 'following']]) button?.addEventListener('click', () => withAccount(button, signedIn => {
    const enabled = signedIn ? !values[key] : true;
    return async () => {
    values = await post('/conta/revistas/' + encodeURIComponent(slug), {action: key, enabled}); render();
    message.textContent = key === 'saved' ? (values.saved ? 'Artigo guardado na sua conta. Consulte Os meus favoritos.' : 'Artigo removido dos favoritos.')
      : (values.following ? 'Notificações activadas. Consulte a página Notificações para ver actualizações deste artigo.' : 'Notificações desactivadas.');
    };
  }));
  refresh().then(async state => {
    if (state.authenticated) {try {await importLegacy(); await refresh();} catch {} return;}
    if (!googleArea?.dataset.clientId || state.google_prompt_suppressed || /^\/(admin|submissoes|conta)(\/|$)/.test(location.pathname)) return;
    // At most one automatic attempt per tab. Closing/ignoring never opens our modal.
    let attempted = false; try {attempted = sessionStorage.getItem('googleOneTapAttempted') === '1';} catch {attempted = true;}
    if (attempted) return;
    setTimeout(async () => {
      if (dialog.open) return;
      try {
        const gis = await prepareGoogle();
        if (gis && !dialog.open && !authenticated) {
          try {sessionStorage.setItem('googleOneTapAttempted', '1');} catch {return;}
          gis.prompt();
        }
      } catch { /* Reading and the visible Entrar button remain available. */ }
    }, 2500);
  }).catch(() => { /* Account service outages never hide public content. */ });
})();
