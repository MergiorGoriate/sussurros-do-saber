(() => {
  const player = document.querySelector('[data-video-playback]');
  if (!player) return;

  const send = (event, seconds = 0) => {
    if (!window.sdsHasAnalyticsConsent?.()) return;
    const body = JSON.stringify({ token: player.dataset.videoPlayback, event, seconds });
    fetch(player.dataset.playbackUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
      keepalive: true,
    }).catch(() => {});
  };

  const view = () => {
    if (document.visibilityState === 'visible' && window.sdsHasAnalyticsConsent?.()) {
      document.removeEventListener('visibilitychange', view);
      window.removeEventListener('cookieconsentchange', view);
      send('view');
    }
  };
  document.addEventListener('visibilitychange', view);
  window.addEventListener('cookieconsentchange', view);
  window.addEventListener('DOMContentLoaded', view, { once: true });
  view();
  if (!(player instanceof HTMLVideoElement)) return;

  let lastSent = 0;
  const record = (event) => {
    if (!window.sdsHasAnalyticsConsent?.()) return;
    let seconds = 0;
    for (let index = 0; index < player.played.length; index += 1) {
      seconds += player.played.end(index) - player.played.start(index);
    }
    seconds = Math.floor(Math.min(seconds, Number(player.dataset.maxSeconds)));
    if (event === 'progress' && seconds <= lastSent) return;
    lastSent = seconds;
    send(event, seconds);
  };
  player.addEventListener('playing', () => {
    if (lastSent === 0) record('start');
  });
  player.addEventListener('pause', () => record('progress'));
  player.addEventListener('ended', () => record('end'));
  player.addEventListener('timeupdate', () => {
    if (player.currentTime > lastSent + 20) record('progress');
  });
  window.addEventListener('pagehide', () => record('progress'));
})();
