(function () {
    'use strict';

    if (!document.body.hasAttribute('data-authenticated')) return;

    var ICON_MAP = {
        coin_received: '\u2733',  // star
        game_invite: '\u2694',    // crossed swords
        game_result: '\u265B',    // crown/queen
    };

    var ws = null;
    var reconnectDelay = 1000;
    var maxReconnectDelay = 30000;
    var pollEl = null;

    function getWsUrl() {
        var protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        return protocol + '//' + location.host + '/ws/notifications/';
    }

    function connect() {
        ws = new WebSocket(getWsUrl());

        ws.onopen = function () {
            reconnectDelay = 1000;
            disablePolling();
        };

        ws.onmessage = function (e) {
            var data;
            try { data = JSON.parse(e.data); } catch (_) { return; }

            if (data.type === 'new_notification') {
                onNewNotification(data.notification);
            } else if (data.type === 'notification_read') {
                onNotificationRead(data.id);
            } else if (data.type === 'all_notifications_read') {
                onAllRead();
            } else if (data.type === 'notification_deleted') {
                onNotificationDeleted(data.id);
            }
        };

        ws.onclose = function () {
            ws = null;
            enablePolling();
            setTimeout(connect, reconnectDelay);
            reconnectDelay = Math.min(reconnectDelay * 2, maxReconnectDelay);
        };
    }

    function enablePolling() {
        // Re-enable HTMX polling on the badge as fallback
        pollEl = document.getElementById('notif-badge-poll');
        if (pollEl) pollEl.removeAttribute('disabled');
        // Trigger a fresh badge fetch
        var badge = document.querySelector('[hx-get*="unread-count"]');
        if (badge && window.htmx) htmx.trigger(badge, 'load');
    }

    function disablePolling() {
        pollEl = document.getElementById('notif-badge-poll');
        if (pollEl) pollEl.setAttribute('disabled', '');
    }

    function updateBadge(delta) {
        // Update all badge elements showing unread count
        var badges = document.querySelectorAll('.notif-badge-count');
        badges.forEach(function (el) {
            var current = parseInt(el.textContent, 10) || 0;
            var next = Math.max(0, current + delta);
            el.textContent = next || '';
            // Toggle visibility of the badge wrapper
            var wrapper = el.closest('.notif-badge-wrapper');
            if (wrapper) {
                wrapper.style.display = next > 0 ? '' : 'none';
            }
        });
    }

    function setBadge(count) {
        var badges = document.querySelectorAll('.notif-badge-count');
        badges.forEach(function (el) {
            el.textContent = count || '';
            var wrapper = el.closest('.notif-badge-wrapper');
            if (wrapper) {
                wrapper.style.display = count > 0 ? '' : 'none';
            }
        });
    }

    function pulseBell() {
        var btn = document.getElementById('notif-bell-btn');
        if (btn) {
            btn.classList.add('text-gold', 'animate-pulse');
            btn.classList.remove('text-slate');
            setTimeout(function () {
                btn.classList.remove('animate-pulse');
            }, 2000);
        }
        var mobileLink = document.getElementById('mobile-notif-link');
        if (mobileLink) {
            mobileLink.classList.add('text-gold', 'animate-pulse');
            mobileLink.classList.remove('text-slate');
            setTimeout(function () {
                mobileLink.classList.remove('animate-pulse');
                mobileLink.classList.add('text-slate');
            }, 2000);
        }
    }

    function onNewNotification(notif) {
        updateBadge(1);
        pulseBell();

        // Prepend to dropdown if it's open
        var dropdown = document.querySelector('.notif-dropdown-list');
        if (dropdown) {
            var icon = ICON_MAP[notif.notif_type] || '\u2022';
            var timeAgo = 'just now';
            var linkStart = notif.link ? '<a href="' + notif.link + '" class="block">' : '<div>';
            var linkEnd = notif.link ? '</a>' : '</div>';
            var html = '<div class="notif-row px-4 py-3 hover:bg-gold/10 border-b border-stone dark:border-slate border-l-3 border-l-gold" data-notif-id="' + notif.id + '" role="menuitem">'
                + linkStart
                + '<p class="text-xs font-medium"><span class="notif-icon mr-1">' + icon + '</span>' + escapeHtml(notif.title) + '</p>'
                + '<p class="text-xs text-slate mt-0.5">' + escapeHtml(notif.message).substring(0, 70) + '</p>'
                + '<p class="text-xs text-slate mt-0.5">' + timeAgo + '</p>'
                + linkEnd
                + '</div>';
            dropdown.insertAdjacentHTML('afterbegin', html);
        }
    }

    function onNotificationRead(id) {
        updateBadge(-1);
        var row = document.querySelector('[data-notif-id="' + id + '"]');
        if (row) {
            row.classList.remove('border-l-gold', 'border-l-3');
            row.classList.add('opacity-60');
            var markBtn = row.querySelector('.notif-mark-read');
            if (markBtn) markBtn.remove();
        }
    }

    function onAllRead() {
        setBadge(0);
        document.querySelectorAll('.notif-row').forEach(function (row) {
            row.classList.remove('border-l-gold', 'border-l-3');
            row.classList.add('opacity-60');
            var markBtn = row.querySelector('.notif-mark-read');
            if (markBtn) markBtn.remove();
        });
    }

    function onNotificationDeleted(id) {
        var row = document.querySelector('[data-notif-id="' + id + '"]');
        if (row) {
            var wasUnread = row.classList.contains('border-l-gold');
            row.remove();
            if (wasUnread) updateBadge(-1);
        }
    }

    function escapeHtml(str) {
        var div = document.createElement('div');
        div.appendChild(document.createTextNode(str));
        return div.innerHTML;
    }

    // Start WebSocket connection
    connect();
})();
