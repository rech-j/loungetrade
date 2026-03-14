function chessApp() {
    return {
        // State (i have endless sadness in my heart)
        ws: null,
        connected: false,
        gameActive: false,
        gameOver: false,
        gameOverTitle: '',
        gameOverMsg: '',
        statusMsg: '',
        errorMsg: '',

        chess: null,           // chess.js instance
        fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
        boardSquares: [],      // array of { name, piece, rank, file, showRank, showFile }
        selectedSq: null,
        legalMoves: [],        // squares the selected piece can move to
        lastMove: null,        // { from, to }
        dragFrom: null,
        touchGhost: null,
        _touchDragSq: null,
        _touchDragging: false,
        _touchDragStartX: 0,
        _touchDragStartY: 0,
        pendingPromotion: null, // { from, to } awaiting piece choice

        currentTurn: 'w',      // 'w' | 'b' — reactive mirror of chess.turn()
        mySide: null,          // 'white' | 'black' | null (spectator/pending)
        myName: 'You',
        opponentName: 'Opponent',
        myUsername: '',
        myAvatar: '',
        myInitial: '',
        opponentAvatar: '',
        opponentInitial: '',
        opponentOnline: false,
        playerAvatars: {},     // { username: { avatar, initial } }

        reconnectAttempts: 0,
        reconnectCountdown: 0,
        _reconnectCountdownInterval: null,
        myTime: 600,
        opponentTime: 600,
        timerInterval: null,
        confirmResign: false,
        movePairs: [],         // [['e4', 'e5'], ['Nf3', ...], ...]
        sanMoves: [],          // all SAN moves in order

        // Computed
        get isMyTurn() {
            if (!this.chess || !this.mySide) return false;
            return (this.currentTurn === 'w' && this.mySide === 'white') ||
                   (this.currentTurn === 'b' && this.mySide === 'black');
        },
        get myTimeLow() { return this.myTime <= 30; },
        get opponentTimeLow() { return this.opponentTime <= 30; },

        // Captured pieces
        get capturedPieces() {
            if (!this.chess) return { white: [], black: [], whiteValue: 0, blackValue: 0 };
            var startingPieces = { p: 8, n: 2, b: 2, r: 2, q: 1 };
            var pieceValues = { p: 1, n: 3, b: 3, r: 5, q: 9 };
            var onBoard = { w: { p: 0, n: 0, b: 0, r: 0, q: 0 }, b: { p: 0, n: 0, b: 0, r: 0, q: 0 } };
            var board = this.chess.board();
            for (var r = 0; r < 8; r++) {
                for (var f = 0; f < 8; f++) {
                    var sq = board[r][f];
                    if (sq && sq.type !== 'k') onBoard[sq.color][sq.type]++;
                }
            }
            // Captured by white = black's missing pieces; captured by black = white's missing pieces
            var capturedByWhite = [];
            var capturedByBlack = [];
            var whiteValue = 0;
            var blackValue = 0;
            var pieceOrder = ['q', 'r', 'b', 'n', 'p'];
            for (var i = 0; i < pieceOrder.length; i++) {
                var t = pieceOrder[i];
                var missingBlack = startingPieces[t] - onBoard.b[t];
                var missingWhite = startingPieces[t] - onBoard.w[t];
                for (var j = 0; j < missingBlack; j++) {
                    capturedByWhite.push('b' + t.toUpperCase());
                    whiteValue += pieceValues[t];
                }
                for (var j = 0; j < missingWhite; j++) {
                    capturedByBlack.push('w' + t.toUpperCase());
                    blackValue += pieceValues[t];
                }
            }
            return { white: capturedByWhite, black: capturedByBlack, whiteValue: whiteValue, blackValue: blackValue };
        },
        get myCaptured() {
            if (!this.mySide) return [];
            return this.mySide === 'white' ? this.capturedPieces.white : this.capturedPieces.black;
        },
        get opponentCaptured() {
            if (!this.mySide) return [];
            return this.mySide === 'white' ? this.capturedPieces.black : this.capturedPieces.white;
        },
        get myAdvantage() {
            if (!this.mySide) return 0;
            var myVal = this.mySide === 'white' ? this.capturedPieces.whiteValue : this.capturedPieces.blackValue;
            var oppVal = this.mySide === 'white' ? this.capturedPieces.blackValue : this.capturedPieces.whiteValue;
            return myVal - oppVal;
        },
        get opponentAdvantage() {
            return -this.myAdvantage;
        },
        get gameOverColorClass() {
            if (this.gameOverTitle === 'You Win!') return 'border-patina';
            if (this.gameOverTitle === 'You Lose') return 'border-burgundy';
            return 'border-stone';
        },
        get gameOverTitleClass() {
            if (this.gameOverTitle === 'You Win!') return 'text-patina';
            if (this.gameOverTitle === 'You Lose') return 'text-burgundy';
            return 'text-slate';
        },
        get turnText() {
            if (!this.gameActive || !this.mySide) return '';
            return this.isMyTurn ? 'Your move' : (this.opponentName + "'s turn");
        },

        // Init
        init() {
            var el = this.$el;
            this.playerAvatars[el.dataset.creatorUsername] = {
                avatar: el.dataset.creatorAvatar || '',
                initial: el.dataset.creatorInitial || '?',
            };
            this.playerAvatars[el.dataset.opponentUsername] = {
                avatar: el.dataset.opponentAvatar || '',
                initial: el.dataset.opponentInitial || '?',
            };
            this.chess = new Chess();
            this.renderBoard();
            this.connectWS();
        },

        connectWS() {
            var proto = location.protocol === 'https:' ? 'wss' : 'ws';
            this.ws = new WebSocket(proto + '://' + location.host + '/ws/chess/' + this.$el.dataset.gameId + '/');
            this.ws.onopen = () => {
                this.connected = true;
                this.errorMsg = '';
                this.reconnectAttempts = 0;
                this.reconnectCountdown = 0;
                if (this._reconnectCountdownInterval) { clearInterval(this._reconnectCountdownInterval); this._reconnectCountdownInterval = null; }
            };
            this.ws.onclose = (event) => {
                this.connected = false;
                if (!this.gameOver && !event.wasClean && this.reconnectAttempts < 5) {
                    this.reconnectAttempts++;
                    var delay = 3000 * this.reconnectAttempts + Math.floor(Math.random() * 2000);
                    this.reconnectCountdown = Math.round(delay / 1000);
                    this.errorMsg = '';
                    if (this._reconnectCountdownInterval) clearInterval(this._reconnectCountdownInterval);
                    this._reconnectCountdownInterval = setInterval(() => {
                        this.reconnectCountdown = Math.max(0, this.reconnectCountdown - 1);
                    }, 1000);
                    setTimeout(() => this.connectWS(), delay);
                } else if (this.reconnectAttempts >= 5) {
                    this.errorMsg = 'Connection lost. Please refresh the page.';
                    this.reconnectCountdown = 0;
                }
            };
            this.ws.onerror = () => { this.errorMsg = 'Connection error.'; };
            this.ws.onmessage = (e) => this.handleMessage(JSON.parse(e.data));
        },

        handleMessage(data) {
            if (data.type === 'game_state') {
                this.applyGameState(data);
            } else if (data.type === 'player_connected') {
                if (data.username !== this.myUsername) this.opponentOnline = true;
                this.statusMsg = data.username + ' connected.';
                setTimeout(() => { this.statusMsg = ''; }, 3000);
            } else if (data.type === 'player_disconnected') {
                if (data.username !== this.myUsername) this.opponentOnline = false;
            } else if (data.type === 'chess_move') {
                this.applyOpponentMove(data);
            } else if (data.type === 'chess_game_over') {
                this.handleGameOver(data);
            } else if (data.type === 'chess_error') {
                this.errorMsg = data.message;
                this.stopTimer();
            }
        },

        applyGameState(data) {
            if (data.status === 'active') {
                this.gameActive = true;
                this.mySide = data.your_side;
                this.chess.load(data.fen);
                this.fen = data.fen;
                this.currentTurn = this.chess.turn();
                this.myTime = this.mySide === 'white' ? data.white_time : data.black_time;
                this.opponentTime = this.mySide === 'white' ? data.black_time : data.white_time;
                var myUser = this.mySide === 'white' ? data.white_player : data.black_player;
                var oppUser = this.mySide === 'white' ? data.black_player : data.white_player;
                this.myName = myUser;
                this.opponentName = oppUser;
                var myInfo = this.playerAvatars[myUser] || {};
                var oppInfo = this.playerAvatars[oppUser] || {};
                this.myAvatar = myInfo.avatar || '';
                this.myInitial = myInfo.initial || myUser.charAt(0).toUpperCase();
                this.opponentAvatar = oppInfo.avatar || '';
                this.opponentInitial = oppInfo.initial || oppUser.charAt(0).toUpperCase();
                this.opponentOnline = true;
                // Rebuild move list from UCI
                if (data.moves_uci) this.rebuildMoveList(data.moves_uci);
                this.renderBoard();
                this.startTimer();
            } else if (data.status === 'completed' || data.status === 'cancelled') {
                this.gameActive = false;
                this.gameOver = true;
                this.gameOverTitle = 'Game Over';
                this.gameOverMsg = 'This game has already ended.';
            }
        },

        rebuildMoveList(movesUci) {
            // Replay moves on a fresh chess instance to get SAN notation
            var temp = new Chess();
            this.sanMoves = [];
            var parts = movesUci.split(' ').filter(Boolean);
            for (var i = 0; i < parts.length; i++) {
                var uci = parts[i];
                var from = uci.slice(0, 2);
                var to = uci.slice(2, 4);
                var promotion = uci.length === 5 ? uci[4] : undefined;
                var result = temp.move({ from: from, to: to, promotion: promotion });
                if (result) this.sanMoves.push(result.san);
            }
            this.buildMovePairs();
        },

        buildMovePairs() {
            var pairs = [];
            for (var i = 0; i < this.sanMoves.length; i += 2) {
                pairs.push([this.sanMoves[i], this.sanMoves[i+1] || '']);
            }
            this.movePairs = pairs;
            this.$nextTick(() => {
                var list = document.getElementById('move-list');
                if (list) list.scrollTop = list.scrollHeight;
            });
        },

        applyOpponentMove(data) {
            // Don't apply our own moves (we already did)
            if (data.player === this.myUsername) return;
            var from = data.move.slice(0, 2);
            var to = data.move.slice(2, 4);
            var promotion = data.move.length === 5 ? data.move[4] : undefined;
            var result = this.chess.move({ from: from, to: to, promotion: promotion });
            if (result) {
                this.playMoveSound();
                this.fen = this.chess.fen();
                this.currentTurn = this.chess.turn();
                this.lastMove = { from: from, to: to };
                this.sanMoves.push(result.san);
                this.buildMovePairs();
                this.renderBoard();
                // Update times
                if (data.white_time !== null) {
                    if (this.mySide === 'white') this.myTime = data.white_time;
                    else this.opponentTime = data.white_time;
                }
                if (data.black_time !== null) {
                    if (this.mySide === 'black') this.myTime = data.black_time;
                    else this.opponentTime = data.black_time;
                }
                this.checkGameEnd();
            }
        },

        handleGameOver(data) {
            this.gameActive = false;
            this.gameOver = true;
            this.stopTimer();
            if (data.winner === null) {
                this.gameOverTitle = 'Draw';
                this.gameOverMsg = (data.reason === 'stalemate' ? 'Stalemate' : 'Draw agreed') + '. No coins transferred.';
            } else if (data.winner === this.myUsername) {
                this.gameOverTitle = 'You Win!';
                this.gameOverMsg = (data.reason === 'resign' ? 'Opponent resigned' : data.reason === 'timeout' ? 'Opponent ran out of time' : 'Checkmate!') + ' You won ' + data.stake + ' LC.';
            } else {
                this.gameOverTitle = 'You Lose';
                this.gameOverMsg = (data.reason === 'resign' ? 'You resigned' : data.reason === 'timeout' ? 'You ran out of time' : 'Checkmate.') + ' You lost ' + data.stake + ' LC.';
            }
        },

        // Timer
        startTimer() {
            this.stopTimer();
            this.timerInterval = setInterval(() => {
                if (!this.gameActive || !this.mySide) return;
                if (this.isMyTurn) {
                    this.myTime = Math.max(0, this.myTime - 1);
                    if (this.myTime === 0) {
                        this.stopTimer();
                        this.ws.send(JSON.stringify({ action: 'timeout', side: this.mySide }));
                    }
                } else {
                    this.opponentTime = Math.max(0, this.opponentTime - 1);
                }
            }, 1000);
        },
        stopTimer() {
            if (this.timerInterval) { clearInterval(this.timerInterval); this.timerInterval = null; }
        },
        formatTime(secs) {
            var m = Math.floor(secs / 60).toString().padStart(2, '0');
            var s = (secs % 60).toString().padStart(2, '0');
            return m + ':' + s;
        },

        // Board rendering
        renderBoard() {
            var board = this.chess.board(); // 8x8 array [rank8..rank1][fileA..fileH]
            var files = ['a','b','c','d','e','f','g','h'];
            var squares = [];
            var flipped = this.mySide === 'black';
            var ranks = flipped ? [1,2,3,4,5,6,7,8] : [8,7,6,5,4,3,2,1];
            var fileOrder = flipped ? ['h','g','f','e','d','c','b','a'] : files;

            for (var r = 0; r < ranks.length; r++) {
                var rank = ranks[r];
                for (var f = 0; f < fileOrder.length; f++) {
                    var file = fileOrder[f];
                    var rankIdx = 8 - rank;
                    var fileIdx = files.indexOf(file);
                    var sq = board[rankIdx][fileIdx];
                    var name = file + rank;
                    squares.push({
                        name: name,
                        piece: sq ? sq.color + sq.type.toUpperCase() : null,
                        rank: rank.toString(),
                        file: file,
                        showRank: f === 0,
                        showFile: r === ranks.length - 1,
                        isLight: (files.indexOf(file) + rank) % 2 === 1,
                    });
                }
            }
            this.boardSquares = squares;
        },

        squareClass(sq) {
            var base = sq.isLight ? 'chess-sq light' : 'chess-sq dark-sq';
            var selected = this.selectedSq === sq.name ? ' selected' : '';
            var isLegal = this.legalMoves.some(function(m) { return m.to === sq.name; }) && !this.chess.get(sq.name) ? ' legal-move' : '';
            var isCapture = this.legalMoves.some(function(m) { return m.to === sq.name; }) && this.chess.get(sq.name) ? ' legal-capture' : '';
            var isLast = this.lastMove && (sq.name === this.lastMove.from || sq.name === this.lastMove.to) ? ' last-move-sq' : '';
            var inCheck = this.chess.in_check() && sq.piece && sq.piece[1] === 'K' && sq.piece[0] === this.chess.turn() ? ' in-check' : '';
            return base + selected + isLegal + isCapture + isLast + inCheck;
        },

        pieceChar(piece) {
            var map = {
                wK: '\u2654', wQ: '\u2655', wR: '\u2656', wB: '\u2657', wN: '\u2658', wP: '\u2659',
                bK: '\u265a', bQ: '\u265b', bR: '\u265c', bB: '\u265d', bN: '\u265e', bP: '\u265f',
            };
            return map[piece] || '';
        },

        squareAriaLabel(sq) {
            var pieceNames = {
                wK: 'White king', wQ: 'White queen', wR: 'White rook', wB: 'White bishop', wN: 'White knight', wP: 'White pawn',
                bK: 'Black king', bQ: 'Black queen', bR: 'Black rook', bB: 'Black bishop', bN: 'Black knight', bP: 'Black pawn',
            };
            var pieceName = sq.piece ? pieceNames[sq.piece] : 'Empty';
            return sq.name + ', ' + pieceName;
        },

        canDragPiece(sq) {
            if (!this.gameActive || !this.isMyTurn || !this.mySide) return false;
            if (!sq.piece) return false;
            var color = sq.piece[0];
            return (color === 'w' && this.mySide === 'white') || (color === 'b' && this.mySide === 'black');
        },

        // Interaction
        handleSquareClick(sq) {
            if (!this.gameActive || !this.isMyTurn || !this.mySide) return;

            if (this.selectedSq === sq.name) {
                this.selectedSq = null;
                this.legalMoves = [];
                return;
            }

            if (this.selectedSq) {
                var moved = this.tryMove(this.selectedSq, sq.name);
                if (!moved) {
                    if (sq.piece && this.isMyPiece(sq.piece)) {
                        this.selectSquare(sq.name);
                    } else {
                        this.selectedSq = null;
                        this.legalMoves = [];
                    }
                }
            } else {
                if (sq.piece && this.isMyPiece(sq.piece)) {
                    this.selectSquare(sq.name);
                }
            }
        },

        selectSquare(sqName) {
            this.selectedSq = sqName;
            this.legalMoves = this.chess.moves({ square: sqName, verbose: true });
        },

        isMyPiece(piece) {
            var color = piece[0];
            return (color === 'w' && this.mySide === 'white') || (color === 'b' && this.mySide === 'black');
        },

        tryMove(from, to) {
            var piece = this.chess.get(from);
            if (piece && piece.type === 'p') {
                var toRank = parseInt(to[1]);
                if ((piece.color === 'w' && toRank === 8) || (piece.color === 'b' && toRank === 1)) {
                    // Verify this is actually a legal move before showing picker
                    var legal = this.chess.moves({ square: from, verbose: true });
                    if (!legal.some(function(m) { return m.to === to; })) return false;
                    this.pendingPromotion = { from: from, to: to };
                    this.selectedSq = null;
                    this.legalMoves = [];
                    return true;
                }
            }
            return this.executeMove(from, to, undefined);
        },

        executeMove(from, to, promotion) {
            var result = this.chess.move({ from: from, to: to, promotion: promotion });
            if (!result) return false;

            this.playMoveSound();
            this.lastMove = { from: from, to: to };
            this.fen = this.chess.fen();
            this.currentTurn = this.chess.turn();
            this.selectedSq = null;
            this.legalMoves = [];
            this.sanMoves.push(result.san);
            this.buildMovePairs();
            this.renderBoard();

            var uci = from + to + (promotion || '');
            this.ws.send(JSON.stringify({
                action: 'move',
                move: uci,
                white_time: this.mySide === 'white' ? this.myTime : this.opponentTime,
                black_time: this.mySide === 'black' ? this.myTime : this.opponentTime,
            }));

            this.checkGameEnd();
            return true;
        },

        promoteTo(pieceType) {
            if (!this.pendingPromotion) return;
            var from = this.pendingPromotion.from;
            var to = this.pendingPromotion.to;
            this.pendingPromotion = null;
            this.executeMove(from, to, pieceType);
        },

        cancelPromotion() {
            this.pendingPromotion = null;
        },

        get promotionColor() {
            if (!this.pendingPromotion) return 'w';
            var piece = this.chess.get(this.pendingPromotion.from);
            return piece ? piece.color : 'w';
        },

        checkGameEnd() {
            if (this.chess.game_over()) {
                var reason, winner;
                if (this.chess.in_checkmate()) {
                    reason = 'checkmate';
                    var loserTurn = this.chess.turn();
                    if (loserTurn === 'w') {
                        winner = this.mySide === 'black' ? this.myUsername : this.opponentName;
                    } else {
                        winner = this.mySide === 'white' ? this.myUsername : this.opponentName;
                    }
                } else {
                    reason = this.chess.in_stalemate() ? 'stalemate' : 'draw';
                    winner = null;
                }
                this.ws.send(JSON.stringify({ action: 'game_over', reason: reason, winner: winner }));
            }
        },

        // Move sound
        playMoveSound() {
            try {
                var ctx = new (window.AudioContext || window.webkitAudioContext)();
                var osc = ctx.createOscillator();
                var gain = ctx.createGain();
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.frequency.value = 480;
                gain.gain.setValueAtTime(0.12, ctx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.08);
                osc.start();
                osc.stop(ctx.currentTime + 0.08);
            } catch (e) {}
        },

        // Drag and drop
        handleDragStart(event, sq) {
            if (!this.canDragPiece(sq)) { event.preventDefault(); return; }
            this.dragFrom = sq.name;
            this.selectSquare(sq.name);
        },
        handleDrop(event) { event.preventDefault(); },
        handleDropOnSquare(event, sq) {
            event.preventDefault();
            if (!this.dragFrom) return;
            this.tryMove(this.dragFrom, sq.name);
            this.dragFrom = null;
        },

        // Actions
        resign() {
            this.confirmResign = false;
            this.ws.send(JSON.stringify({ action: 'resign' }));
        },

        // Touch drag for mobile
        handleTouchStart(event) {
            var touch = event.touches[0];
            var el = document.elementFromPoint(touch.clientX, touch.clientY);
            while (el && !el.dataset.sq) el = el.parentElement;
            if (!el || !el.dataset.sq) return;
            var sq = this.boardSquares.find(function(s) { return s.name === el.dataset.sq; });
            if (!sq || !this.canDragPiece(sq)) { this._touchDragSq = null; return; }
            this._touchDragSq = sq;
            this._touchDragStartX = touch.clientX;
            this._touchDragStartY = touch.clientY;
            this._touchDragging = false;
        },

        handleTouchMove(event) {
            if (!this._touchDragSq) return;
            var touch = event.touches[0];
            if (!this._touchDragging) {
                var dx = touch.clientX - this._touchDragStartX;
                var dy = touch.clientY - this._touchDragStartY;
                if (Math.sqrt(dx * dx + dy * dy) < 10) return;
                this._touchDragging = true;
                this.dragFrom = this._touchDragSq.name;
                this.selectSquare(this._touchDragSq.name);
                var ghost = document.createElement('span');
                var sq = this._touchDragSq;
                ghost.textContent = this.pieceChar(sq.piece);
                ghost.style.cssText = 'position:fixed;pointer-events:none;z-index:9999;font-size:2.5rem;line-height:1;opacity:0.8;transform:translate(-50%,-120%);';
                ghost.style.left = touch.clientX + 'px';
                ghost.style.top = touch.clientY + 'px';
                document.body.appendChild(ghost);
                this.touchGhost = ghost;
            }
            if (this.touchGhost) {
                this.touchGhost.style.left = touch.clientX + 'px';
                this.touchGhost.style.top = touch.clientY + 'px';
            }
        },

        handleTouchEnd(event) {
            if (this.touchGhost) { document.body.removeChild(this.touchGhost); this.touchGhost = null; }
            if (this._touchDragging && this.dragFrom) {
                var touch = event.changedTouches[0];
                var el = document.elementFromPoint(touch.clientX, touch.clientY);
                while (el && !el.dataset.sq) el = el.parentElement;
                if (el && el.dataset.sq) { this.tryMove(this.dragFrom, el.dataset.sq); }
                this.dragFrom = null;
            }
            this._touchDragSq = null;
            this._touchDragging = false;
        },
    };
}
