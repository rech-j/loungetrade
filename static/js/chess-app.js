function chessApp() {
    return {
        // ── State ─────────────────────────────────────────────
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

        mySide: null,          // 'white' | 'black' | null (spectator/pending)
        myName: 'You',
        opponentName: 'Opponent',
        myUsername: '',

        reconnectAttempts: 0,
        myTime: 600,
        opponentTime: 600,
        timerInterval: null,
        confirmResign: false,
        movePairs: [],         // [['e4', 'e5'], ['Nf3', ...], ...]
        sanMoves: [],          // all SAN moves in order

        // ── Computed ──────────────────────────────────────────
        get isMyTurn() {
            if (!this.chess || !this.mySide) return false;
            var turn = this.chess.turn(); // 'w' or 'b'
            return (turn === 'w' && this.mySide === 'white') ||
                   (turn === 'b' && this.mySide === 'black');
        },
        get myTimeLow() { return this.myTime <= 30; },
        get opponentTimeLow() { return this.opponentTime <= 30; },

        // ── Init ─────────────────────────────────────────────
        init() {
            this.chess = new Chess();
            this.renderBoard();
            this.connectWS();
        },

        connectWS() {
            var proto = location.protocol === 'https:' ? 'wss' : 'ws';
            this.ws = new WebSocket(proto + '://' + location.host + '/ws/chess/' + this.$el.dataset.gameId + '/');
            this.ws.onopen = () => { this.connected = true; this.errorMsg = ''; this.reconnectAttempts = 0; };
            this.ws.onclose = (event) => {
                this.connected = false;
                if (!this.gameOver && !event.wasClean && this.reconnectAttempts < 5) {
                    this.reconnectAttempts++;
                    this.errorMsg = 'Connection lost. Reconnecting...';
                    setTimeout(() => this.connectWS(), 3000 * this.reconnectAttempts);
                } else if (this.reconnectAttempts >= 5) {
                    this.errorMsg = 'Connection lost. Please refresh the page.';
                }
            };
            this.ws.onerror = () => { this.errorMsg = 'Connection error.'; };
            this.ws.onmessage = (e) => this.handleMessage(JSON.parse(e.data));
        },

        handleMessage(data) {
            if (data.type === 'game_state') {
                this.applyGameState(data);
            } else if (data.type === 'player_connected') {
                this.statusMsg = data.username + ' connected.';
                setTimeout(() => { this.statusMsg = ''; }, 3000);
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
                this.myTime = this.mySide === 'white' ? data.white_time : data.black_time;
                this.opponentTime = this.mySide === 'white' ? data.black_time : data.white_time;
                this.myName = this.mySide === 'white' ? data.white_player : data.black_player;
                this.opponentName = this.mySide === 'white' ? data.black_player : data.white_player;
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
                this.fen = this.chess.fen();
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

        // ── Timer ──────────────────────────────────────────────
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

        // ── Board rendering ────────────────────────────────────
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
            return base + selected + isLegal + isCapture + isLast;
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

        // ── Interaction ────────────────────────────────────────
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
            var promotion = undefined;
            if (piece && piece.type === 'p') {
                var toRank = parseInt(to[1]);
                if ((piece.color === 'w' && toRank === 8) || (piece.color === 'b' && toRank === 1)) {
                    promotion = 'q';
                }
            }
            var result = this.chess.move({ from: from, to: to, promotion: promotion });
            if (!result) return false;

            this.lastMove = { from: from, to: to };
            this.fen = this.chess.fen();
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

        // ── Drag and drop ──────────────────────────────────────
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

        // ── Actions ────────────────────────────────────────────
        resign() {
            this.confirmResign = false;
            this.ws.send(JSON.stringify({ action: 'resign' }));
        },
    };
}
