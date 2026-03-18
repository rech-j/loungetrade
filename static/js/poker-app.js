function pokerApp() {
    return {
        ws: null,
        connected: false,
        tableId: '',
        myUsername: '',
        tableStatus: 'pending',
        isCreator: false,

        // Table config
        minPlayers: 3,
        maxPlayers: 8,

        // Game state
        seats: [],
        myCards: [],
        communityCards: [],
        pot: 0,
        handNumber: 0,
        dealerSeat: -1,
        activeSeat: -1,
        validActions: [],
        isMyTurn: false,
        myChips: 0,
        raiseAmount: 0,
        timeout: 0,
        timeRemaining: 0,
        _timerInterval: null,

        // UI state
        statusMsg: '',
        errorMsg: '',
        gameOver: false,
        payoutResults: [],
        showShowdown: false,
        showdownResults: [],
        handLog: [],
        _logId: 0,
        canRebuy: false,
        showdownReady: {},       // { username: true/false } ready status per player
        showdownReadyCount: 0,
        showdownExpectedCount: 0,
        iWasFolded: false,       // whether I was folded this hand (auto-ready)

        // Payout projection
        myCoinsInvested: 0,
        totalCoinsInvested: 0,
        totalChips: 0,
        stake: 0,

        // Vote state
        endVoteActive: false,
        hasVotedEnd: false,
        endVoteYes: 0,
        endVoteTotal: 0,

        // Reconnect
        _reconnectAttempts: 0,
        _maxReconnectAttempts: 10,
        _reconnectTimeout: null,

        init() {
            const el = document.querySelector('[data-table-id]');
            if (!el) return;

            this.tableId = el.dataset.tableId;
            this.myUsername = el.dataset.username;
            this.tableStatus = el.dataset.tableStatus;
            this.isCreator = el.dataset.isCreator === 'true';

            this.connect();
        },

        connect() {
            // Close any existing WebSocket to prevent duplicate connections
            if (this.ws) {
                this.ws.onclose = null;  // prevent reconnect loop
                this.ws.close();
            }

            const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
            const url = proto + '//' + location.host + '/ws/poker/' + this.tableId + '/';

            this.ws = new WebSocket(url);

            this.ws.onopen = () => {
                this.connected = true;
                this._reconnectAttempts = 0;
                this.errorMsg = '';
            };

            this.ws.onclose = () => {
                this.connected = false;
                this.scheduleReconnect();
            };

            this.ws.onerror = () => {
                this.connected = false;
            };

            this.ws.onmessage = (e) => {
                const data = JSON.parse(e.data);
                this.handleMessage(data);
            };
        },

        scheduleReconnect() {
            if (this._reconnectAttempts >= this._maxReconnectAttempts) {
                this.errorMsg = 'Connection lost. Please refresh the page.';
                return;
            }
            const delay = Math.min(1000 * Math.pow(2, this._reconnectAttempts), 30000);
            this._reconnectAttempts++;
            this._reconnectTimeout = setTimeout(() => this.connect(), delay);
        },

        send(data) {
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify(data));
            }
        },

        handleMessage(data) {
            switch (data.type) {
                case 'table_state':
                    this.handleTableState(data);
                    break;
                case 'hand_started':
                    this.handleHandStarted(data);
                    break;
                case 'action_required':
                    this.handleActionRequired(data);
                    break;
                case 'player_acted':
                    this.handlePlayerActed(data);
                    break;
                case 'community_cards':
                    this.handleCommunityCards(data);
                    break;
                case 'showdown':
                    this.handleShowdown(data);
                    break;
                case 'hand_complete':
                    this.handleHandComplete(data);
                    break;
                case 'pot_update':
                    this.pot = data.pot;
                    break;
                case 'player_connected':
                    this.setPlayerOnline(data.username, true);
                    this.addLog(data.username + ' connected');
                    break;
                case 'player_disconnected':
                    this.setPlayerOnline(data.username, false);
                    this.addLog(data.username + ' disconnected');
                    break;
                case 'player_joined':
                    this.handlePlayerJoined(data);
                    break;
                case 'player_left':
                    this.handlePlayerLeft(data);
                    break;
                case 'table_cancelled':
                    this.handleTableCancelled();
                    break;
                case 'table_started':
                    this.handleTableStarted();
                    break;
                case 'game_over':
                    this.handleGameOver(data);
                    break;
                case 'player_eliminated':
                    this.addLog(data.username + ' eliminated');
                    break;
                case 'showdown_ready_update':
                    this.handleShowdownReadyUpdate(data);
                    break;
                case 'player_rebuyed':
                    this.handlePlayerRebuyed(data);
                    break;
                case 'end_vote_update':
                    this.handleEndVoteUpdate(data);
                    break;
                case 'error':
                    this.errorMsg = data.message;
                    setTimeout(() => this.errorMsg = '', 5000);
                    break;
            }
        },

        handleTableState(data) {
            this.tableStatus = data.status;
            this.handNumber = data.hand_number;
            this.dealerSeat = data.dealer_seat;
            this.isCreator = data.is_creator;
            this.minPlayers = data.min_players || 3;
            this.maxPlayers = data.max_players || 8;
            this.stake = data.stake || 0;

            // Build seats array (8 max seats)
            this.seats = [];
            for (let i = 0; i < 8; i++) {
                const player = data.players.find(p => p.seat === i);
                if (player) {
                    this.seats.push({
                        seat: i,
                        username: player.username,
                        display_name: player.display_name || player.username,
                        chips: player.chips,
                        status: player.status,
                        is_online: player.is_online,
                        avatar_url: player.avatar_url || '',
                        coins_invested: player.coins_invested || 0,
                        lastAction: '',
                        isSmallBlind: false,
                        isBigBlind: false,
                        hasCards: false,
                        roundBet: 0,
                        potContrib: 0,
                    });
                } else {
                    this.seats.push({
                        seat: i, username: '', display_name: '', chips: 0,
                        status: '', is_online: false, avatar_url: '',
                        coins_invested: 0,
                        lastAction: '', isSmallBlind: false, isBigBlind: false,
                        hasCards: false, roundBet: 0, potContrib: 0,
                    });
                }
            }

            // Update my chip count and payout projection data
            const mySeatData = this.seats.find(s => s.username === this.myUsername);
            if (mySeatData) this.myChips = mySeatData.chips;
            this.updatePayoutProjection();

            if (data.my_cards) {
                this.myCards = data.my_cards.split(',').filter(c => c);
            }

            if (data.hand) {
                this.communityCards = data.hand.community_cards ?
                    data.hand.community_cards.split(',').filter(c => c) : [];
                this.pot = data.hand.pot;
                this.activeSeat = data.hand.current_seat;
                this.dealerSeat = data.hand.dealer_seat;
            }

            this.checkCanRebuy();
        },

        handleHandStarted(data) {
            this.handNumber = data.hand_number;
            this.dealerSeat = data.dealer_seat;
            this.pot = data.pot;
            this.communityCards = [];
            this.showShowdown = false;
            this.showdownResults = [];
            this.showdownReady = {};
            this.showdownReadyCount = 0;
            this.showdownExpectedCount = 0;
            this.iWasFolded = false;
            this.tableStatus = 'active';

            // Update player chips and statuses
            if (data.players) {
                for (const p of data.players) {
                    const seat = this.seats.find(s => s.seat === p.seat);
                    if (seat) {
                        seat.chips = p.chips;
                        seat.status = p.status;
                        seat.lastAction = '';
                        seat.isSmallBlind = false;
                        seat.isBigBlind = false;
                        seat.hasCards = p.status !== 'eliminated' && p.status !== 'spectating' && p.status !== 'left';
                        seat.roundBet = 0;
                        seat.potContrib = 0;
                    }
                }
            }

            // Set hole cards
            if (data.my_cards) {
                this.myCards = data.my_cards.split(',').filter(c => c);
            } else {
                this.myCards = [];
            }

            // Mark blind positions
            this.markBlinds(data.dealer_seat, data.small_blind, data.big_blind);

            this.addLog('--- Hand #' + data.hand_number + ' ---');
            this.statusMsg = '';
            this.updateMyChips();
            this.checkCanRebuy();
        },

        markBlinds(dealerSeat, smallBlind, bigBlind) {
            const activePlayers = this.seats.filter(s => s.username && s.status !== 'eliminated' && s.status !== 'spectating' && s.status !== 'left');
            if (activePlayers.length < 2) return;

            const sorted = activePlayers.slice().sort((a, b) => a.seat - b.seat);

            const nextSeat = (fromSeat) => {
                for (let i = 0; i < sorted.length; i++) {
                    if (sorted[i].seat > fromSeat) return sorted[i].seat;
                }
                return sorted[0].seat;
            };

            let sbSeat, bbSeat;
            if (sorted.length === 2) {
                sbSeat = dealerSeat;
                bbSeat = nextSeat(dealerSeat);
            } else {
                sbSeat = nextSeat(dealerSeat);
                bbSeat = nextSeat(sbSeat);
            }

            for (const s of this.seats) {
                s.isSmallBlind = s.seat === sbSeat;
                s.isBigBlind = s.seat === bbSeat;
                if (s.seat === sbSeat) {
                    s.roundBet = smallBlind || 0;
                    s.potContrib = smallBlind || 0;
                }
                if (s.seat === bbSeat) {
                    s.roundBet = bigBlind || 0;
                    s.potContrib = bigBlind || 0;
                }
            }
        },

        handleActionRequired(data) {
            this.activeSeat = data.seat;
            this.pot = data.pot;
            this.timeout = data.timeout;

            const isMe = data.username === this.myUsername;
            this.isMyTurn = isMe;
            this.validActions = isMe ? data.valid_actions : [];

            // Set default raise amount
            const raiseAction = this.validActions.find(a => a.action === 'raise' || a.action === 'bet');
            if (raiseAction) {
                this.raiseAmount = raiseAction.min;
            }

            if (isMe) {
                this.statusMsg = 'Your turn';
            } else {
                this.statusMsg = "Waiting for " + data.username + "...";
            }

            // Start timer countdown
            this.startTimer(data.timeout);
        },

        startTimer(seconds) {
            if (this._timerInterval) clearInterval(this._timerInterval);
            this.timeRemaining = seconds;
            if (seconds <= 0) return;

            this._timerInterval = setInterval(() => {
                this.timeRemaining = Math.max(0, this.timeRemaining - 1);
                if (this.timeRemaining <= 0) {
                    clearInterval(this._timerInterval);
                }
            }, 1000);
        },

        handlePlayerActed(data) {
            const seat = this.seats.find(s => s.username === data.username);
            if (seat) {
                seat.lastAction = data.poker_action;
                if (data.poker_action === 'fold') {
                    seat.status = 'folded';
                    seat.hasCards = false;
                }
                if (data.poker_action === 'all_in') seat.status = 'all_in';
                if (data.amount > 0) {
                    seat.roundBet = (seat.roundBet || 0) + data.amount;
                    seat.potContrib = (seat.potContrib || 0) + data.amount;
                }
                // Update chip count from server
                if (data.chips !== undefined) seat.chips = data.chips;
            }
            this.pot = data.pot;
            this.updateMyChips();

            const amt = data.amount && data.amount > 0 ? ' ' + data.amount : '';
            this.addLog(data.username + ': ' + data.poker_action + amt);

            if (data.username === this.myUsername) {
                this.isMyTurn = false;
                this.validActions = [];
            }
        },

        handleCommunityCards(data) {
            if (data.cards) {
                const newCards = data.cards.split(',').filter(c => c);
                // Deduplicate: only add cards not already on the board
                const existing = new Set(this.communityCards);
                for (const card of newCards) {
                    if (!existing.has(card)) {
                        this.communityCards.push(card);
                    }
                }
            }
            this.pot = data.pot;

            // Clear last actions and round bets for new round
            for (const s of this.seats) {
                if (s.status !== 'folded' && s.status !== 'eliminated') {
                    s.lastAction = '';
                }
                s.roundBet = 0;
            }

            this.addLog('Community: ' + this.communityCards.map(c => this.formatCard(c)).join(' '));
        },

        handleShowdown(data) {
            this.showdownResults = data.results || [];
            this.showShowdown = true;
            this.pot = 0;
            this.isMyTurn = false;
            this.validActions = [];
            this.activeSeat = -1;
            for (const s of this.seats) { s.hasCards = false; s.roundBet = 0; }

            if (data.community_cards) {
                this.communityCards = data.community_cards.split(',').filter(c => c);
            }

            for (const r of this.showdownResults) {
                if (r.winnings > 0) {
                    this.addLog(r.username + ' wins ' + r.winnings + ' (' + r.hand_name + ')');
                }
            }

            // Update chips from results
            for (const r of this.showdownResults) {
                const seat = this.seats.find(s => s.username === r.username);
                if (seat && r.winnings > 0) {
                    seat.chips += r.winnings;
                }
            }
            this.updateMyChips();

            // Ready-up tracking
            const needsReady = data.needs_ready || [];
            this.showdownReady = {};
            for (const u of needsReady) {
                this.showdownReady[u] = false;
            }
            this.showdownExpectedCount = needsReady.length;
            this.showdownReadyCount = 0;

            // Check if I was folded (auto-ready, no button needed)
            this.iWasFolded = !needsReady.includes(this.myUsername);
        },

        handleShowdownReadyUpdate(data) {
            if (this.showdownReady.hasOwnProperty(data.username)) {
                this.showdownReady[data.username] = true;
            }
            this.showdownReadyCount = Object.values(this.showdownReady).filter(v => v).length;
        },

        sendShowdownReady() {
            this.send({ action: 'showdown_ready' });
        },

        handleHandComplete(data) {
            // Single winner (others folded)
            this.pot = 0;
            this.isMyTurn = false;
            this.validActions = [];
            this.activeSeat = -1;
            for (const s of this.seats) { s.hasCards = false; s.roundBet = 0; }

            const results = data.results || [];
            for (const r of results) {
                if (r.winnings > 0) {
                    this.addLog(r.username + ' wins ' + r.winnings);
                    const seat = this.seats.find(s => s.username === r.username);
                    if (seat) seat.chips += r.winnings;
                }
            }
            this.updateMyChips();
        },

        handleGameOver(data) {
            this.gameOver = true;
            this.tableStatus = 'completed';
            this.payoutResults = data.payouts || [];
            this.isMyTurn = false;
            this.validActions = [];
            this.statusMsg = 'Game over!';
            this.addLog('=== Game Over ===');
        },

        handlePlayerRebuyed(data) {
            const seat = this.seats.find(s => s.username === data.username);
            if (seat) {
                seat.chips = data.chips;
                seat.status = 'active';
                if (data.coins_invested) seat.coins_invested = data.coins_invested;
            }
            this.addLog(data.username + ' rebuyed');
            this.updateMyChips();
            this.checkCanRebuy();
        },

        handleEndVoteUpdate(data) {
            this.endVoteActive = data.active;
            const votes = data.votes || [];
            this.endVoteTotal = votes.length;
            this.endVoteYes = votes.filter(v => v.voted).length;
            const me = votes.find(v => v.username === this.myUsername);
            this.hasVotedEnd = me ? me.voted : false;
        },

        setPlayerOnline(username, online) {
            const seat = this.seats.find(s => s.username === username);
            if (seat) seat.is_online = online;
        },

        handlePlayerJoined(data) {
            // Add or update the seat in the seats array
            if (data.seat >= 0 && data.seat < this.seats.length) {
                this.seats[data.seat] = {
                    seat: data.seat,
                    username: data.username,
                    display_name: data.display_name || data.username,
                    chips: data.chips,
                    status: 'active',
                    is_online: false,
                    avatar_url: data.avatar_url || '',
                    coins_invested: data.coins_invested || 0,
                    lastAction: '',
                    isSmallBlind: false,
                    isBigBlind: false,
                    hasCards: false,
                    roundBet: 0,
                    potContrib: 0,
                };
            }
            this.addLog(data.username + ' joined the table');
            this.updatePayoutProjection();
        },

        handlePlayerLeft(data) {
            if (data.seat >= 0 && data.seat < this.seats.length) {
                this.seats[data.seat] = {
                    seat: data.seat, username: '', display_name: '', chips: 0,
                    status: '', is_online: false, avatar_url: '',
                    coins_invested: 0,
                    lastAction: '', isSmallBlind: false, isBigBlind: false,
                    hasCards: false, roundBet: 0, potContrib: 0,
                };
            }
            this.addLog(data.username + ' left the table');
        },

        handleTableCancelled() {
            this.tableStatus = 'cancelled';
            this.statusMsg = 'Table cancelled by creator. Buy-ins refunded.';
            this.gameOver = true;
        },

        handleTableStarted() {
            this.tableStatus = 'active';
            this.statusMsg = 'Game started!';
        },

        checkCanRebuy() {
            const mySeat = this.seats.find(s => s.username === this.myUsername);
            this.canRebuy = mySeat && mySeat.chips === 0 &&
                (mySeat.status === 'eliminated' || mySeat.status === 'active' || mySeat.status === 'folded');
        },

        updateMyChips() {
            const mySeat = this.seats.find(s => s.username === this.myUsername);
            if (mySeat) this.myChips = mySeat.chips;
            this.updatePayoutProjection();
        },

        updatePayoutProjection() {
            const activePlayers = this.seats.filter(s => s.username && s.status !== 'invited');
            this.totalCoinsInvested = activePlayers.reduce((sum, s) => sum + (s.coins_invested || 0), 0);
            this.totalChips = activePlayers.reduce((sum, s) => sum + s.chips, 0);
            const mySeat = this.seats.find(s => s.username === this.myUsername);
            this.myCoinsInvested = mySeat ? (mySeat.coins_invested || 0) : 0;
        },

        getMyProjectedPayout() {
            if (this.totalCoinsInvested === 0) return 0;

            const activePlayers = this.seats.filter(s => s.username && s.status !== 'invited');

            // Use effective chips (stack + pot contribution) to mirror server
            // pot-refund logic: the server returns pot to stacks before payout
            const effectiveChips = (s) => s.chips + (s.potContrib || 0);
            const totalEffective = activePlayers.reduce((sum, s) => sum + effectiveChips(s), 0);
            if (totalEffective === 0) return 0;

            const mySeat = activePlayers.find(s => s.username === this.myUsername);
            if (!mySeat || effectiveChips(mySeat) === 0) return 0;

            // Mirror server logic: largest stack gets the rounding remainder
            const myEffective = effectiveChips(mySeat);
            const maxEffective = Math.max(...activePlayers.map(s => effectiveChips(s)));
            const iAmLargest = myEffective === maxEffective;

            if (iAmLargest) {
                const othersSum = activePlayers
                    .filter(s => s.username !== this.myUsername)
                    .reduce((sum, s) => {
                        const eff = effectiveChips(s);
                        if (eff === 0) return sum;
                        return sum + Math.floor((eff * this.totalCoinsInvested) / totalEffective);
                    }, 0);
                return this.totalCoinsInvested - othersSum;
            }
            return Math.floor((myEffective * this.totalCoinsInvested) / totalEffective);
        },

        getMyProjectedNet() {
            return this.getMyProjectedPayout() - this.myCoinsInvested;
        },

        // Actions
        sendAction(action, amount) {
            this.send({
                action: 'poker_action',
                poker_action: action,
                amount: amount || 0,
            });
            this.isMyTurn = false;
            this.validActions = [];
        },

        sendRebuy() {
            this.send({ action: 'rebuy' });
        },

        sendVoteEnd(vote) {
            this.send({ action: 'vote_end', vote: vote });
            if (vote) this.hasVotedEnd = true;
        },

        startGame() {
            // Use HTTP form submission for starting
            const form = document.createElement('form');
            form.method = 'POST';
            form.action = '/poker/start/' + this.tableId + '/';
            const csrf = document.querySelector('[name=csrfmiddlewaretoken]');
            if (csrf) {
                const input = document.createElement('input');
                input.type = 'hidden';
                input.name = 'csrfmiddlewaretoken';
                input.value = csrf.value;
                form.appendChild(input);
            }
            document.body.appendChild(form);
            form.submit();
        },

        addLog(msg) {
            this.handLog.push({ id: ++this._logId, text: msg });
            this.$nextTick(() => {
                const el = document.getElementById('hand-log');
                if (el) el.scrollTop = el.scrollHeight;
            });
        },

        // Card display helpers
        formatCard(cardStr) {
            if (!cardStr || cardStr.length < 2) return '';
            const rank = cardStr[0];
            const suit = cardStr[1];
            const suitSymbols = { 's': '\u2660', 'h': '\u2665', 'd': '\u2666', 'c': '\u2663' };
            const rankDisplay = { 'T': '10', 'J': 'J', 'Q': 'Q', 'K': 'K', 'A': 'A' };
            return (rankDisplay[rank] || rank) + (suitSymbols[suit] || suit);
        },

        cardColorClass(cardStr) {
            if (!cardStr || cardStr.length < 2) return '';
            const suit = cardStr[1];
            if (suit === 'h' || suit === 'd') return 'hearts';
            return 'spades';
        },
    };
}
