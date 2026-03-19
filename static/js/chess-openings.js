/**
 * Lightweight chess opening book.
 * Maps move sequences (space-separated SAN) to opening names.
 * Ordered longest-first so the most specific match wins.
 */
var CHESS_OPENINGS = [
    // Sicilian variations
    ['e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 a6', 'Sicilian Najdorf'],
    ['e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 g6', 'Sicilian Dragon'],
    ['e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 e5', 'Sicilian Sveshnikov'],
    ['e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 Nc6', 'Sicilian Classical'],
    ['e4 c5 Nf3 Nc6 d4 cxd4 Nxd4 Nf6 Nc3 e5', 'Sicilian Kalashnikov'],
    ['e4 c5 Nf3 e6 d4 cxd4 Nxd4 Nc6', 'Sicilian Taimanov'],
    ['e4 c5 Nf3 e6 d4 cxd4 Nxd4 a6', 'Sicilian Kan'],
    ['e4 c5 Nc3', 'Sicilian Closed'],
    ['e4 c5 c3', 'Sicilian Alapin'],
    ['e4 c5 Nf3 d6 d4', 'Sicilian Open'],
    ['e4 c5 Nf3 Nc6', 'Sicilian Defense'],
    ['e4 c5 Nf3 e6', 'Sicilian Defense'],
    ['e4 c5 Nf3', 'Sicilian Defense'],
    ['e4 c5', 'Sicilian Defense'],

    // Ruy Lopez variations
    ['e4 e5 Nf3 Nc6 Bb5 a6 Ba4 Nf6 O-O Be7', 'Ruy Lopez Closed'],
    ['e4 e5 Nf3 Nc6 Bb5 a6 Ba4 Nf6 O-O Nxe4', 'Ruy Lopez Open'],
    ['e4 e5 Nf3 Nc6 Bb5 a6 Ba4 Nf6 O-O', 'Ruy Lopez'],
    ['e4 e5 Nf3 Nc6 Bb5 a6 Ba4 Nf6', 'Ruy Lopez'],
    ['e4 e5 Nf3 Nc6 Bb5 a6 Bxc6', 'Ruy Lopez Exchange'],
    ['e4 e5 Nf3 Nc6 Bb5 Nf6', 'Ruy Lopez Berlin'],
    ['e4 e5 Nf3 Nc6 Bb5 f5', 'Ruy Lopez Schliemann'],
    ['e4 e5 Nf3 Nc6 Bb5 a6', 'Ruy Lopez Morphy Defense'],
    ['e4 e5 Nf3 Nc6 Bb5', 'Ruy Lopez'],

    // Italian Game
    ['e4 e5 Nf3 Nc6 Bc4 Bc5 c3 Nf6 d4', 'Italian Giuoco Piano'],
    ['e4 e5 Nf3 Nc6 Bc4 Bc5', 'Italian Giuoco Piano'],
    ['e4 e5 Nf3 Nc6 Bc4 Nf6', 'Italian Two Knights'],
    ['e4 e5 Nf3 Nc6 Bc4', 'Italian Game'],

    // Scotch
    ['e4 e5 Nf3 Nc6 d4 exd4 Nxd4', 'Scotch Game'],
    ['e4 e5 Nf3 Nc6 d4', 'Scotch Game'],

    // King's Gambit
    ['e4 e5 f4 exf4', 'King\'s Gambit Accepted'],
    ['e4 e5 f4 Bc5', 'King\'s Gambit Declined'],
    ['e4 e5 f4', 'King\'s Gambit'],

    // French Defense
    ['e4 e6 d4 d5 Nc3 Bb4', 'French Winawer'],
    ['e4 e6 d4 d5 Nc3 Nf6', 'French Classical'],
    ['e4 e6 d4 d5 Nd2', 'French Tarrasch'],
    ['e4 e6 d4 d5 e5', 'French Advance'],
    ['e4 e6 d4 d5 exd5 exd5', 'French Exchange'],
    ['e4 e6 d4 d5', 'French Defense'],
    ['e4 e6', 'French Defense'],

    // Caro-Kann
    ['e4 c6 d4 d5 Nc3 dxe4 Nxe4 Bf5', 'Caro-Kann Classical'],
    ['e4 c6 d4 d5 Nc3 dxe4 Nxe4 Nd7', 'Caro-Kann Karpov'],
    ['e4 c6 d4 d5 e5', 'Caro-Kann Advance'],
    ['e4 c6 d4 d5 exd5 cxd5', 'Caro-Kann Exchange'],
    ['e4 c6 d4 d5', 'Caro-Kann Defense'],
    ['e4 c6', 'Caro-Kann Defense'],

    // Pirc / Modern
    ['e4 d6 d4 Nf6 Nc3 g6', 'Pirc Defense'],
    ['e4 d6 d4 Nf6', 'Pirc Defense'],
    ['e4 g6 d4 Bg7', 'Modern Defense'],
    ['e4 g6', 'Modern Defense'],

    // Scandinavian
    ['e4 d5 exd5 Qxd5', 'Scandinavian Defense'],
    ['e4 d5 exd5 Nf6', 'Scandinavian Icelandic'],
    ['e4 d5', 'Scandinavian Defense'],

    // Alekhine
    ['e4 Nf6', 'Alekhine\'s Defense'],

    // Other e4 responses
    ['e4 e5 Nf3 Nf6', 'Petrov\'s Defense'],
    ['e4 e5 Nf3 d6', 'Philidor\'s Defense'],
    ['e4 e5 Nf3 f5', 'Latvian Gambit'],
    ['e4 e5 d4 exd4 c3', 'Danish Gambit'],
    ['e4 e5 Nf3 Nc6', 'King\'s Knight Opening'],
    ['e4 e5 Nf3', 'King\'s Knight Opening'],
    ['e4 e5', 'King\'s Pawn Game'],
    ['e4', 'King\'s Pawn Opening'],

    // Queen's Gambit
    ['d4 d5 c4 e6 Nc3 Nf6 Bg5', 'Queen\'s Gambit Declined'],
    ['d4 d5 c4 e6 Nc3 Nf6', 'Queen\'s Gambit Declined'],
    ['d4 d5 c4 e6 Nf3 Nf6 Bg5', 'Queen\'s Gambit Declined'],
    ['d4 d5 c4 dxc4', 'Queen\'s Gambit Accepted'],
    ['d4 d5 c4 c6', 'Slav Defense'],
    ['d4 d5 c4 e6', 'Queen\'s Gambit Declined'],
    ['d4 d5 c4', 'Queen\'s Gambit'],

    // Indian defenses
    ['d4 Nf6 c4 g6 Nc3 Bg7 e4 d6', 'King\'s Indian Defense'],
    ['d4 Nf6 c4 g6 Nc3 Bg7 e4', 'King\'s Indian Defense'],
    ['d4 Nf6 c4 g6 Nc3 Bg7', 'King\'s Indian Defense'],
    ['d4 Nf6 c4 g6 Nc3 d5', 'Grünfeld Defense'],
    ['d4 Nf6 c4 e6 Nc3 Bb4', 'Nimzo-Indian Defense'],
    ['d4 Nf6 c4 e6 Nf3 Bb4+', 'Bogo-Indian Defense'],
    ['d4 Nf6 c4 e6 Nf3 b6', 'Queen\'s Indian Defense'],
    ['d4 Nf6 c4 e6 g3', 'Catalan Opening'],
    ['d4 Nf6 c4 e6', 'Indian Defense'],
    ['d4 Nf6 c4 c5', 'Benoni Defense'],

    // London / System openings
    ['d4 Nf6 Bf4', 'London System'],
    ['d4 d5 Bf4', 'London System'],
    ['d4 Nf6 Nf3 g6 Bf4', 'London System'],

    // Other d4 lines
    ['d4 d5 Nf3 Nf6 c4', 'Queen\'s Gambit'],
    ['d4 d5 Nf3 Nf6', 'Queen\'s Pawn Game'],
    ['d4 d5', 'Queen\'s Pawn Game'],
    ['d4 Nf6 c4', 'Indian Defense'],
    ['d4 Nf6', 'Indian Defense'],
    ['d4 f5', 'Dutch Defense'],
    ['d4', 'Queen\'s Pawn Opening'],

    // English
    ['c4 e5 Nc3 Nf6', 'English Opening'],
    ['c4 e5', 'English Opening'],
    ['c4 c5', 'English Symmetrical'],
    ['c4 Nf6', 'English Opening'],
    ['c4', 'English Opening'],

    // Réti
    ['Nf3 d5 c4', 'Réti Opening'],
    ['Nf3 d5 g3', 'Réti Opening'],
    ['Nf3 d5', 'Réti Opening'],
    ['Nf3 Nf6 c4', 'Réti Opening'],
    ['Nf3 Nf6', 'King\'s Indian Attack'],
    ['Nf3', 'Réti Opening'],

    // Others
    ['b3', 'Larsen\'s Opening'],
    ['g3', 'King\'s Fianchetto Opening'],
    ['f4', 'Bird\'s Opening'],
];

/**
 * Given an array of SAN moves, return the most specific opening name or ''.
 */
function detectOpening(sanMoves) {
    if (!sanMoves || sanMoves.length === 0) return '';
    var moveStr = sanMoves.join(' ');
    for (var i = 0; i < CHESS_OPENINGS.length; i++) {
        var seq = CHESS_OPENINGS[i][0];
        if (moveStr === seq || moveStr.indexOf(seq + ' ') === 0) {
            return CHESS_OPENINGS[i][1];
        }
    }
    return '';
}
