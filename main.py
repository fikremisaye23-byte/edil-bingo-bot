<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Temerachi Bingo</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <script src="https://www.gstatic.com/firebasejs/10.14.1/firebase-app-compat.js"></script>
    <script src="https://www.gstatic.com/firebasejs/10.14.1/firebase-auth-compat.js"></script>
    <script src="https://www.gstatic.com/firebasejs/10.14.1/firebase-database-compat.js"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0b0f19;
            --card-bg: #131b2e;
            --cell-bg: #1c2640;
            --accent-color: #3b82f6;
            --text-color: #ffffff;
            --danger-color: #ef4444;
            --success-color: #10b981;
            --orange-color: #f59e0b;
            --btn-green: #10b981;
            --btn-blue: #06b6d4;
            --shadow-soft: 0 4px 14px rgba(0, 0, 0, 0.35);
            --shadow-strong: 0 8px 24px rgba(0, 0, 0, 0.45);
        }

        body {
            font-family: 'Poppins', Arial, sans-serif;
            background: radial-gradient(circle at 50% 0%, #1a1836 0%, #0b0f19 55%, #090c14 100%);
            color: var(--text-color);
            margin: 0;
            padding: 4px;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding-bottom: 90px;
            overflow-x: hidden;
            min-height: 100vh;
        }

        .screen {
            display: none;
            width: 100%;
            max-width: 400px;
            flex-direction: column;
            align-items: center;
        }

        .screen.active {
            display: flex;
        }

        h2 {
            margin: 6px 0 10px 0;
            text-align: center;
            color: var(--orange-color);
            font-size: 21px;
            font-weight: 700;
            letter-spacing: 0.3px;
            text-shadow: 0 0 14px rgba(245, 158, 11, 0.35);
        }

        .menu-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 36px 14px;
            width: 100%;
            margin-bottom: 15px;
        }

        .btn {
            background: linear-gradient(145deg, #0891b2, var(--btn-blue));
            color: white;
            border: none;
            padding: 13px 8px;
            font-size: 15px;
            font-weight: 600;
            border-radius: 12px;
            cursor: pointer;
            width: 100%;
            text-align: center;
            box-sizing: border-box;
            box-shadow: var(--shadow-soft);
            transition: transform 0.12s ease, box-shadow 0.12s ease, filter 0.12s ease;
        }

        .btn:active {
            transform: scale(0.97);
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
            filter: brightness(0.95);
        }

        .btn-green { background: linear-gradient(145deg, #059669, var(--btn-green)); }
        .btn-danger { background: linear-gradient(145deg, #dc2626, var(--danger-color)); }
        .btn-orange { background: linear-gradient(145deg, #d97706, var(--orange-color)); color: #1a1200; }

        .main-card {
            background: linear-gradient(160deg, #182342, var(--card-bg));
            border-radius: 16px;
            padding: 15px;
            width: 100%;
            box-sizing: border-box;
            margin-bottom: 15px;
            border: 1px solid #263450;
            text-align: center;
            box-shadow: var(--shadow-soft);
        }

        .selection-top-stats {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr 1fr;
            gap: 6px;
            width: 100%;
            background: linear-gradient(160deg, #182342, var(--card-bg));
            padding: 8px;
            border-radius: 12px;
            box-sizing: border-box;
            margin-bottom: 12px;
            border: 1px solid #263450;
            box-shadow: var(--shadow-soft);
        }

        .stat-box {
            background: linear-gradient(160deg, #1f2a44, #192237);
            border: 1px solid #2e3d5c;
            border-radius: 10px;
            padding: 6px 4px;
            text-align: center;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.04);
        }

        .stat-box span {
            font-size: 11px;
            color: #94a3b8;
            display: block;
            margin-bottom: 2px;
        }

        .stat-box b {
            font-size: 14px;
            color: white;
        }

        .number-grid {
            display: grid;
            grid-template-columns: repeat(8, 1fr);
            gap: 6px;
            width: 100%;
            height: 540px;
            overflow-y: auto;
            background: linear-gradient(160deg, #182342, var(--card-bg));
            padding: 12px;
            border-radius: 12px;
            box-sizing: border-box;
            margin-bottom: 10px;
            border: 1px solid #263450;
            box-shadow: var(--shadow-soft);
        }

        .num-cell {
            aspect-ratio: 1;
            background: linear-gradient(160deg, #223052, var(--cell-bg));
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            user-select: none;
            box-shadow: 0 2px 6px rgba(0,0,0,0.25);
            transition: transform 0.1s ease, background 0.15s ease;
        }

        .num-cell:active {
            transform: scale(0.93);
        }

        .num-cell.selected {
            background: linear-gradient(160deg, #ef4444, var(--danger-color));
            color: white;
            border: 2px solid #fff;
            box-shadow: 0 0 10px rgba(239, 68, 68, 0.5);
        }

        .num-cell.taken {
            background: linear-gradient(160deg, #7f1d1d, #5c1616);
            color: #d4a5a5;
            cursor: not-allowed;
            opacity: 0.7;
            box-shadow: none;
        }

        .bingo-card-container {
            background: linear-gradient(160deg, #182342, var(--card-bg));
            border-radius: 10px;
            padding: 4px;
            width: 100%;
            box-sizing: border-box;
            margin-bottom: 4px;
            border: 1px solid var(--accent-color);
            box-shadow: var(--shadow-soft);
        }

        .bingo-table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 2px;
            text-align: center;
        }

        .bingo-table th {
            background: linear-gradient(160deg, #5b9bff, var(--accent-color));
            color: white;
            font-size: 12px;
            padding: 3px 0;
            border-radius: 3px;
        }

        .bingo-table td {
            background: linear-gradient(160deg, #223052, var(--cell-bg));
            border-radius: 3px;
            height: 27px;
            font-size: 13px;
            font-weight: 600;
        }

        .bingo-table td.marked {
            background: var(--danger-color) !important;
            color: white;
        }

        .bingo-table td.free {
            background: var(--success-color) !important;
            color: white;
        }

        .bingo-grid {
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 2px;
        }

        .bingo-card-container.compact {
            padding: 3px;
            margin-bottom: 3px;
        }

        .bingo-grid.compact {
            gap: 1px;
        }

        .bingo-header-cell.compact {
            font-size: 10px;
            padding: 2px 0;
            border-radius: 10px;
        }

        .bingo-cell.compact {
            font-size: 11px;
            border-radius: 5px;
        }

        .bingo-header-cell {
            background: linear-gradient(160deg, #5b9bff, var(--accent-color));
            color: white;
            font-size: 12px;
            font-weight: 700;
            padding: 5px 0;
            border-radius: 16px;
            text-align: center;
        }

        .bingo-header-cell:nth-child(1) { background: linear-gradient(160deg, #5b9bff, #3b82f6); } /* B */
        .bingo-header-cell:nth-child(2) { background: linear-gradient(160deg, #a78bfa, #8b5cf6); } /* I */
        .bingo-header-cell:nth-child(3) { background: linear-gradient(160deg, #c084fc, #a855f7); } /* N */
        .bingo-header-cell:nth-child(4) { background: linear-gradient(160deg, #34d399, #10b981); } /* G */
        .bingo-header-cell:nth-child(5) { background: linear-gradient(160deg, #fb923c, #f97316); } /* O */

        .bingo-cell {
            aspect-ratio: 1.15 / 1;
            background: #e9ecf2;
            color: #1e293b;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 700;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .bingo-cell.marked {
            background: var(--danger-color) !important;
            color: white;
        }

        .bingo-cell.free {
            background: var(--success-color) !important;
            color: white;
        }

        .bingo-cell.win-pattern {
            background: var(--success-color) !important;
            color: white;
        }

        .bingo-cell.called-not-pattern {
            background: var(--orange-color) !important;
            color: white;
        }

        .called-circle {
            width: 30px;
            height: 30px;
            background: #ffffff;
            border: 3px solid #f5b301;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 11px;
            font-weight: 800;
            margin: 3px auto;
            box-shadow: 0 0 12px rgba(245, 179, 1, 0.45);
            position: relative;
        }

        @keyframes calledPop {
            0% { transform: scale(0.4); opacity: 0.3; }
            55% { transform: scale(1.25); opacity: 1; }
            75% { transform: scale(0.92); }
            100% { transform: scale(1); }
        }

        .called-circle.pop {
            animation: calledPop 0.45s cubic-bezier(0.34, 1.56, 0.64, 1);
        }

        .called-circle::after {
            content: '';
            position: absolute;
            top: -1px;
            right: -4px;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #f5b301;
            opacity: 0.85;
        }

        .recent-call-badge {
            width: 38px;
            height: 38px;
            min-width: 38px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 11px;
            font-weight: 700;
            color: white;
            box-shadow: 0 2px 6px rgba(0,0,0,0.3);
            animation: calledPop 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
        }

        #customModal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.85);
            z-index: 1000;
            justify-content: center;
            align-items: center;
            padding: 10px;
            box-sizing: border-box;
        }

        .modal-content {
            background: linear-gradient(145deg, #162035, #0d1322);
            padding: 18px;
            border-radius: 20px;
            width: 100%;
            max-width: 340px;
            border: 1px solid rgba(245, 158, 11, 0.3);
            text-align: center;
            box-shadow: 0 10px 30px rgba(0,0,0,0.6);
            box-sizing: border-box;
            max-height: 90vh;
            overflow-y: auto;
        }

        @keyframes depositSpin {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
        }

        .deposit-spinner {
            width: 46px;
            height: 46px;
            border: 4px solid #2e3b55;
            border-top: 4px solid var(--orange-color);
            border-radius: 50%;
            margin: 10px auto;
            animation: depositSpin 0.9s linear infinite;
        }

        .deposit-method-card {
            display: flex;
            align-items: center;
            gap: 10px;
            background: #1c2640;
            border: 1px solid #2e3b55;
            border-radius: 10px;
            padding: 10px 12px;
            margin-bottom: 8px;
            cursor: pointer;
            text-align: left;
        }

        .deposit-method-card:active {
            border-color: var(--orange-color);
        }

        .deposit-amount-btn {
            background: #1c2640;
            border: 1px solid #2e3b55;
            color: white;
            border-radius: 8px;
            padding: 10px 0;
            font-size: 14px;
            font-weight: bold;
            cursor: pointer;
        }

        .deposit-amount-btn.active {
            background: var(--orange-color);
            border-color: var(--orange-color);
            color: #1a1200;
        }

        .nav-bar {
            position: fixed;
            bottom: 0;
            left: 0;
            width: 100%;
            background: linear-gradient(180deg, #0d1220, #070a10);
            display: flex;
            justify-content: space-around;
            padding: 12px 0 calc(12px + env(safe-area-inset-bottom, 0px)) 0;
            border-top: 1px solid #263450;
            box-shadow: 0 -6px 18px rgba(0,0,0,0.35);
            z-index: 100;
            box-sizing: border-box;
        }

        .nav-item {
            background: none;
            border: none;
            color: #64748b;
            font-size: 13px;
            cursor: pointer;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 2px;
            transition: color 0.15s ease, transform 0.1s ease;
        }

        .nav-item:active { transform: scale(0.95); }

        .nav-item.active { color: var(--btn-blue); text-shadow: 0 0 10px rgba(6, 182, 212, 0.5); }

        #customToast {
            display: none;
            position: fixed;
            left: 50%;
            bottom: 80px;
            transform: translateX(-50%);
            background: linear-gradient(145deg, #162035, #0d1322);
            color: #ffffff;
            padding: 12px 18px;
            border-radius: 12px;
            border: 1px solid rgba(245, 158, 11, 0.4);
            box-shadow: 0 10px 30px rgba(0,0,0,0.6);
            font-size: 14px;
            font-weight: bold;
            text-align: center;
            max-width: 90%;
            z-index: 2000;
            opacity: 0;
            transition: opacity 0.25s ease;
        }

        #customToast.show {
            display: block;
            opacity: 1;
        }
    </style>
</head>
<body>

    <!-- WINNER MODAL / POPUP -->
    <div id="customModal" style="display: none;">
        <div class="modal-content" id="modalBodyText"></div>
    </div>

    <!-- TOAST (replaces native alert popups) -->
    <div id="customToast"></div>

    <!-- 1.5 STAKE SELECTION SCREEN -->
    <div id="stakeScreen" class="screen active">
        <div style="display: flex; justify-content: space-between; align-items: center; width: 100%; margin-bottom: 10px;">
            <h2 style="margin: 0; font-size: 16px; text-align: center; flex: 1;">▷ Choose Your Stake</h2>
            <div style="width: 54px;"></div>
        </div>

        <div class="main-card" style="display: flex; flex-direction: column; gap: 10px;">
            <button class="btn btn-green" style="font-size: 17px; padding: 15px 8px;" onclick="chooseStake(10)">▷ Play 10</button>
            <button class="btn" style="font-size: 17px; padding: 15px 8px;" onclick="chooseStake(20)">▷ Play 20</button>
        </div>

        <div class="selection-top-stats" style="grid-template-columns: 1fr;">
            <div class="stat-box">
                <span>Active Players</span>
                <b id="statActivePlayers" style="font-size: 18px;">0</b>
            </div>
            <div class="stat-box">
                <span>Games Played</span>
                <b id="statGamesPlayed" style="font-size: 18px;">0</b>
            </div>
            <div class="stat-box">
                <span>Winners Daily</span>
                <b id="statWinnersDaily" style="font-size: 18px;">0</b>
            </div>
        </div>
    </div>

    <!-- 2. NUMBER SELECTION SCREEN -->
    <div id="selectScreen" class="screen">
        <div style="display: flex; justify-content: space-between; align-items: center; width: 100%; margin-bottom: 6px;">
            <button class="btn btn-danger" style="width: auto; padding: 6px 12px; font-size: 13px;" onclick="switchNav('stakeScreen', 'navGame')">✕ Back</button>
            <h2 style="margin: 0; font-size: 13px; text-align: center; line-height: 1.2; flex: 1;">Temerachi Bingo</h2>
            <button class="btn" style="width: auto; padding: 6px 12px; font-size: 13px;" onclick="openSelection()">🔄 Refresh</button>
        </div>

        <div class="selection-top-stats" style="grid-template-columns: 1fr 1fr 1fr 1fr;">
            <div class="stat-box">
                <span style="font-size: 9px;">Main Wallet</span>
                <b id="selMainWallet" style="font-size: 13px;">0</b>
            </div>
            <div class="stat-box">
                <span style="font-size: 9px;">Play Wallet</span>
                <b id="selPlayWallet" style="font-size: 13px;">0</b>
            </div>
            <div class="stat-box">
                <span style="font-size: 9px;">Stake</span>
                <b id="selStakeDisplay" style="font-size: 13px;">10</b>
            </div>
            <div class="stat-box" style="background: #231c12; border-color: #533d1e;">
                <span style="color: #f59e0b; font-size: 9px;">Timer</span>
                <b id="selectionTimer" style="color: #f59e0b; font-size: 13px;">50s</b>
            </div>
        </div>
        
        <div id="selectedCardsPreviewContainer" style="width: 100%; display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-bottom: 10px;">
            <div style="font-size: 13px; color: #64748b; text-align: center; width: 100%; padding: 4px;">ካርቴላ ለመምረጥ ከላይ ያሉትን ቁጥሮች ይጫኑ (ከፍተኛ 2)</div>
        </div>

        <div class="number-grid" id="numberGrid"></div>
    </div>

    <!-- 3. LIVE GAME ROOM SCREEN -->
    <div id="gameScreen" class="screen" style="max-width: 420px;">
        <!-- Top Info Header -->
        <div style="display: grid; grid-template-columns: repeat(5, 1fr); gap: 4px; width: 100%; background: var(--card-bg); padding: 5px; border-radius: 8px; margin-bottom: 6px; border: 1px solid #1e293b; text-align: center; box-sizing: border-box;">
            <div style="background: #192237; border-radius: 5px; padding: 3px;">
                <div style="font-size: 12px; color: #94a3b8;">Game ID</div>
                <div id="gameIdDisplay" style="font-size: 14px; font-weight: bold; color: var(--orange-color);">BBX54</div>
            </div>
            <div style="background: #192237; border-radius: 5px; padding: 3px;">
                <div style="font-size: 12px; color: #94a3b8;">Players</div>
                <div style="font-size: 14px; font-weight: bold; color: white;" id="activePlayersCountDisplay">2</div>
            </div>
            <div style="background: #192237; border-radius: 5px; padding: 3px;">
                <div style="font-size: 12px; color: #94a3b8;">Bet</div>
                <div style="font-size: 14px; font-weight: bold; color: white;">10</div>
            </div>
            <div style="background: #192237; border-radius: 5px; padding: 3px;">
                <div style="font-size: 12px; color: #94a3b8;">Derash 🪙</div>
                <div id="gamePrizeDisplay" style="font-size: 14px; font-weight: bold; color: var(--success-color);">16</div>
            </div>
            <div style="background: #192237; border-radius: 5px; padding: 3px;">
                <div style="font-size: 12px; color: #94a3b8;">Called</div>
                <div id="calledCountDisplay" style="font-size: 14px; font-weight: bold; color: var(--orange-color);">0</div>
            </div>
        </div>

        <div style="display: flex; gap: 8px; width: 100%; margin-bottom: 6px; box-sizing: border-box; min-height: 0;">
            <!-- Left Side: 5-Column BINGO Board -->
            <div style="width: 40%; display: flex; flex-direction: column; min-height: 0;">
                <div id="masterBoardCard" style="background: var(--card-bg); border-radius: 10px; padding: 4px; border: 1px solid #1e293b; box-sizing: border-box; display: flex; flex-direction: column; flex: 1; min-height: 0;">
                    <div id="masterBoardHeader" style="display: grid; grid-template-columns: repeat(5, 1fr); gap: 2px; text-align: center; margin-bottom: 3px;">
                        <div style="background: #3b82f6; color: white; font-size: 12px; font-weight: bold; padding: 3px 0; border-radius: 3px;">B</div>
                        <div style="background: #8b5cf6; color: white; font-size: 12px; font-weight: bold; padding: 3px 0; border-radius: 3px;">I</div>
                        <div style="background: #a855f7; color: white; font-size: 12px; font-weight: bold; padding: 3px 0; border-radius: 3px;">N</div>
                        <div style="background: #10b981; color: white; font-size: 12px; font-weight: bold; padding: 3px 0; border-radius: 3px;">G</div>
                        <div style="background: #f97316; color: white; font-size: 12px; font-weight: bold; padding: 3px 0; border-radius: 3px;">O</div>
                    </div>
                    <div id="gameBoardGrid" style="display: grid; grid-template-columns: repeat(5, 1fr); grid-template-rows: repeat(15, 1fr); gap: 2px; flex: 1; min-height: 0;"></div>
                </div>
            </div>

            <!-- Right Side: Called Number & User Cartelas (Strictly fitted to avoid bottom cutoff) -->
            <div id="rightColumnWrapper" style="width: 60%; display: flex; flex-direction: column; gap: 4px;">
                <div style="display: flex; justify-content: space-between; align-items: center; background: var(--card-bg); padding: 3px 6px; border-radius: 8px; border: 1px solid #1e293b; width: calc(100% - 28px); margin: 0 auto; box-sizing: border-box;">
                    <div style="display: flex; gap: 3px; flex-wrap: wrap; max-height: 42px; overflow-y: auto; overflow-x: hidden; align-content: flex-start;" id="recentCalledContainer"></div>
                    <button onclick="toggleAudio()" id="audioToggleBtn" style="background: none; border: none; color: white; font-size: 13px; cursor: pointer;">🔊</button>
                </div>

                <div style="background: var(--card-bg); border-radius: 8px; padding: 4px; text-align: center; border: 1px solid #1e293b; width: calc(100% - 28px); margin: 0 auto; box-sizing: border-box;">
                    <div class="called-circle" id="currentCalledNum">-</div>
                    <div id="gameStatusText" style="font-size: 10px; color: var(--orange-color); font-weight: bold; margin-top: 1px;">Game in progress...</div>
                </div>

                <!-- User Cards Container with exact max-height and overflow scroll -->
                <div id="userCardsContainer" style="width: 100%; display: flex; flex-direction: column; gap: 4px; padding-right: 2px;"></div>
            </div>
        </div>


        <!-- Bottom Action Buttons -->
        <div style="display: flex; gap: 6px; width: 100%; margin-top: 2px;">
            <button class="btn btn-danger" style="padding: 7px; font-size: 11px; flex: 1;" onclick="goBackToSelection()">Leave</button>
            <button class="btn btn-orange" style="padding: 7px; font-size: 11px; flex: 1;" onclick="openSelection()">🔄 Refresh</button>
            <button id="gameAutomaticBtn" class="btn btn-green" style="padding: 7px; font-size: 11px; flex: 1;" onclick="alert('Automatic mode is active!')">Automatic</button>
        </div>
    </div>

    <!-- 4. WALLET SCREEN -->
    <div id="walletScreen" class="screen">
        <h2>🪙 Your Wallets</h2>
        <div class="main-card">
            <div style="font-size: 13px; color: #94a3b8; margin-bottom: 4px;">Main Wallet (withdrawable winnings)</div>
            <div id="mainWalletBalanceDisplay" style="color: var(--success-color); font-size: 24px; font-weight: bold; margin-bottom: 10px;">0 coins</div>
            <button class="btn btn-orange" onclick="handleWithdraw()">Withdraw 💸</button>
        </div>

        <div class="main-card">
            <div style="font-size: 13px; color: #94a3b8; margin-bottom: 4px;">Play Wallet (used to join games)</div>
            <div id="playWalletBalanceDisplay" style="color: var(--btn-blue); font-size: 24px; font-weight: bold; margin-bottom: 10px;">0 coins</div>
            <button class="btn btn-green" onclick="handleDeposit()">Deposit 🪙</button>
        </div>

        <div class="main-card">
            <div style="font-size: 12px; color: #64748b;">
                Play Wallet coins are used to join games. When you win a game, winnings automatically move to your Main Wallet. Deposits go into your Play Wallet. Only real deposited winnings can be withdrawn from your Main Wallet.
            </div>
        </div>
    </div>

    <!-- 5. PROFILE SCREEN -->
    <div id="profileScreen" class="screen">
        <h2>👤 User Profile</h2>
        <div class="main-card" style="text-align: left;">
            <div style="margin-bottom: 12px; font-size: 14px;"><b>Name:</b> <span id="profileNameDisplay">Player</span></div>
            <div style="margin-bottom: 12px; font-size: 14px;"><b>ID:</b> <span id="profileIdDisplay">#849201</span></div>
            <div style="margin-bottom: 12px; font-size: 14px;"><b>Status:</b> <span id="userStatusDisplay" style="color: var(--danger-color);">Not Registered ❌</span></div>
            <div style="margin-bottom: 15px; font-size: 13px;"><b>Invite Link:</b> <span id="profileRefLink" style="color: var(--btn-blue);">t.me/Temerachibingo_bot?start=ref849201</span></div>
            <button class="btn" onclick="handleInvite()">Invite Friends 🔗</button>
            <button class="btn btn-green" onclick="showInstructions()">Instruction 📖</button>
            <div id="adminLinkContainer" style="text-align:center; margin-top:14px; display:none;">
                <span onclick="openAdminPanel()" style="font-size:11px; color:#475569; cursor:pointer;">🛠 Admin <span id="adminPendingBadge" style="display:none; background:var(--danger-color); color:white; border-radius:10px; padding:1px 6px; font-size:10px; font-weight:bold; margin-left:2px;"></span></span>
            </div>
        </div>
    </div>

    <div id="adminScreen" class="screen">
        <h2>🛠 Admin Panel</h2>
        <button class="btn" style="margin-bottom:12px;" onclick="switchNav('profileScreen', 'navProfile')">⬅ Back to Profile</button>

        <div class="main-card" style="text-align:left;">
            <div style="font-weight:bold; color:var(--orange-color); margin-bottom:8px;">⏳ Pending Deposits</div>
            <div id="adminDepositsList" style="font-size:13px; color:#94a3b8;">Loading...</div>
        </div>

        <div class="main-card" style="text-align:left;">
            <div style="font-weight:bold; color:var(--orange-color); margin-bottom:8px;">⏳ Pending Withdrawals</div>
            <div id="adminWithdrawalsList" style="font-size:13px; color:#94a3b8;">Loading...</div>
        </div>
    </div>
    <div class="nav-bar">
        <button class="nav-item active" id="navGame" onclick="switchNav('stakeScreen', 'navGame')">🎮 Game</button>
        <button class="nav-item" id="navProfile" onclick="switchNav('profileScreen', 'navProfile')">👤 Profile</button>
    </div>

    <script>
        let toastTimer = null;
        function showToast(message, duration = 2500) {
            let toastEl = document.getElementById('customToast');
            if (!toastEl) return;
            toastEl.innerText = message;
            toastEl.classList.add('show');
            if (toastTimer) clearTimeout(toastTimer);
            toastTimer = setTimeout(function() {
                toastEl.classList.remove('show');
            }, duration);
        }
        window.alert = showToast;

        let tg = null;
        let telegramUserId = "guest_user";
        let userName = "Player";
        let soundEnabled = true;

        try {
            if (window.Telegram && window.Telegram.WebApp) {
                tg = window.Telegram.WebApp;
                tg.expand();
                tg.ready();
                if (tg.initDataUnsafe && tg.initDataUnsafe.user) {
                    telegramUserId = tg.initDataUnsafe.user.id.toString();
                    userName = (tg.initDataUnsafe.user.first_name || "") + " " + (tg.initDataUnsafe.user.last_name || "");
                    userName = userName.trim() || "Player";
                }
            }
        } catch (e) {
            console.log("Telegram WebApp not initialized");
        }

        let userShortId = telegramUserId !== "guest_user" ? telegramUserId.slice(-6) : "849201";
        document.getElementById('profileNameDisplay').innerText = userName;
        document.getElementById('profileIdDisplay').innerText = "#" + userShortId;
        
        let refLinkText = `t.me/Temerachibingo_bot?start=ref${userShortId}`;
        let profileRefEl = document.getElementById('profileRefLink');
        if (profileRefEl) profileRefEl.innerText = refLinkText;

        let selectedCards = [];
        let selectionInterval = null;
        let selectedStake = 10;

        // --- Firebase (shared card locking across players) ---
        const firebaseConfig = {
            apiKey: "AIzaSyB26jKNQA-ydGWf8Boq5572AgaQcVHN8N8",
            authDomain: "edil-bingo.firebaseapp.com",
            databaseURL: "https://edil-bingo-default-rtdb.firebaseio.com",
            projectId: "edil-bingo",
            storageBucket: "edil-bingo.firebasestorage.app",
            messagingSenderId: "744593373916",
            appId: "1:744593373916:web:b14e2fdd9816071e221219"
        };
        let db = null;
        try {
            firebase.initializeApp(firebaseConfig);
            db = firebase.database();
            firebase.auth().signInAnonymously().catch(function(e) {
                console.log("Anonymous sign-in failed", e);
            });
            firebase.auth().onAuthStateChanged(function(user) {
                if (user) {
                    initStatsTracking();
                    loadUserWalletFromFirebase();
                    loadUserRegistrationFromFirebase();
                    watchPendingRequestsForAdmin();
                }
            });
        } catch (e) {
            console.log("Firebase init failed", e);
        }

        // --- Wallet balances now live in Firebase (users/<id>/wallet) so they survive refresh ---
        // Uses a live listener (not once()) so a change made elsewhere -- e.g. an admin
        // approving a deposit from the Telegram bot -- shows up immediately here too,
        // instead of only appearing the next time the Mini App is reopened.
        function loadUserWalletFromFirebase() {
            if (!db) return;
            db.ref('users/' + telegramUserId + '/wallet').on('value', function(snap) {
                let w = snap.val();
                isApplyingRemoteWalletUpdate = true;
                if (w && typeof w.main === 'number' && typeof w.play === 'number') {
                    mainWalletBalance = w.main;
                    playWalletBalance = w.play;
                    depositedBalance = typeof w.deposited === 'number' ? w.deposited : 0;
                    updateWalletDisplay();
                } else {
                    isApplyingRemoteWalletUpdate = false;
                    db.ref('users/' + telegramUserId + '/wallet').set({ main: mainWalletBalance, play: playWalletBalance, deposited: depositedBalance });
                    updateWalletDisplay();
                    return;
                }
                isApplyingRemoteWalletUpdate = false;
            }, function(err) {
                console.log('Wallet load failed', err);
            });
        }

        // --- Registration status now lives in Firebase (users/<id>/registered) too ---
        function loadUserRegistrationFromFirebase() {
            if (!db) return;
            db.ref('users/' + telegramUserId + '/registered').once('value').then(function(snap) {
                if (snap.val() === true) {
                    isRegistered = true;
                    localStorage.setItem(storageKey, "true");
                    let statusEl = document.getElementById('userStatusDisplay');
                    if (statusEl) {
                        statusEl.innerText = "Registered 📝";
                        statusEl.style.color = "var(--success-color)";
                    }
                }
            }).catch(function(err) {
                console.log('Registration load failed', err);
            });

            db.ref('users/' + telegramUserId + '/hasUsedFreeGame').once('value').then(function(snap) {
                hasUsedFreeGame = (snap.val() === true);
            }).catch(function(err) {
                console.log('Free game flag load failed', err);
            });
        }

        // --- Live stats: start at 0, count for real as the app is actually used ---
        let statsListenersAttached = false;
        let currentRoundId = null;

        function initStatsTracking() {
            if (!db || statsListenersAttached) return;
            statsListenersAttached = true;

            // Active Players = number of currently-connected users (real-time presence)
            try {
                let presenceRef = db.ref('presence/' + telegramUserId);
                presenceRef.set(true);
                presenceRef.onDisconnect().remove();
            } catch (e) {
                console.log("Presence setup failed", e);
            }
            db.ref('presence').on('value', function(snapshot) {
                let val = snapshot.val();
                let count = val ? Object.keys(val).length : 0;
                let el = document.getElementById('statActivePlayers');
                if (el) el.innerText = count;
            });

            // Games Played = total completed rounds, counted once per round
            db.ref('stats/gamesPlayed').on('value', function(snapshot) {
                let el = document.getElementById('statGamesPlayed');
                if (el) el.innerText = snapshot.val() || 0;
            });

            // Winners Daily = winners counted today, resets automatically each new day
            let todayKey = new Date().toISOString().slice(0, 10);
            db.ref('stats/winnersDaily/' + todayKey).on('value', function(snapshot) {
                let el = document.getElementById('statWinnersDaily');
                if (el) el.innerText = snapshot.val() || 0;
            });
        }

        // Called once per round when it actually ends, so the counters reflect real games
        function recordGameCompletion(winnersCount) {
            if (!db) return;
            let claimId = currentRoundId || 'unknown_' + Math.floor(Date.now() / 60000);
            db.ref('stats/countedRounds/' + claimId).transaction(function(current) {
                if (current === null) return true;
                return; // abort — this round was already counted
            }).then(function(result) {
                if (result.committed) {
                    db.ref('stats/gamesPlayed').transaction(function(c) { return (c || 0) + 1; });
                    let todayKey = new Date().toISOString().slice(0, 10);
                    db.ref('stats/winnersDaily/' + todayKey).transaction(function(c) { return (c || 0) + winnersCount; });
                }
            }).catch(function(err) {
                console.log("Stats update failed", err);
            });
        }

        let takenCardsData = {};
        let takenCardsListenerAttached = false;
        let calledNumbersListenerAttached = false;
        let isRoundCaller = false;
        let callerLockListenerAttached = false;
        let payoutAppliedForRound = false;
        let roundEndListenerAttached = false;
        let winnerPopupShown = false;
        let roomRoundEndedCached = false;

        function renderTakenCardsUI() {
            for (let i = 1; i <= 600; i++) {
                let cellEl = document.getElementById(`grid_cell_${i}`);
                if (!cellEl) continue;
                let info = takenCardsData[i];
                if (info && info.by !== telegramUserId) {
                    cellEl.classList.add('taken');
                    cellEl.classList.remove('selected');
                } else {
                    cellEl.classList.remove('taken');
                }
            }
            let activePlayersCountDisplay = document.getElementById('activePlayersCountDisplay');
            if (activePlayersCountDisplay) {
                let uniquePlayers = new Set(Object.values(takenCardsData).map(v => v.by));
                if (uniquePlayers.size > 0) activePlayersCountDisplay.innerText = uniquePlayers.size;
            }
        }

        function subscribeTakenCards() {
            if (!db) return;
            if (takenCardsListenerAttached) { renderTakenCardsUI(); return; }
            takenCardsListenerAttached = true;
            db.ref('room/takenCards').on('value', function(snapshot) {
                takenCardsData = snapshot.val() || {};
                renderTakenCardsUI();
            });
        }

        function joinOrResetRound() {
            if (!db) return;
            let myRoundValue = null;
            db.ref('room/roundEnded').once('value').then(function(endedSnap) {
                let isEnded = endedSnap.val() === true;
                return db.ref('room/roundId').transaction(function(current) {
                    if (!current || isEnded || (Date.now() - current) > 90000) {
                        myRoundValue = Date.now();
                        return myRoundValue;
                    }
                    return current;
                });
            }).then(function(result) {
                currentRoundId = result.snapshot.val();
                if (result.committed && myRoundValue && result.snapshot.val() === myRoundValue) {
                    db.ref('room/takenCards').remove();
                    db.ref('room/calledNumbers').remove();
                    db.ref('room/winnerCards').remove();
                    db.ref('room/roundEnded').remove();
                    db.ref('room/caller').remove();
                    db.ref('room/prizePool').remove();
                    db.ref('room/roundFinalizing').remove();
                }
                winnerPopupShown = false;
                roomRoundEndedCached = false;
                subscribeTakenCards();
            }).catch(function(err) {
                console.log("Firebase round join failed", err);
                winnerPopupShown = false;
                roomRoundEndedCached = false;
                subscribeTakenCards();
            });
        }

        function claimCardInFirebase(cellNum, onSuccess, onTaken) {
            if (!db) { onSuccess(generateBingoMatrix()); return; }
            let newMatrix = generateBingoMatrix();
            db.ref('room/takenCards/' + cellNum).transaction(function(current) {
                if (current === null) {
                    return { by: telegramUserId, name: userName, matrix: newMatrix };
                }
                return; // abort - already taken
            }).then(function(result) {
                if (result.committed) {
                    onSuccess(result.snapshot.val().matrix);
                } else {
                    onTaken();
                }
            }).catch(function(err) {
                console.log("Firebase claim failed", err);
                onSuccess(newMatrix); // fail open if offline, so the game still works
            });
        }

        function releaseCardInFirebase(cellNum) {
            if (!db) return;
            db.ref('room/takenCards/' + cellNum).remove();
        }
        // --- end Firebase card locking ---

        // --- Shared number-calling + real winner detection across all real players ---
        function subscribeCalledNumbers() {
            if (!db) return;
            if (calledNumbersListenerAttached) return;
            calledNumbersListenerAttached = true;
            db.ref('room/calledNumbers').on('value', function(snapshot) {
                let serverList = snapshot.val() || [];
                while (calledNumbersList.length < serverList.length) {
                    let nextNum = serverList[calledNumbersList.length];
                    calledNumbersList.push(nextNum);
                    handleNumberCalled(nextNum);
                }
            });
        }

        function subscribePrizePool() {
            if (!db) return;
            db.ref('room/prizePool').on('value', function(snapshot) {
                let value = Number(snapshot.val() || 0);
                if (value > 0) {
                    currentGamePrize = value;
                    let el = document.getElementById('gamePrizeDisplay');
                    if (el) el.innerText = Math.floor(value);
                }
            });
        }

        function subscribeRoundEnd() {
            if (!db) return;
            if (roundEndListenerAttached) return;
            roundEndListenerAttached = true;
            db.ref('room/roundEnded').on('value', function(snapshot) {
                roomRoundEndedCached = (snapshot.val() === true);
                if (snapshot.val() === true && !winnerPopupShown) {
                    winnerPopupShown = true;
                    clearInterval(gameInterval);
                    db.ref('room/winnerCards').once('value').then(function(wSnap) {
                        let winnersObj = wSnap.val() || {};
                        let winnersArr = Object.keys(winnersObj).map(function(cardNumStr) {
                            return { cardNum: parseInt(cardNumStr), by: winnersObj[cardNumStr].by, name: winnersObj[cardNumStr].name };
                        });

                        let myWins = winnersArr.filter(function(w) { return w.by === telegramUserId; });
                        if (myWins.length > 0 && db && currentRoundId) {
                            let prizePool = Number(currentGamePrize || 0);
                            let prizePerWinner = winnersArr.length > 0 ? prizePool / winnersArr.length : 0;
                            let myPrize = prizePerWinner * myWins.length;
                            // Idempotent payout: the same user can never be credited twice for the same round.
                            db.ref('users/' + telegramUserId).transaction(function(current) {
                                current = current || { main: 0, play: 0, deposited: 0 };
                                current.bingoPayouts = current.bingoPayouts || {};
                                if (current.bingoPayouts[String(currentRoundId)]) return;
                                current.main = Number(current.main || 0) + myPrize;
                                current.bingoPayouts[String(currentRoundId)] = { amount: myPrize, winners: winnersArr.length, ts: firebase.database.ServerValue.TIMESTAMP };
                                return current;
                            }).then(function(result) {
                                if (result && result.committed) {
                                    mainWalletBalance += myPrize;
                                    updateWalletDisplay();
                                    addHistoryRecord('win', 'Bingo Game Winnings', myPrize);
                                }
                            }).catch(function(err) {
                                console.error('Prize payout failed:', err);
                            });
                        }

                        recordGameCompletion(winnersArr.length);
                        showWinnerPopup(winnersArr);
                    });
                }
            });
        }

        function acquireRoundCaller() {
            if (!db || callerLockListenerAttached) return;
            callerLockListenerAttached = true;
            db.ref('room/caller').transaction(function(current) {
                if (!current || !current.uid) {
                    return { uid: telegramUserId, name: userName, ts: firebase.database.ServerValue.TIMESTAMP };
                }
                return current;
            }).then(function(result) {
                let caller = result && result.snapshot ? result.snapshot.val() : null;
                isRoundCaller = !!(caller && caller.uid === telegramUserId);
                let callerLabel = document.getElementById('gameStatusText');
                if (callerLabel) callerLabel.innerText = isRoundCaller ? '🎱 Caller is active' : 'Watching Caller...';
                if (!isRoundCaller) return;

                // Only the elected caller establishes the shared prize pool.
                // Prize pool = 80% of all cards actually taken in this round (20% commission retained).
                return db.ref('room/takenCards').once('value').then(function(snap) {
                    let taken = snap.val() || {};
                    let cardCount = Object.keys(taken).length;
                    let stake = Number(selectedStake || 0);
                    let pool = cardCount * stake * 0.8;
                    return db.ref('room/prizePool').transaction(function(current) {
                        if (Number(current || 0) > 0) return current;
                        return pool;
                    });
                });
            }).catch(function(err) {
                console.error('Caller lock/prize pool failed:', err);
            });
        }

        function attemptCallNextNumber() {
            if (!db || roomRoundEndedCached || !isRoundCaller) return;
            db.ref('room/calledNumbers').transaction(function(current) {
                let list = current || [];
                if (list.length >= 75) return list;
                let next = Math.floor(Math.random() * 75) + 1;
                let attempts = 0;
                while (list.includes(next) && attempts < 200) {
                    next = Math.floor(Math.random() * 75) + 1;
                    attempts++;
                }
                if (list.includes(next)) return list;
                return list.concat([next]);
            }).catch(function(err) {
                console.log('attemptCallNextNumber failed:', err);
            });
        }

        function getWinningPattern(matrix, calledSet) {
            for (let r = 0; r < 5; r++) {
                let rowWin = true;
                for (let c = 0; c < 5; c++) {
                    let val = matrix[r][c];
                    if (val !== 'FREE' && !calledSet[val]) { rowWin = false; break; }
                }
                if (rowWin) {
                    let cells = [];
                    for (let c = 0; c < 5; c++) cells.push([r, c]);
                    return cells;
                }
            }

            for (let c = 0; c < 5; c++) {
                let colWin = true;
                for (let r = 0; r < 5; r++) {
                    let val = matrix[r][c];
                    if (val !== 'FREE' && !calledSet[val]) { colWin = false; break; }
                }
                if (colWin) {
                    let cells = [];
                    for (let r = 0; r < 5; r++) cells.push([r, c]);
                    return cells;
                }
            }

            let diag1Win = true;
            for (let i = 0; i < 5; i++) {
                let val = matrix[i][i];
                if (val !== 'FREE' && !calledSet[val]) { diag1Win = false; break; }
            }
            if (diag1Win) {
                let cells = [];
                for (let i = 0; i < 5; i++) cells.push([i, i]);
                return cells;
            }

            let diag2Win = true;
            for (let i = 0; i < 5; i++) {
                let val = matrix[i][4 - i];
                if (val !== 'FREE' && !calledSet[val]) { diag2Win = false; break; }
            }
            if (diag2Win) {
                let cells = [];
                for (let i = 0; i < 5; i++) cells.push([i, 4 - i]);
                return cells;
            }

            let corners = [[0,0],[0,4],[4,0],[4,4]];
            let cornersWin = corners.every(function(pos) {
                let val = matrix[pos[0]][pos[1]];
                return val === 'FREE' || calledSet[val];
            });
            if (cornersWin) return corners;

            return [];
        }

        function checkGlobalWinConditions() {
            let winners = [];
            let calledSet = {};
            calledNumbersList.forEach(function(n) { calledSet[n] = true; });

            // Combine Firebase-synced taken cards with the player's own locally-tracked
            // cards. takenCardsData can be empty (offline, or local-fallback calling mode),
            // and without this merge a win would never be detected in that case.
            let cardsToCheck = {};
            Object.keys(takenCardsData).forEach(function(cardNumStr) {
                cardsToCheck[cardNumStr] = takenCardsData[cardNumStr];
            });
            userBingoMatrices.forEach(function(cardObj) {
                let key = String(cardObj.id);
                if (!cardsToCheck[key]) {
                    cardsToCheck[key] = { by: telegramUserId, name: userName, matrix: cardObj.matrix };
                }
            });

            Object.keys(cardsToCheck).forEach(function(cardNumStr) {
                let entry = cardsToCheck[cardNumStr];
                if (!entry || !entry.matrix) return;
                let matrix = entry.matrix;
                let isWinner = false;

                for (let r = 0; r < 5; r++) {
                    let rowWin = true;
                    for (let c = 0; c < 5; c++) {
                        let val = matrix[r][c];
                        if (val !== 'FREE' && !calledSet[val]) { rowWin = false; break; }
                    }
                    if (rowWin) { isWinner = true; break; }
                }
                if (!isWinner) {
                    for (let c = 0; c < 5; c++) {
                        let colWin = true;
                        for (let r = 0; r < 5; r++) {
                            let val = matrix[r][c];
                            if (val !== 'FREE' && !calledSet[val]) { colWin = false; break; }
                        }
                        if (colWin) { isWinner = true; break; }
                    }
                }

                if (!isWinner) {
                    // Diagonal (top-left to bottom-right)
                    let diag1Win = true;
                    for (let i = 0; i < 5; i++) {
                        let val = matrix[i][i];
                        if (val !== 'FREE' && !calledSet[val]) { diag1Win = false; break; }
                    }
                    if (diag1Win) isWinner = true;
                }

                if (!isWinner) {
                    // Diagonal (top-right to bottom-left)
                    let diag2Win = true;
                    for (let i = 0; i < 5; i++) {
                        let val = matrix[i][4 - i];
                        if (val !== 'FREE' && !calledSet[val]) { diag2Win = false; break; }
                    }
                    if (diag2Win) isWinner = true;
                }

                if (!isWinner) {
                    // Four corners
                    let corners = [matrix[0][0], matrix[0][4], matrix[4][0], matrix[4][4]];
                    let cornersWin = corners.every(function(val) {
                        return val === 'FREE' || calledSet[val];
                    });
                    if (cornersWin) isWinner = true;
                }

                if (isWinner) {
                    let pattern = getWinningPattern(matrix, calledSet);
                    winners.push({ cardNum: parseInt(cardNumStr), by: entry.by, name: entry.name, pattern: pattern });
                }
            });

            return winners;
        }

        function finalizeRoundWinners(winners) {
            if (!db || !isRoundCaller || !winners || !winners.length) return;
            // Lock finalization first, then write the complete winner list, then publish roundEnded.
            db.ref('room/roundFinalizing').transaction(function(current) {
                if (current === true) return;
                return true;
            }).then(function(lockResult) {
                if (!lockResult || !lockResult.committed) return;
                let updates = {};
                winners.forEach(function(w) {
                    updates[w.cardNum] = { by: w.by, name: w.name, pattern: w.pattern || [] };
                });
                return db.ref('room/winnerCards').set(updates);
            }).then(function() {
                return db.ref('room/roundEnded').transaction(function(current) {
                    if (current === true) return;
                    return true;
                });
            }).catch(function(err) {
                console.log('finalizeRoundWinners failed:', err);
            });
        }

        function handleNumberCalled(num) {
            lastCallTime = Date.now();
            let calledBox = document.getElementById('currentCalledNum');
            let calledCountEl = document.getElementById('calledCountDisplay');
            let recentContainer = document.getElementById('recentCalledContainer');

            let letter = 'B';
            if (num >= 1 && num <= 15) letter = 'B';
            else if (num >= 16 && num <= 30) letter = 'I';
            else if (num >= 31 && num <= 45) letter = 'N';
            else if (num >= 46 && num <= 60) letter = 'G';
            else if (num >= 61 && num <= 75) letter = 'O';

            let letterColors = { B: '#3b82f6', I: '#8b5cf6', N: '#a855f7', G: '#10b981', O: '#f97316' };
            let letterColor = letterColors[letter];

            let displayCall = `${letter}-${num}`;

            if (calledBox) {
                calledBox.innerText = displayCall;
                calledBox.style.color = letterColor;
                calledBox.style.borderColor = '#f5b301';
                calledBox.style.boxShadow = `0 0 16px rgba(245, 179, 1, 0.55)`;
                calledBox.classList.remove('pop');
                void calledBox.offsetWidth; // restart animation even if same number pattern repeats
                calledBox.classList.add('pop');
            }
            if (calledCountEl) calledCountEl.innerText = calledNumbersList.length;

            if (recentContainer) {
                let newTag = `<div class="recent-call-badge" style="background: ${letterColor};">${displayCall}</div>`;
                recentContainer.insertAdjacentHTML('afterbegin', newTag);
            }

            speakNumber(displayCall);
            markBoardAndCards(num);

            if (isRoundCaller && !roomRoundEndedCached) {
                let winners = checkGlobalWinConditions();
                if (winners.length > 0) finalizeRoundWinners(winners);
            }
        }
        // --- end shared calling / win detection ---

        let gameInterval = null;
        let calledNumbersList = [];
        let lastCallTime = 0;
        let userBingoMatrices = [];
        
        let mainWalletBalance = 0; // winnings land here automatically; withdraw from here
        let playWalletBalance = 0; // starts at 0; gets 10 when player registers
        let depositedBalance = 0; // tracks how much of playWalletBalance came from REAL Telebirr deposits (vs free bonus coins) — only this fraction of any winnings becomes withdrawable
        let currentRoundDepositedFraction = 0; // what fraction of this round's stake was funded by real deposits (0 = pure bonus, 1 = pure deposited money)
        let hasUsedFreeGame = false; // once true, playing again requires a real Telebirr deposit — bonus coins alone are no longer enough
        let gameHistoryList = [];
        
        let isRegistered = false;
        let currentGamePrize = 0;

        const storageKey = "habesha_bingo_reg_" + telegramUserId;
        if (localStorage.getItem(storageKey) === "true") {
            isRegistered = true;
            let statusEl = document.getElementById('userStatusDisplay');
            if (statusEl) {
                statusEl.innerText = "Registered 📝";
                statusEl.style.color = "var(--success-color)";
            }
        }

        let isApplyingRemoteWalletUpdate = false; // true while syncing FROM Firebase, so updateWalletDisplay() doesn't echo stale local values back and clobber a change made elsewhere (e.g. an admin deposit approval from the bot)

        function updateWalletDisplay() {
            let mainEl = document.getElementById('mainWalletBalanceDisplay');
            if (mainEl) mainEl.innerText = Math.floor(mainWalletBalance) + " coins";

            let playEl = document.getElementById('playWalletBalanceDisplay');
            if (playEl) playEl.innerText = Math.floor(playWalletBalance) + " coins";

            let selMainEl = document.getElementById('selMainWallet');
            if (selMainEl) selMainEl.innerText = Math.floor(mainWalletBalance);

            let selPlayEl = document.getElementById('selPlayWallet');
            if (selPlayEl) selPlayEl.innerText = Math.floor(playWalletBalance);

            let selStakeEl = document.getElementById('selStakeDisplay');
            if (selStakeEl) selStakeEl.innerText = selectedStake;

            // Only push to Firebase when the change originated locally (a game
            // result, a deposit/withdraw in this session, etc). If we're here
            // because the live listener just synced in a change from elsewhere
            // (e.g. the bot approving a deposit), writing back would overwrite
            // that change with the stale values this tab already had in memory.
            if (db && !isApplyingRemoteWalletUpdate) {
                db.ref('users/' + telegramUserId + '/wallet').set({
                    main: mainWalletBalance,
                    play: playWalletBalance,
                    deposited: depositedBalance
                }).catch(function(err) {
                    console.log('Wallet save failed', err);
                });
            }
        }

        function addHistoryRecord(type, desc, amount) {
            let timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            gameHistoryList.unshift({ type, desc, amount, timeStr });
        }

        function handleInvite() {
            let shareUrl = `https://t.me/share/url?url=https://t.me/Temerachibingo_bot?start=ref${userShortId}&text=Join%20Temerachi%20Bingo`;
            if (tg && tg.openTelegramLink) {
                tg.openTelegramLink(shareUrl);
            } else {
                navigator.clipboard.writeText(`https://t.me/Temerachibingo_bot?start=ref${userShortId}`);
                alert("🔗 Invite link copied to clipboard! Share it with your friends.");
            }
        }

        function handleSupport() {
            let supportUrl = 'https://t.me/Temerachibingosupport';
            if (tg && tg.openTelegramLink) {
                tg.openTelegramLink(supportUrl);
            } else {
                window.open(supportUrl, '_blank');
            }
        }

        function showInstructions() {
            let modalBox = document.getElementById('customModal');
            let modalBody = document.getElementById('modalBodyText');
            modalBody.innerHTML = `
                <div style="font-size: 30px; margin-bottom: 4px;">📖</div>
                <div style="font-size: 19px; font-weight: bold; color: var(--orange-color); margin-bottom: 12px;">Instructions</div>
                <div style="text-align: left; font-size: 14px; line-height: 1.7; color: #e2e8f0; white-space: pre-line;">🃏 መጫወቻ ካርድ

1. ጨዋታውን ለመጀመር ከሚመጣልን ከ1-600 የካርድ መምረጫ ቦርድ ውስጥ እስከ 2 የመጫወቻ ካርድ (ካርቴላ) መምረጥ ይቻላል።

2. የካርድ መምረጫ ቦርድ ላይ በቀይ ቀለም የተመረጡ ቁጥሮች የሚያሳዩት መጫወቻ ካርዱ (ካርቴላው) በሌላ ተጫዋች መመረጡን ነው።

3. የመጫወቻ ካርዱን (ካርቴላውን) ሲመርጡት ከታች የሚይዛቸውን ቁጥሮች ያሳያል።

4. ወደ ጨዋታው ለመግባት የሚፈልጉትን የመጫወቻ ካርድ (ካርቴላ) ሲመርጡና ለምዝገባ የተሰጠው ሰኮንድ ዜሮ ሲሆን ቀጥታ ወደ ጨዋታ ያስገባል።

🎮 ጨዋታ እንዴት ይካሄዳል

1. ወደ ጨዋታው ከገቡ በኋላ በመረጡት የመጫወቻ ካርድ (ካርቴላ) ከታች በቀኝ በኩል ያገኙታል።

2. ጨዋታው ሲጀምር ሲስተሙ ከ1 እስከ 75 ያሉ ቁጥሮችን Randomly መጥራት ይጀምራል።

3. ሲስተሙ ከሚጠራቸው ቁጥሮች ውስጥ በራስዎ የመጫወቻ ካርድ (ካርቴላ) ላይ ካሉ በመምረጥ ያጥቁሩ። በራሱ እንዲያጠቁር ከፈለጉ Automatic የሚለውን ያብሩት።

🏆 አሸናፊ የሚሆኑባቸው መንገዶች

1. መጫወቻ ካርድ (ካርቴላ) ላይ የተጠቆሩት ቁጥሮች፦
   • ወደጎን ወይም ወደታች መስመር ከሰሩ
   • ወደሁለቱም አግዳሚ መስመር ከሰሩ
   • አራቱ ማእዘናት (ኮርነር) ከተጠሩ አሸናፊ ይሆናሉ።

2. ሁለት ወይም ከዚያ በላይ ተጫዋቾች እኩል ቢያሸንፉ አጠቃላይ ደራሹ ብር ለአሸናፊዎች እኩል ይካፈላል።</div>
                <button class="btn btn-orange" style="margin-top: 16px;" onclick="document.getElementById('customModal').style.display = 'none';">Close</button>
            `;
            modalBox.style.display = 'flex';
        }

        // --- Admin panel: approve/reject pending deposit & withdrawal requests ---
        // Hardcoded admin Telegram IDs — add/remove IDs here, no need to touch Firebase.
        const HARDCODED_ADMIN_IDS = ["7078415767"];

        let pendingBadgeListenersAttached = false;
        let pendingDepositCount = 0;
        let pendingWithdrawalCount = 0;

        function updatePendingBadge() {
            let badge = document.getElementById('adminPendingBadge');
            if (!badge) return;
            let total = pendingDepositCount + pendingWithdrawalCount;
            if (total > 0) {
                badge.innerText = total;
                badge.style.display = 'inline-block';
            } else {
                badge.style.display = 'none';
            }
        }

        function watchPendingRequestsForAdmin() {
            if (!HARDCODED_ADMIN_IDS.includes(String(telegramUserId))) return;

            let linkContainer = document.getElementById('adminLinkContainer');
            if (linkContainer) linkContainer.style.display = 'block';

            if (!db || pendingBadgeListenersAttached) return;
            pendingBadgeListenersAttached = true;

            db.ref('transactions/deposits').on('value', function(snapshot) {
                let all = snapshot.val() || {};
                pendingDepositCount = Object.keys(all).filter(k => all[k].status === 'pending').length;
                updatePendingBadge();
            });

            db.ref('transactions/withdrawals').on('value', function(snapshot) {
                let all = snapshot.val() || {};
                pendingWithdrawalCount = Object.keys(all).filter(k => all[k].status === 'pending').length;
                updatePendingBadge();
            });
        }

        let adminUnlocked = false;
        let adminListenersAttached = false;

        function openAdminPanel() {
            if (adminUnlocked) {
                switchScreen('adminScreen');
                subscribeAdminRequests();
                return;
            }

            // 1) Check the hardcoded list first (works even if Firebase 'admins' node doesn't exist)
            if (HARDCODED_ADMIN_IDS.includes(String(telegramUserId))) {
                adminUnlocked = true;
                switchScreen('adminScreen');
                subscribeAdminRequests();
                return;
            }

            // 2) Fallback: check Firebase 'admins/<id>' node, in case it's set up there instead
            if (!db) {
                alert("❌ You are not authorized to access the admin panel.");
                return;
            }
            db.ref('admins/' + telegramUserId).once('value').then(function(snap) {
                if (snap.val() === true) {
                    adminUnlocked = true;
                    switchScreen('adminScreen');
                    subscribeAdminRequests();
                } else {
                    alert("❌ You are not authorized to access the admin panel.");
                }
            }).catch(function(err) {
                console.log('Admin check failed', err);
                alert("❌ You are not authorized to access the admin panel.");
            });
        }

        function subscribeAdminRequests() {
            if (!db || adminListenersAttached) return;
            adminListenersAttached = true;

            db.ref('transactions/deposits').on('value', function(snapshot) {
                let all = snapshot.val() || {};
                let listEl = document.getElementById('adminDepositsList');
                if (!listEl) return;
                let pendingKeys = Object.keys(all).filter(k => all[k].status === 'pending');
                if (pendingKeys.length === 0) {
                    listEl.innerHTML = 'No pending deposits.';
                    return;
                }
                listEl.innerHTML = pendingKeys.map(function(key) {
                    let r = all[key];
                    let smsHtml = r.smsText ? `<div style="font-size:11px; color:#cbd5e1; background:#0f172a; border-radius:6px; padding:6px; margin-top:6px; white-space:pre-wrap; word-break:break-word;">${r.smsText}</div>` : '';
                    return `
                    <div style="background:#1c2640; border:1px solid #2e3b55; border-radius:8px; padding:8px; margin-bottom:8px;">
                        <div><b>${r.name}</b> — ${r.amount} coins</div>
                        <div style="font-size:11px; color:#64748b;">Txn: ${key} · Phone: ${r.phone || '-'}</div>
                        ${smsHtml}
                        <div style="display:flex; gap:6px; margin-top:6px;">
                            <button class="btn btn-green" style="padding:6px;" onclick="adminApproveDeposit('${key}')">Approve</button>
                            <button class="btn btn-danger" style="padding:6px;" onclick="adminRejectDeposit('${key}')">Reject</button>
                        </div>
                    </div>`;
                }).join('');
            });

            db.ref('transactions/withdrawals').on('value', function(snapshot) {
                let all = snapshot.val() || {};
                let listEl = document.getElementById('adminWithdrawalsList');
                if (!listEl) return;
                let pendingKeys = Object.keys(all).filter(k => all[k].status === 'pending');
                if (pendingKeys.length === 0) {
                    listEl.innerHTML = 'No pending withdrawals.';
                    return;
                }
                listEl.innerHTML = pendingKeys.map(function(key) {
                    let r = all[key];
                    return `
                    <div style="background:#1c2640; border:1px solid #2e3b55; border-radius:8px; padding:8px; margin-bottom:8px;">
                        <div><b>${r.name}</b> — ${r.amount} coins</div>
                        <div style="font-size:11px; color:#64748b;">Telegram: ${r.telegramName || '-'} · Send to: ${r.phone || '-'}</div>
                        <div style="display:flex; gap:6px; margin-top:6px;">
                            <button class="btn btn-green" style="padding:6px;" onclick="adminApproveWithdrawal('${key}')">Approve (Sent)</button>
                            <button class="btn btn-danger" style="padding:6px;" onclick="adminRejectWithdrawal('${key}')">Reject</button>
                        </div>
                    </div>`;
                }).join('');
            });
        }

        function adminApproveDeposit(key) {
            if (!db) return;
            db.ref('transactions/deposits/' + key).once('value').then(function(snap) {
                let record = snap.val();
                if (!record || record.status === 'approved') return; // avoid double-crediting
                let userId = record.by;
                let amount = Number(record.amount) || 0;

                db.ref('transactions/deposits/' + key + '/status').set('approved');

                // Credit the user's wallet directly on the server so it works
                // even if the depositor already closed the app.
                db.ref('users/' + userId + '/wallet/play').transaction(function(current) {
                    return (current || 0) + amount;
                });
                db.ref('users/' + userId + '/wallet/deposited').transaction(function(current) {
                    return (current || 0) + amount;
                });
            });
        }

        function adminRejectDeposit(key) {
            if (!db) return;
            db.ref('transactions/deposits/' + key + '/status').set('rejected');
        }

        function adminApproveWithdrawal(key) {
            if (!db) return;
            db.ref('transactions/withdrawals/' + key + '/status').set('approved');
        }

        function adminRejectWithdrawal(key) {
            if (!db) return;
            db.ref('transactions/withdrawals/' + key).once('value').then(function(snap) {
                let record = snap.val();
                if (!record || record.status !== 'pending') return; // already handled
                let userId = record.by;
                let amount = Number(record.amount) || 0;

                db.ref('transactions/withdrawals/' + key + '/status').set('rejected');

                // Refund the amount back to the user's main wallet, since it
                // was deducted immediately when they submitted the request.
                db.ref('users/' + userId + '/wallet/main').transaction(function(current) {
                    return (current || 0) + amount;
                });
            });
        }

        function showInsuffientBalanceModal(message) {
            let modalBox = document.getElementById('customModal');
            let modalBody = document.getElementById('modalBodyText');
            
            modalBody.innerHTML = `
                <div style="text-align: center; color: var(--danger-color); font-size: 28px; margin-bottom: 12px;">⚠️</div>
                <div style="font-size: 16px; font-weight: bold; margin-bottom: 12px; color: var(--text-color);">${message}</div>
                <div style="display: flex; gap: 10px; flex-direction: column;">
                    <button class="btn btn-green" onclick="handleDeposit(); document.getElementById('customModal').style.display = 'none';">💰 Deposit Now</button>
                    <button class="btn btn-danger" onclick="document.getElementById('customModal').style.display = 'none';">Close</button>
                </div>
            `;
            
            modalBox.style.display = 'flex';
        }

        

        const gridContainer = document.getElementById('numberGrid');
        if (gridContainer) {
            for (let i = 1; i <= 600; i++) {
                let cell = document.createElement('div');
                cell.className = 'num-cell';
                cell.innerText = i;
                cell.id = `grid_cell_${i}`;
                cell.onclick = (function(cellNum, cellElement) {
                    return function() {
                        if (cellElement.classList.contains('taken')) {
                            showToast('ይህ ካርድ ቀድሞ በሌላ ተጫዋች ተይዟል!');
                            return;
                        }
                        if (cellElement.classList.contains('pending')) {
                            return; // a claim for this cell is already in flight
                        }

                        let index = selectedCards.indexOf(cellNum);

                        if (index === -1) {
                            if (selectedCards.length >= 2) {
                                alert('You cannot select more than 2 cards!');
                                return;
                            }

                            let nextCost = (selectedCards.length + 1) * selectedStake;

                            if ((playWalletBalance + mainWalletBalance) < nextCost) {
                                showToast(`Insufficient wallet balance.`, 3000);
                                return;
                            }

                            // Reserve the slot immediately (synchronously) so rapid taps
                            // can never push more than 2 cards while the Firebase claim
                            // for an earlier tap is still in flight.
                            selectedCards.push(cellNum);
                            cellElement.classList.add('selected');
                            cellElement.classList.add('pending');
                            updateSelectedCardsPreview();

                            claimCardInFirebase(cellNum, function() {
                                cellElement.classList.remove('pending');
                                updateSelectedCardsPreview();
                            }, function() {
                                // Someone else actually holds this card — roll back the reservation
                                let idx = selectedCards.indexOf(cellNum);
                                if (idx !== -1) selectedCards.splice(idx, 1);
                                cellElement.classList.remove('selected');
                                cellElement.classList.remove('pending');
                                cellElement.classList.add('taken');
                                showToast('ይህ ካርድ ልክ አሁን በሌላ ተጫዋች ተይዞ ነበር!');
                                updateSelectedCardsPreview();
                            });
                        } else {
                            selectedCards.splice(index, 1);
                            cellElement.classList.remove('selected');
                            cellElement.classList.remove('pending');
                            releaseCardInFirebase(cellNum);
                            updateSelectedCardsPreview();
                        }
                    };
                })(i, cell);
                gridContainer.appendChild(cell);
            }
        }

        function updateSelectedCardsPreview() {
            let container = document.getElementById('selectedCardsPreviewContainer');
            if (!container) return;
            
            if (selectedCards.length === 0) {
                container.innerHTML = `<div style="grid-column: 1 / -1; font-size: 13px; color: #64748b; text-align: center; width: 100%; padding: 4px;">ካርቴላ ለመምረጥ ከላይ ያሉትን ቁጥሮች ይጫኑ (ከፍተኛ 2)</div>`;
                return;
            }

            let html = '';
            selectedCards.forEach(cardNum => {
                let matrix = generateBingoMatrix();
                
                html += `
                <div class="bingo-card-container">
                    <div style="font-size:10px; margin-bottom:2px; color:var(--orange-color); font-weight: bold; text-align: center;">Cartela No : ${cardNum}</div>
                    <div class="bingo-grid">
                        <div class="bingo-header-cell">B</div><div class="bingo-header-cell">I</div><div class="bingo-header-cell">N</div><div class="bingo-header-cell">G</div><div class="bingo-header-cell">O</div>`;

                for(let r=0; r<5; r++) {
                    for(let c=0; c<5; c++) {
                        let val = matrix[r][c];
                        let isFree = (val === 'FREE');
                        let cellClass = isFree ? 'bingo-cell free' : 'bingo-cell';
                        if(isFree) val = '✨';
                        html += `<div class="${cellClass}">${val}</div>`;
                    }
                }
                html += `</div></div>`;
            });
            container.innerHTML = html;
        }

        function switchScreen(screenId) {
            let screens = document.querySelectorAll('.screen');
            screens.forEach(screen => screen.classList.remove('active'));
            let targetScreen = document.getElementById(screenId);
            if (targetScreen) targetScreen.classList.add('active');
        }

        function switchNav(screenId, navId) {
            clearInterval(selectionInterval);
            clearInterval(gameInterval);
            switchScreen(screenId);
            
            let navItems = document.querySelectorAll('.nav-item');
            navItems.forEach(item => item.classList.remove('active'));
            
            let activeNav = document.getElementById(navId);
            if (activeNav) activeNav.classList.add('active');
        }

        function handleRegister() {
            if (isRegistered || localStorage.getItem(storageKey) === "true") {
                alert("⚠️ You are already registered! You cannot claim the bonus again.");
                return;
            }

            isRegistered = true;
            localStorage.setItem(storageKey, "true");
            if (db) {
                db.ref('users/' + telegramUserId + '/registered').set(true).catch(function(err) {
                    console.log('Registration save failed', err);
                });
            }
            
            playWalletBalance += 10;
            updateWalletDisplay();
            addHistoryRecord('bonus', 'Registration Bonus', 10);

            let statusEl = document.getElementById('userStatusDisplay');
            if (statusEl) {
                statusEl.innerText = "Registered 📝";
                statusEl.style.color = "var(--success-color)";
            }

            alert("🎉 Welcome! 10 free fun coins have been added to your balance.");
        }

        function chooseStake(stake) {
            selectedStake = stake;
            openSelection();
        }

        function openSelection() {
            unlockAudio();
            clearInterval(gameInterval);
            selectedCards = [];
            
            let cells = document.querySelectorAll('.num-cell');
            cells.forEach(cell => cell.classList.remove('selected'));
            
            updateSelectedCardsPreview();
            updateWalletDisplay();
            switchScreen('selectScreen');
            startSelectionCountdown();
            joinOrResetRound();
        }

        function startSelectionCountdown() {
            clearInterval(selectionInterval);
            let timeLeft = 50;
            let timerEl = document.getElementById('selectionTimer');
            if (timerEl) timerEl.innerText = timeLeft + 's';

            selectionInterval = setInterval(function() {
                timeLeft--;
                if (timerEl) timerEl.innerText = timeLeft + 's';

                if (timeLeft <= 0) {
                    clearInterval(selectionInterval);
                    if (selectedCards.length === 0) {
                        let randomCard = pickRandomAvailableCard();
                        selectedCards.push(randomCard);
                        claimCardInFirebase(randomCard, function() {}, function() {});
                    }
                    processGameEntry();
                }
            }, 1000);
        }

        function pickRandomAvailableCard() {
            let candidate = Math.floor(Math.random() * 600) + 1;
            let attempts = 0;
            while (takenCardsData[candidate] && takenCardsData[candidate].by !== telegramUserId && attempts < 50) {
                candidate = Math.floor(Math.random() * 600) + 1;
                attempts++;
            }
            return candidate;
        }

        function processGameEntry() {
            // Only ONE free (non-deposit) game is allowed per user. After that, playing again requires real money in the wallet.
            if (depositedBalance <= 0 && hasUsedFreeGame) {
                alert('🔒 You have already played your one free game. Please deposit to keep playing.');
                switchNav('walletScreen', 'navWallet');
                return;
            }

            if (selectedCards.length === 0) {
                let randomCard = pickRandomAvailableCard();
                selectedCards.push(randomCard);
                claimCardInFirebase(randomCard, function() {}, function() {});
            }

            let totalDeduction = selectedCards.length * selectedStake;

            if ((playWalletBalance + mainWalletBalance) < totalDeduction) {
                showInsuffientBalanceModal(`❌ Not enough coins! You need ${totalDeduction} coins for the selected ${selectedCards.length} card(s).`);
                return;
            }

            if (depositedBalance <= 0 && !hasUsedFreeGame) {
                hasUsedFreeGame = true;
                if (db) {
                    db.ref('users/' + telegramUserId + '/hasUsedFreeGame').set(true).catch(function(err) {
                        console.log('Free game flag save failed', err);
                    });
                }
            }

            // Play Wallet is used first; any shortfall is covered by Main Wallet.
            // Main Wallet money is already real/withdrawable, so that portion
            // counts as 100% "real" toward this round's withdrawable fraction.
            let playPortion = Math.min(playWalletBalance, totalDeduction);
            let mainPortion = totalDeduction - playPortion;

            // Track what fraction of THIS stake is real (deposited) money vs free bonus coins —
            // only the real fraction of any winnings will be withdrawable.
            let playDepositedFraction = playWalletBalance > 0 ? Math.min(1, depositedBalance / playWalletBalance) : 0;
            let realFromPlay = playPortion * playDepositedFraction;
            let totalReal = realFromPlay + mainPortion;
            currentRoundDepositedFraction = totalDeduction > 0 ? totalReal / totalDeduction : 0;
            depositedBalance = Math.max(0, depositedBalance - realFromPlay);

            playWalletBalance -= playPortion;
            mainWalletBalance -= mainPortion;
            updateWalletDisplay();
            addHistoryRecord('game', `Game Entry (${selectedCards.length} Cards)`, -totalDeduction);

            // Derash = (total cards taken this round × card price) × 0.8 (20% platform commission held back)
            const CARD_PRICE = selectedStake;
            let totalCardsTakenThisRound = selectedCards.length;
            if (db) {
                totalCardsTakenThisRound = Object.keys(takenCardsData).length || selectedCards.length;
            }
            currentGamePrize = totalCardsTakenThisRound * CARD_PRICE * 0.8;

            let gamePrizeDisplay = document.getElementById('gamePrizeDisplay');
            if (gamePrizeDisplay) gamePrizeDisplay.innerText = Math.floor(currentGamePrize);

            let randomGameId = 'BBX' + Math.random().toString(36).substring(2, 6).toUpperCase();
            let gameIdEl = document.getElementById('gameIdDisplay');
            if (gameIdEl) gameIdEl.innerText = randomGameId;

            let activePlayersCountDisplay = document.getElementById('activePlayersCountDisplay');
            if (activePlayersCountDisplay) {
                activePlayersCountDisplay.innerText = selectedCards.length;
            }

            switchScreen('gameScreen');
            initializeGameBoard();
            initializeUserCards();
            startBingoGame();
            requestAnimationFrame(function() {
                requestAnimationFrame(syncBoardHeight);
            });
        }

        function syncBoardHeight() {
            let rightCol = document.getElementById('rightColumnWrapper');
            let masterCard = document.getElementById('masterBoardCard');
            let headerRow = document.getElementById('masterBoardHeader');
            let grid = document.getElementById('gameBoardGrid');
            if (!rightCol || !masterCard || !headerRow || !grid) return;

            let targetHeight = rightCol.offsetHeight;
            if (!targetHeight) return;

            let cardPadding = 10; // ~4px top+4px bottom padding + 1px border top/bottom on masterCard
            let headerHeight = headerRow.offsetHeight;
            let headerMarginBottom = 3;
            let rowGap = 2;
            let numRows = 15;
            let totalGaps = (numRows - 1) * rowGap;

            let availableForRows = targetHeight - cardPadding - headerHeight - headerMarginBottom - totalGaps;
            let cellHeight = availableForRows / numRows;
            cellHeight = Math.max(14, Math.min(cellHeight, 40));

            let fontSize = Math.max(9, Math.min(cellHeight * 0.48, 15));

            let cells = grid.children;
            for (let i = 0; i < cells.length; i++) {
                cells[i].style.height = cellHeight + 'px';
                cells[i].style.fontSize = fontSize + 'px';
            }
        }

        function goBackToSelection() {
            clearInterval(gameInterval);
            openSelection();
        }

        // Fun mode UI demo: Telebirr-only manual deposit with rotating numbers + Firebase-backed anti-duplicate transaction ID check
        let depositSelectedAmount = 50;
        let depositSelectedNumber = null;

        const telebirrNumbers = [
            { phone: "0923160399", name: "Fikre" },
            { phone: "0900619106", name: "Fikr" },
            { phone: "0921466712", name: "asebechimariyam" }
        ];

        function closeCustomModal() {
            let modalBox = document.getElementById('customModal');
            if (modalBox) modalBox.style.display = 'none';
        }

        function handleDeposit() {
            renderDepositAmountStep();
        }

        function renderDepositAmountStep() {
            let modalBox = document.getElementById('customModal');
            let modalBody = document.getElementById('modalBodyText');

            modalBody.innerHTML = `
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 12px;">
                    <div style="font-size: 17px; font-weight: bold; color: var(--orange-color);">🪙 Deposit to Play Wallet</div>
                    <div onclick="closeCustomModal()" style="cursor:pointer; font-size: 18px; color: #64748b;">✕</div>
                </div>
                <div style="font-size: 13px; color: #94a3b8; margin-bottom: 12px; text-align: left;">Choose an amount (fun coins — no real money):</div>
                <div style="display: grid; grid-template-columns: repeat(5, 1fr); gap: 6px; margin-bottom: 10px;">
                    <div class="deposit-amount-btn active" id="depAmt10" onclick="selectDepositAmount(10)">10</div>
                    <div class="deposit-amount-btn" id="depAmt50" onclick="selectDepositAmount(50)">50</div>
                    <div class="deposit-amount-btn" id="depAmt100" onclick="selectDepositAmount(100)">100</div>
                    <div class="deposit-amount-btn" id="depAmt200" onclick="selectDepositAmount(200)">200</div>
                    <div class="deposit-amount-btn" id="depAmt500" onclick="selectDepositAmount(500)">500</div>
                </div>
                <div style="text-align:left; margin-bottom:6px; font-size:12px; color:#94a3b8;">ወይም የፈለከውን መጠን አስገባ (ዝቅተኛ 10)</div>
                <input type="number" id="depositCustomAmount" min="10" max="10000" step="1" placeholder="ለምሳሌ 30" style="width:100%; box-sizing:border-box; padding:10px; border-radius:8px; border:1px solid #2e3b55; background:#1c2640; color:white; font-size:14px; margin-bottom:6px;" oninput="selectCustomDepositAmount(this.value)">
                <div id="depositAmountErrorMsg" style="color:var(--danger-color); font-size:12px; margin-bottom:8px; display:none;">ዝቅተኛ የማስገቢያ መጠን 10 ኮይን ነው።</div>
                <button class="btn btn-green" onclick="confirmDepositAmountAndContinue()">Continue ➜</button>
            `;
            depositSelectedAmount = 10;
            modalBox.style.display = 'flex';
        }

        function selectDepositAmount(amount) {
            depositSelectedAmount = amount;
            document.querySelectorAll('.deposit-amount-btn').forEach(b => b.classList.remove('active'));
            let btn = document.getElementById('depAmt' + amount);
            if (btn) btn.classList.add('active');
            let customInput = document.getElementById('depositCustomAmount');
            if (customInput) customInput.value = '';
            let errorEl = document.getElementById('depositAmountErrorMsg');
            if (errorEl) errorEl.style.display = 'none';
        }

        function selectCustomDepositAmount(value) {
            document.querySelectorAll('.deposit-amount-btn').forEach(b => b.classList.remove('active'));
            let amount = parseInt(value, 10);
            depositSelectedAmount = (!isNaN(amount) && amount > 0) ? amount : 0;
        }

        function confirmDepositAmountAndContinue() {
            let errorEl = document.getElementById('depositAmountErrorMsg');
            if (!depositSelectedAmount || depositSelectedAmount < 10) {
                if (errorEl) {
                    errorEl.innerText = 'ዝቅተኛ የማስገቢያ መጠን 10 ኮይን ነው።';
                    errorEl.style.display = 'block';
                }
                return;
            }
            if (depositSelectedAmount > 10000) {
                if (errorEl) {
                    errorEl.innerText = 'ከፍተኛ የማስገቢያ መጠን 10,000 ኮይን ነው። ከዚህ በላይ ከፈለጉ Support ያግኙ።';
                    errorEl.style.display = 'block';
                }
                return;
            }
            if (errorEl) errorEl.style.display = 'none';
            renderDepositTelebirrStep();
        }

        function getNextTelebirrNumber(callback) {
            if (!db) {
                callback(telebirrNumbers[Math.floor(Math.random() * telebirrNumbers.length)]);
                return;
            }
            db.ref('deposits/rotationIndex').transaction(function(current) {
                return (typeof current === 'number') ? current + 1 : 0;
            }).then(function(result) {
                let idx = result.committed ? result.snapshot.val() : 0;
                callback(telebirrNumbers[idx % telebirrNumbers.length]);
            }).catch(function() {
                callback(telebirrNumbers[Math.floor(Math.random() * telebirrNumbers.length)]);
            });
        }

        function renderDepositTelebirrStep() {
            let modalBody = document.getElementById('modalBodyText');
            modalBody.innerHTML = `
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 12px;">
                    <div style="font-size: 17px; font-weight: bold; color: var(--orange-color);">📱 Pay with Telebirr</div>
                    <div onclick="closeCustomModal()" style="cursor:pointer; font-size: 18px; color: #64748b;">✕</div>
                </div>
                <div class="deposit-spinner" style="width:28px; height:28px; border-width:3px;"></div>
            `;

            getNextTelebirrNumber(function(numberObj) {
                depositSelectedNumber = numberObj;
                modalBody.innerHTML = `
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 12px;">
                        <div style="font-size: 17px; font-weight: bold; color: var(--orange-color);">📱 Pay with Telebirr</div>
                        <div onclick="closeCustomModal()" style="cursor:pointer; font-size: 18px; color: #64748b;">✕</div>
                    </div>
                    <div style="font-size: 13px; color: #94a3b8; margin-bottom: 10px; text-align: left;">Depositing <b style="color: var(--success-color);">${depositSelectedAmount}</b></div>
                    <div style="background:#1c2640; border:1px solid #2e3b55; border-radius:10px; padding:14px; margin-bottom:14px;">
                        <div style="font-size:12px; color:#94a3b8; margin-bottom:4px;">ወደዚህ ቁጥር Telebirr ይላኩ</div>
                        <div style="font-size:22px; font-weight:bold; color:var(--orange-color); margin-bottom:2px;">${numberObj.phone}</div>
                        <div style="font-size:13px; color:#cbd5e1;">${numberObj.name}</div>
                    </div>
                    <button class="btn btn-green" onclick="renderDepositProofStep()">ላክኩ - ቀጥል ➜</button>
                    <button class="btn" style="margin-top:6px;" onclick="renderDepositAmountStep()">⬅ Back</button>
                `;
            });
        }

        function pasteTelebirrSms() {
            if (!navigator.clipboard || !navigator.clipboard.readText) {
                showToast('📋 የዚህ ብራውዘር ገደብ Paste አይፈቅድም - በእጅ ይለጥፉ (long-press → Paste)።');
                return;
            }
            navigator.clipboard.readText().then(function(text) {
                if (!text) {
                    showToast('📋 ክሊፕቦርድ ላይ ምንም ጽሑፍ አልተገኘም።');
                    return;
                }
                let inputEl = document.getElementById('depositSmsText');
                if (inputEl) inputEl.value = text.trim();
            }).catch(function(err) {
                console.log('Clipboard read failed', err);
                showToast('📋 ከክሊፕቦርድ ማንበብ አልተቻለም - በእጅ ይለጥፉ (long-press → Paste)።');
            });
        }

        function extractTxnIdFromSms(text) {
            let labelMatch = text.match(/(?:transaction\s*id|txn\s*id|reference\s*(?:no|number)?|ref\s*no)[\s:.\-]*([A-Za-z0-9]{6,})/i);
            if (labelMatch) return labelMatch[1];
            let tokens = text.split(/\s+/);
            let candidates = tokens.filter(function(t) {
                return /^[A-Za-z0-9]{8,}$/.test(t) && /[0-9]/.test(t) && /[A-Za-z]/.test(t);
            });
            if (candidates.length > 0) return candidates[candidates.length - 1];
            return null;
        }

        function validateTelebirrSms(text, amount) {
            if (!text || text.trim().length < 25) {
                return 'ኤስኤምኤስ በጣም አጭር ነው። ሙሉ የቴሌብር ማረጋገጫ መልዕክት ይለጥፉ።';
            }
            if (!/telebirr|ቴሌብር|confirmed|receipt|successful/i.test(text)) {
                return '⚠️ ይሄ የቴሌብር ማረጋገጫ መልዕክት አይመስልም። ትክክለኛውን SMS ይለጥፉ።';
            }
            let txnId = extractTxnIdFromSms(text);
            if (!txnId) {
                return 'የትራንዛክሽን ID በኤስኤምኤስ ውስጥ ማግኘት አልተቻለም። ሙሉውን SMS ኮፒ አድርገው ለጥፉ።';
            }
            if (amount && text.indexOf(String(amount)) === -1) {
                return `⚠️ የገባው መጠን (${amount}) በኤስኤምኤስ ውስጥ አልተገኘም። ትክክለኛውን SMS ለጥፉ።`;
            }
            return null;
        }

        function renderDepositProofStep() {
            let modalBody = document.getElementById('modalBodyText');
            modalBody.innerHTML = `
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 12px;">
                    <div style="font-size: 17px; font-weight: bold; color: var(--orange-color);">🧾 Confirm Payment</div>
                    <div onclick="closeCustomModal()" style="cursor:pointer; font-size: 18px; color: #64748b;">✕</div>
                </div>
                <div style="text-align:left; margin-bottom:6px; font-size:13px; color:#94a3b8;">ሙሉ የቴሌብር ማረጋገጫ SMS ኮፒ አድርገው ይለጥፉ</div>
                <textarea id="depositSmsText" rows="4" placeholder="Dear ..., you have transferred ETB ... Transaction ID: ..." style="width:100%; box-sizing:border-box; padding:10px; border-radius:8px; border:1px solid #2e3b55; background:#1c2640; color:white; font-size:13px; margin-bottom:6px; resize:vertical;"></textarea>
                <button type="button" onclick="pasteTelebirrSms()" style="width:100%; background:#1c2640; border:1px solid #2e3b55; color:var(--orange-color); border-radius:8px; padding:8px; font-size:12px; font-weight:bold; cursor:pointer; margin-bottom:10px;">📋 Paste from Clipboard</button>
                <div id="depositErrorMsg" style="color:var(--danger-color); font-size:12px; margin-bottom:8px; display:none;"></div>
                <button class="btn btn-green" onclick="submitDepositProof()">Submit for Approval ✅</button>
                <button class="btn" style="margin-top:6px;" onclick="renderDepositTelebirrStep()">⬅ Back</button>
            `;
        }

        function copyDepositRequestText() {
            let smsRaw = (document.getElementById('depositSmsText').value || '').trim() || '[SMS text]';
            let phone = depositSelectedNumber ? depositSelectedNumber.phone : '[number]';
            let text = `🪙 Deposit Request\nAmount: ${depositSelectedAmount} coins\nTelegram: ${userName} (#${userShortId})\nSent to Telebirr: ${phone}\nSMS: ${smsRaw}`;
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text).then(function() {
                    showToast('📋 Copied! Send this to the admin.');
                }).catch(function() {
                    showToast('⚠️ Could not copy automatically — select and copy manually.');
                });
            } else {
                showToast('⚠️ Clipboard not available on this browser.');
            }
        }

        function submitDepositProof() {
            let smsRaw = (document.getElementById('depositSmsText').value || '').trim();
            let errorEl = document.getElementById('depositErrorMsg');
            errorEl.style.display = 'none';

            if (!smsRaw) {
                errorEl.innerText = 'እባክህ ሙሉ የቴሌብር ማረጋገጫ SMS ይለጥፉ።';
                errorEl.style.display = 'block';
                return;
            }

            let validationError = validateTelebirrSms(smsRaw, depositSelectedAmount);
            if (validationError) {
                errorEl.innerText = validationError;
                errorEl.style.display = 'block';
                return;
            }

            let txnIdRaw = extractTxnIdFromSms(smsRaw);
            let txnKey = txnIdRaw.replace(/[.#$\[\]\/\s]/g, '').toUpperCase();
            if (!txnKey) {
                errorEl.innerText = 'ልክ ያልሆነ Transaction ID።';
                errorEl.style.display = 'block';
                return;
            }

            if (!db) {
                errorEl.innerText = '⚠️ ከFirebase ጋር መገናኘት አልተቻለም። እባክህ ኢንተርኔትህን አረጋግጥ።';
                errorEl.style.display = 'block';
                return;
            }

            db.ref('transactions/deposits/' + txnKey).transaction(function(current) {
                if (current === null) {
                    return {
                        by: telegramUserId,
                        name: userName,
                        amount: depositSelectedAmount,
                        phone: depositSelectedNumber ? depositSelectedNumber.phone : '',
                        smsText: smsRaw,
                        status: 'pending',
                        timestamp: Date.now()
                    };
                }
                return; // abort - already used
            }).then(function(result) {
                if (result.committed) {
                    renderDepositPendingStep(txnKey);
                } else {
                    errorEl.innerText = '⚠️ ይህ Transaction ID ቀድሞ ጥቅም ላይ ውሏል! ማጭበርበር አይፈቀድም።';
                    errorEl.style.display = 'block';
                }
            }).catch(function(err) {
                console.log('Deposit txn check failed', err);
                errorEl.innerText = '⚠️ ስህተት ተከስቷል፣ እንደገና ሞክር። (' + (err && err.message ? err.message : err) + ')';
                errorEl.style.display = 'block';
            });
        }

        function renderDepositPendingStep(txnKey) {
            let modalBody = document.getElementById('modalBodyText');
            modalBody.innerHTML = `
                <div style="padding: 10px 0 6px 0;">
                    <div class="deposit-spinner"></div>
                    <div style="font-size: 15px; font-weight: bold; margin-top: 8px;">⏳ Waiting for admin approval...</div>
                    <div style="font-size: 12px; color: #64748b; margin-top: 4px;">Transaction ID: ${txnKey}</div>
                </div>
            `;

            db.ref('transactions/deposits/' + txnKey).on('value', function(snapshot) {
                let record = snapshot.val();
                if (!record) return;
                if (record.status === 'approved') {
                    db.ref('transactions/deposits/' + txnKey).off('value');
                    renderDepositApprovedStep(txnKey, record);
                } else if (record.status === 'rejected') {
                    db.ref('transactions/deposits/' + txnKey).off('value');
                    renderDepositRejectedStep(txnKey);
                }
            });
        }

        function renderDepositApprovedStep(txnKey, record) {
            playWalletBalance += record.amount;
            depositedBalance += record.amount; // this portion is real money — winnings funded by it become withdrawable
            updateWalletDisplay();
            addHistoryRecord('deposit', `Deposit via Telebirr (${txnKey})`, record.amount);

            let modalBody = document.getElementById('modalBodyText');
            modalBody.innerHTML = `
                <div style="font-size: 42px; margin-bottom: 4px;">✅</div>
                <div style="font-size: 18px; font-weight: bold; color: var(--success-color); margin-bottom: 6px;">Deposit Approved!</div>
                <div style="font-size: 14px; color: #cbd5e1; margin-bottom: 14px;">${record.amount} coins added to your Play Wallet.<br>Transaction ID: ${txnKey}</div>
                <button class="btn btn-green" onclick="closeCustomModal()">Done</button>
            `;
        }

        function renderDepositRejectedStep(txnKey) {
            let modalBody = document.getElementById('modalBodyText');
            modalBody.innerHTML = `
                <div style="font-size: 42px; margin-bottom: 4px;">❌</div>
                <div style="font-size: 18px; font-weight: bold; color: var(--danger-color); margin-bottom: 6px;">Deposit Rejected</div>
                <div style="font-size: 14px; color: #cbd5e1; margin-bottom: 14px;">Your deposit request (${txnKey}) was rejected by the admin. Please double-check your payment and try again.</div>
                <button class="btn" onclick="closeCustomModal()">Close</button>
            `;
        }

        function handleWithdraw() {
            if (mainWalletBalance <= 0) {
                showToast("💸 Your Main Wallet is empty — win a game first!");
                return;
            }
            if (mainWalletBalance < 50) {
                showToast("💸 ዝቅተኛ የማውጫ መጠን 50 ኮይን ነው። (Minimum withdrawal is 50 coins)");
                return;
            }
            if (!db) {
                showToast("⚠️ Cannot connect to server for withdrawal request.");
                return;
            }
            renderWithdrawStep();
        }

        function renderWithdrawStep() {
            let modalBox = document.getElementById('customModal');
            let modalBody = document.getElementById('modalBodyText');
            modalBody.innerHTML = `
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 12px;">
                    <div style="font-size: 17px; font-weight: bold; color: var(--orange-color);">💸 Withdraw via Telebirr</div>
                    <div onclick="closeCustomModal()" style="cursor:pointer; font-size: 18px; color: #64748b;">✕</div>
                </div>
                <div style="font-size: 13px; color: #94a3b8; margin-bottom: 10px; text-align: left;">Main Wallet balance: <b style="color: var(--success-color);">${Math.floor(mainWalletBalance)} coins</b></div>
                <div style="text-align:left; margin-bottom:6px; font-size:13px; color:#94a3b8;">ወጪ ማድረግ የፈለጉት መጠን</div>
                <input type="number" id="withdrawAmount" min="50" max="${Math.floor(mainWalletBalance)}" step="1" placeholder="e.g. 100" style="width:100%; box-sizing:border-box; padding:10px; border-radius:8px; border:1px solid #2e3b55; background:#1c2640; color:white; font-size:14px; margin-bottom:10px;">
                <div style="text-align:left; margin-bottom:6px; font-size:13px; color:#94a3b8;">ስም (Full Name)</div>
                <input type="text" id="withdrawName" value="${userName}" placeholder="e.g. Abebe Kebede" style="width:100%; box-sizing:border-box; padding:10px; border-radius:8px; border:1px solid #2e3b55; background:#1c2640; color:white; font-size:14px; margin-bottom:10px;">
                <div style="text-align:left; margin-bottom:6px; font-size:13px; color:#94a3b8;">Your Telebirr Number</div>
                <input type="text" id="withdrawPhone" placeholder="e.g. 0911223344" style="width:100%; box-sizing:border-box; padding:10px; border-radius:8px; border:1px solid #2e3b55; background:#1c2640; color:white; font-size:14px; margin-bottom:10px;">
                <button type="button" onclick="copyWithdrawRequestText()" style="width:100%; background:#1c2640; border:1px solid #2e3b55; color:#cbd5e1; border-radius:8px; padding:8px; font-size:12px; margin-bottom:10px; cursor:pointer;">📋 Copy Request Text (send to admin)</button>
                <div id="withdrawErrorMsg" style="color:var(--danger-color); font-size:12px; margin-bottom:8px; display:none;"></div>
                <button class="btn btn-orange" onclick="submitWithdrawRequest()">Submit Request ✅</button>
            `;
            modalBox.style.display = 'flex';
        }

        function copyWithdrawRequestText() {
            let amount = (document.getElementById('withdrawAmount').value || '').trim() || '[amount]';
            let name = (document.getElementById('withdrawName').value || '').trim() || userName;
            let phone = (document.getElementById('withdrawPhone').value || '').trim() || '[your Telebirr number]';
            let text = `💸 Withdraw Request\nAmount: ${amount} coins\nName: ${name}\nTelegram: ${userName} (#${userShortId})\nSend to Telebirr: ${phone}`;
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text).then(function() {
                    showToast('📋 Copied! Send this to the admin.');
                }).catch(function() {
                    showToast('⚠️ Could not copy automatically — select and copy manually.');
                });
            } else {
                showToast('⚠️ Clipboard not available on this browser.');
            }
        }

        function submitWithdrawRequest() {
            let amountRaw = (document.getElementById('withdrawAmount').value || '').trim();
            let name = (document.getElementById('withdrawName').value || '').trim();
            let phone = (document.getElementById('withdrawPhone').value || '').trim();
            let errorEl = document.getElementById('withdrawErrorMsg');
            errorEl.style.display = 'none';

            let amount = parseInt(amountRaw, 10);

            if (!amount || isNaN(amount) || amount <= 0) {
                errorEl.innerText = 'እባክህ ትክክለኛ መጠን አስገባ።';
                errorEl.style.display = 'block';
                return;
            }
            if (amount < 50) {
                errorEl.innerText = 'ዝቅተኛ የማውጫ መጠን 50 ኮይን ነው።';
                errorEl.style.display = 'block';
                return;
            }
            if (amount > mainWalletBalance) {
                errorEl.innerText = `⚠️ በቂ ገንዘብ የለህም። ያለህ ${Math.floor(mainWalletBalance)} ኮይን ብቻ ነው።`;
                errorEl.style.display = 'block';
                return;
            }
            if (!name) {
                errorEl.innerText = 'እባክህ ስምህን አስገባ።';
                errorEl.style.display = 'block';
                return;
            }
            if (!phone) {
                errorEl.innerText = 'እባክህ የቴሌብር ቁጥርህን አስገባ።';
                errorEl.style.display = 'block';
                return;
            }

            let pushRef = db.ref('transactions/withdrawals').push();
            pushRef.set({
                by: telegramUserId,
                name: name,
                telegramName: userName,
                amount: amount,
                phone: phone,
                status: 'pending',
                timestamp: Date.now()
            }).then(function() {
                mainWalletBalance -= amount; // hold funds pending admin approval
                updateWalletDisplay();
                addHistoryRecord('withdraw', 'Withdraw Requested (pending)', -amount);
                renderWithdrawPendingStep(pushRef.key, amount);
            }).catch(function(err) {
                console.log('Withdraw request failed', err);
                errorEl.innerText = '⚠️ ስህተት ተከስቷል፣ እንደገና ሞክር።';
                errorEl.style.display = 'block';
            });
        }

        function renderWithdrawPendingStep(pushId, amount) {
            let modalBody = document.getElementById('modalBodyText');
            modalBody.innerHTML = `
                <div style="padding: 10px 0 6px 0;">
                    <div class="deposit-spinner"></div>
                    <div style="font-size: 15px; font-weight: bold; margin-top: 8px;">⏳ Waiting for admin to send your payment...</div>
                    <div style="font-size: 12px; color: #64748b; margin-top: 4px;">${amount} coins requested</div>
                </div>
            `;

            db.ref('transactions/withdrawals/' + pushId).on('value', function(snapshot) {
                let record = snapshot.val();
                if (!record) return;
                if (record.status === 'approved') {
                    db.ref('transactions/withdrawals/' + pushId).off('value');
                    let modalBodyEl = document.getElementById('modalBodyText');
                    modalBodyEl.innerHTML = `
                        <div style="font-size: 42px; margin-bottom: 4px;">✅</div>
                        <div style="font-size: 18px; font-weight: bold; color: var(--success-color); margin-bottom: 6px;">Payment Sent!</div>
                        <div style="font-size: 14px; color: #cbd5e1; margin-bottom: 14px;">${amount} coins sent to ${record.phone} via Telebirr.</div>
                        <button class="btn btn-green" onclick="closeCustomModal()">Done</button>
                    `;
                } else if (record.status === 'rejected') {
                    db.ref('transactions/withdrawals/' + pushId).off('value');
                    mainWalletBalance += amount; // refund
                    updateWalletDisplay();
                    addHistoryRecord('withdraw', 'Withdraw Rejected (refunded)', amount);
                    let modalBodyEl = document.getElementById('modalBodyText');
                    modalBodyEl.innerHTML = `
                        <div style="font-size: 42px; margin-bottom: 4px;">❌</div>
                        <div style="font-size: 18px; font-weight: bold; color: var(--danger-color); margin-bottom: 6px;">Withdrawal Rejected</div>
                        <div style="font-size: 14px; color: #cbd5e1; margin-bottom: 14px;">Your ${amount} coins have been refunded to your Main Wallet.</div>
                        <button class="btn" onclick="closeCustomModal()">Close</button>
                    `;
                }
            });
        }

        // ---- Audio system: unlock on first tap, beep + speech, so it works even in in-app WebViews ----
        let audioCtx = null;
        let cachedVoices = [];
        let audioUnlocked = false;

        function unlockAudio() {
            if (audioUnlocked) return;
            audioUnlocked = true;
            try {
                if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                if (audioCtx.state === 'suspended') audioCtx.resume();
                // Prime speechSynthesis with a silent utterance so later calls aren't blocked
                if ('speechSynthesis' in window) {
                    let primer = new SpeechSynthesisUtterance('');
                    primer.volume = 0;
                    window.speechSynthesis.speak(primer);
                    cachedVoices = window.speechSynthesis.getVoices();
                    // Some in-app WebViews (Telegram on Android especially) load the
                    // voice list asynchronously and never fire onvoiceschanged, so a
                    // single getVoices() right here can come back empty. Re-check a
                    // few times over the next couple seconds to catch it once it's ready.
                    if (cachedVoices.length === 0) {
                        [300, 800, 1500, 3000].forEach(function(delay) {
                            setTimeout(function() {
                                let v = window.speechSynthesis.getVoices();
                                if (v.length > 0) cachedVoices = v;
                            }, delay);
                        });
                    }
                    // Chrome/WebView TTS engines silently stop speaking after being idle
                    // or after ~15s of continuous speech (a long-standing Chromium bug).
                    // Nudging pause()+resume() periodically keeps the engine alive so
                    // later calls don't just go silent.
                    setInterval(function() {
                        if (window.speechSynthesis.speaking || window.speechSynthesis.pending) {
                            window.speechSynthesis.pause();
                            window.speechSynthesis.resume();
                        }
                    }, 5000);
                }
            } catch(e) {
                console.log("Audio unlock error", e);
            }
        }

        if ('speechSynthesis' in window) {
            window.speechSynthesis.onvoiceschanged = function() {
                cachedVoices = window.speechSynthesis.getVoices();
            };
        }

        function playBeep() {
            try {
                if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                if (audioCtx.state === 'suspended') audioCtx.resume();
                let osc = audioCtx.createOscillator();
                let gain = audioCtx.createGain();
                osc.type = 'sine';
                osc.frequency.value = 880;
                gain.gain.setValueAtTime(0.15, audioCtx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.2);
                osc.connect(gain);
                gain.connect(audioCtx.destination);
                osc.start();
                osc.stop(audioCtx.currentTime + 0.2);
            } catch(e) {
                console.log("Beep error", e);
            }
        }

        function speakNumber(callText) {
            if (!soundEnabled) return;

            // Always play a beep first - this works even where speech synthesis is blocked (e.g. Telegram WebView)
            playBeep();

            if ('speechSynthesis' in window) {
                try {
                    window.speechSynthesis.cancel();
                    // Re-check the voice list right before speaking too -- on some
                    // WebViews it's still empty at unlock time but ready a bit later.
                    if (cachedVoices.length === 0) {
                        cachedVoices = window.speechSynthesis.getVoices();
                    }
                    let spokenText = callText.replace('-', ' ');
                    let utterance = new SpeechSynthesisUtterance(spokenText);
                    utterance.lang = 'en-US';
                    utterance.rate = 0.9;
                    if (cachedVoices.length > 0) {
                        let enVoice = cachedVoices.find(v =>
                            v.lang && v.lang.startsWith('en') && /male/i.test(v.name) && !/female/i.test(v.name)
                        );
                        if (!enVoice) {
                            // Common male-voice names across platforms (Windows/Android/iOS/macOS)
                            enVoice = cachedVoices.find(v =>
                                v.lang && v.lang.startsWith('en') && /(david|daniel|alex|fred|mark|guy|male)/i.test(v.name)
                            );
                        }
                        if (!enVoice) {
                            enVoice = cachedVoices.find(v => v.lang && v.lang.startsWith('en'));
                        }
                        if (enVoice) utterance.voice = enVoice;
                    }
                    // Small delay so it doesn't collide with the cancel() on some browsers
                    setTimeout(function() {
                        window.speechSynthesis.speak(utterance);
                    }, 120);
                } catch(e) {
                    console.log("Speech synthesis error", e);
                }
            }
        }

        function toggleAudio() {
            unlockAudio();
            soundEnabled = !soundEnabled;
            let btn = document.getElementById('audioToggleBtn');
            if (btn) {
                btn.innerText = soundEnabled ? '🔊' : '🔇';
            }
        }

        function initializeGameBoard() {
            let boardGrid = document.getElementById('gameBoardGrid');
            if (!boardGrid) return;
            boardGrid.innerHTML = '';
            lastCalledBoardCellNum = null;

            let ranges = [[1,15], [16,30], [31,45], [46,60], [61,75]];
            let matrixCols = [];

            for(let c=0; c<5; c++) {
                let colNums = [];
                for(let n=ranges[c][0]; n<=ranges[c][1]; n++) {
                    colNums.push(n);
                }
                matrixCols.push(colNums);
            }

            for(let r=0; r<15; r++) {
                for(let c=0; c<5; c++) {
                    let num = matrixCols[c][r];
                    let cell = document.createElement('div');
                    cell.id = `board_cell_${num}`;
                    cell.style.cssText = "background: #4a4270; border-radius: 6px; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: bold; color: #ffffff; min-height: 18px;";
                    cell.innerText = num;
                    boardGrid.appendChild(cell);
                }
            }
        }

        function generateBingoMatrix() {
            let matrix = [];
            let ranges = [[1,15], [16,30], [31,45], [46,60], [61,75]];
            
            for(let col = 0; col < 5; col++) {
                let colNums = [];
                let min = ranges[col][0];
                let max = ranges[col][1];
                while(colNums.length < 5) {
                    let r = Math.floor(Math.random() * (max - min + 1)) + min;
                    if(!colNums.includes(r)) colNums.push(r);
                }
                matrix.push(colNums);
            }

            let rows = [];
            for(let r = 0; r < 5; r++) {
                let row = [];
                for(let c = 0; c < 5; c++) {
                    row.push(matrix[c][r]);
                }
                rows.push(row);
            }
            rows[2][2] = 'FREE';
            return rows;
        }

        function initializeUserCards() {
            let container = document.getElementById('userCardsContainer');
            if (!container) return;
            container.innerHTML = '';
            userBingoMatrices = [];
            calledNumbersList = [];

            if (selectedCards.length === 0) {
                container.innerHTML = `
                    <div style="background: var(--card-bg); border-radius: 8px; padding: 16px 10px; text-align: center; border: 1px solid #1e293b;">
                        <div style="font-size: 17px; font-weight: bold; color: white; margin-bottom: 10px;">Watching Only</div>
                        <div style="font-size: 12px; color: #cbd5e1; line-height: 1.6;">የዚህ ዙር ጨዋታ ተጀምሯል። አዲስ ዙር<br>እስኪጀምር እዚሁ ይጠብቁ።</div>
                    </div>`;
                let autoBtn = document.getElementById('gameAutomaticBtn');
                if (autoBtn) {
                    autoBtn.disabled = true;
                    autoBtn.style.opacity = '0.5';
                    autoBtn.style.pointerEvents = 'none';
                }
                return;
            } else {
                let autoBtn = document.getElementById('gameAutomaticBtn');
                if (autoBtn) {
                    autoBtn.disabled = false;
                    autoBtn.style.opacity = '1';
                    autoBtn.style.pointerEvents = 'auto';
                }
            }

            selectedCards.forEach((cardNum, idx) => {
                let sharedEntry = takenCardsData[cardNum];
                let matrix = (sharedEntry && sharedEntry.matrix) ? sharedEntry.matrix : generateBingoMatrix();
                userBingoMatrices.push({ id: cardNum, matrix: matrix });

                let isCompact = selectedCards.length > 1;
                let cardDiv = document.createElement('div');
                cardDiv.className = isCompact ? 'bingo-card-container compact' : 'bingo-card-container';
                cardDiv.innerHTML = `<div style="font-size:${isCompact ? 9 : 10}px; margin-bottom:2px; color:var(--orange-color); font-weight: bold; text-align: center;">Cartela No : ${cardNum}</div>`;

                let grid = document.createElement('div');
                grid.className = isCompact ? 'bingo-grid compact' : 'bingo-grid';
                let headerClass = isCompact ? 'bingo-header-cell compact' : 'bingo-header-cell';
                let bodyHTML = `<div class="${headerClass}">B</div><div class="${headerClass}">I</div><div class="${headerClass}">N</div><div class="${headerClass}">G</div><div class="${headerClass}">O</div>`;

                for(let r = 0; r < 5; r++) {
                    for(let c = 0; c < 5; c++) {
                        let val = matrix[r][c];
                        let cellId = `c_${idx}_${r}_${c}`;
                        let isFree = (val === 'FREE');
                        let className = (isFree ? 'bingo-cell free' : 'bingo-cell') + (isCompact ? ' compact' : '');
                        if(isFree) val = '✨';
                        bodyHTML += `<div id="${cellId}" class="${className}">${val}</div>`;
                    }
                }
                grid.innerHTML = bodyHTML;
                cardDiv.appendChild(grid);
                container.appendChild(cardDiv);
            });
        }

        function startBingoGame() {
            let statusText = document.getElementById('gameStatusText');

            if (statusText) {
                statusText.innerText = 'Waiting for Caller...';
                statusText.style.color = 'var(--orange-color)';
            }

            if (db) {
                subscribeCalledNumbers();
                subscribeRoundEnd();
                subscribePrizePool();
                acquireRoundCaller();
            }

            lastCallTime = Date.now();
            clearInterval(gameInterval);
            gameInterval = setInterval(function() {
                if (!db || roomRoundEndedCached || !isRoundCaller) return;
                if (calledNumbersList.length >= 75) {
                    clearInterval(gameInterval);
                    return;
                }
                attemptCallNextNumber();
            }, 1500);
        }

        function showWinnerPopup(winners) {
            let modalBox = document.getElementById('customModal');
            let modalBody = document.getElementById('modalBodyText');

            // winners: [{ cardNum, by, name }] — all real, from Firebase (or local fallback)
            let mainWinner = winners[0] || { cardNum: null, by: telegramUserId, name: userName };
            let mainMatrix = null;
            if (mainWinner.cardNum && takenCardsData[mainWinner.cardNum] && takenCardsData[mainWinner.cardNum].matrix) {
                mainMatrix = takenCardsData[mainWinner.cardNum].matrix;
            } else {
                let ownCard = userBingoMatrices.find(c => c.id === mainWinner.cardNum);
                mainMatrix = ownCard ? ownCard.matrix : generateBingoMatrix();
            }

            let playersListHTML = `
                <div style="display: flex; justify-content: center; gap: 6px; margin-bottom: 12px; flex-wrap: wrap;">
                    ${winners.map(function(w) {
                        let displayName = w.name || "Player";
                        let shortId = (w.by && w.by !== "guest_user") ? w.by.slice(-6) : "guest";
                        let initial = displayName.charAt(0).toUpperCase();
                        return `
                        <div style="background: #1c2640; border: 1px solid #2e3b55; border-radius: 20px; padding: 4px 10px; font-size: 13px; display: flex; align-items: center; gap: 5px;">
                            <span style="background: #3b82f6; color: white; width: 20px; height: 20px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-size: 11px; font-weight: bold;">${initial}</span>
                            <span>${displayName} #${shortId} · Cartela ${w.cardNum}</span>
                        </div>`;
                    }).join('')}
                </div>
            `;

            let winnersCountText = winners.length === 1 ? "🎉 1 player won!" : `🎉 ${winners.length} players won!`;

            let tableHTML = `
                <div class="bingo-card-container" style="margin-bottom: 12px; border: 1px solid rgba(59, 130, 246, 0.4); background: #131b2e; padding: 8px; border-radius: 12px;">
                    <div style="font-size:13px; margin-bottom:6px; color:var(--orange-color); font-weight: bold; text-align: center;">🏆 Winning Cartela : ${mainWinner.cardNum}</div>
                    <div class="bingo-grid">
                        <div class="bingo-header-cell" style="background-color:#3b82f6;">B</div>
                        <div class="bingo-header-cell" style="background-color:#8b5cf6;">I</div>
                        <div class="bingo-header-cell" style="background-color:#a855f7;">N</div>
                        <div class="bingo-header-cell" style="background-color:#10b981;">G</div>
                        <div class="bingo-header-cell" style="background-color:#f97316;">O</div>`;

            let calledSetForPopup = {};
            calledNumbersList.forEach(function(n) { calledSetForPopup[n] = true; });
            let winPattern = getWinningPattern(mainMatrix, calledSetForPopup);
            let winPatternSet = {};
            winPattern.forEach(function(pos) { winPatternSet[pos[0] + '_' + pos[1]] = true; });

            for(let r = 0; r < 5; r++) {
                for(let c = 0; c < 5; c++) {
                    let val = mainMatrix[r][c];
                    let isFree = (val === 'FREE');
                    let isInPattern = winPatternSet[r + '_' + c];
                    let cellClass = 'bingo-cell';
                    if (isFree) {
                        cellClass += ' free';
                    } else if (isInPattern) {
                        cellClass += ' win-pattern';
                    } else if (calledSetForPopup[val]) {
                        cellClass += ' called-not-pattern';
                    }
                    if(isFree) val = '✨';
                    tableHTML += `<div class="${cellClass}">${val}</div>`;
                }
            }
            tableHTML += `</div></div>`;

            modalBody.innerHTML = `
                <div style="font-size: 34px; margin-bottom: 2px;">👑</div>
                <div style="font-size: 22px; font-weight: bold; color: var(--orange-color); margin-bottom: 4px;">BINGO!</div>
                <div style="font-size: 13px; color: #cbd5e1; margin-bottom: 10px;">${winnersCountText}</div>
                ${playersListHTML}
                ${tableHTML}
                <div id="popupTimer" style="font-size: 13px; color: var(--orange-color); background: rgba(245, 158, 11, 0.1); padding: 8px; border-radius: 8px; border: 1px solid rgba(245, 158, 11, 0.2);">
                    🟠 Auto-starting next game in 5s
                </div>
            `;

            modalBox.style.display = 'flex';

            let count = 5;
            let timerInterval = setInterval(function() {
                count--;
                let timerEl = document.getElementById('popupTimer');
                if (timerEl) {
                    timerEl.innerText = `🟠 Auto-starting next game in ${count}s`;
                }
                if (count <= 0) {
                    clearInterval(timerInterval);
                    modalBox.style.display = 'none';
                    openSelection();
                }
            }, 1000);
        }

        let lastCalledBoardCellNum = null;

        function markBoardAndCards(num) {
            if (lastCalledBoardCellNum !== null) {
                let prevCell = document.getElementById(`board_cell_${lastCalledBoardCellNum}`);
                if (prevCell) {
                    prevCell.style.background = "var(--orange-color)";
                    prevCell.style.color = "white";
                }
            }
            let boardCell = document.getElementById(`board_cell_${num}`);
            if (boardCell) {
                boardCell.style.background = "var(--success-color)";
                boardCell.style.color = "white";
            }
            lastCalledBoardCellNum = num;

            userBingoMatrices.forEach((cardObj, idx) => {
                let matrix = cardObj.matrix;
                for(let r = 0; r < 5; r++) {
                    for(let c = 0; c < 5; c++) {
                        if(matrix[r][c] === num) {
                            let cell = document.getElementById(`c_${idx}_${r}_${c}`);
                            if(cell) cell.classList.add('marked');
                        }
                    }
                }
            });
        }
    </script>
</body>
</html>
