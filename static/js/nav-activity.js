function updateBellActivity(el) {
    var sig = el.querySelector('[data-game-activity]');
    var active = sig && sig.dataset.gameActivity === 'true';
    var btn = document.getElementById('notif-bell-btn');
    if (btn) {
        btn.classList.toggle('text-gold', active);
        btn.classList.toggle('animate-pulse', active);
        btn.classList.toggle('text-slate', !active);
    }
    var mobileLink = document.getElementById('mobile-notif-link');
    if (mobileLink) {
        mobileLink.classList.toggle('text-gold', active);
        mobileLink.classList.toggle('animate-pulse', active);
        mobileLink.classList.toggle('text-slate', !active);
    }
}
