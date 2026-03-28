# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Ultra Blockchain Tracker** - Real-time monitoring of Ethereum and Bitcoin transactions with whale detection and multi-platform support.

**Architecture:**
- Current: Single-file Python CLI (`Blockchain traker.py`)
- Future: Backend API (Flask) + Multi-platform clients (Web/Mobile/Desktop)

## Security ⚠️

**API Key Management:**
- API keys are stored in `.env` file (NEVER committed)
- `.env` is in `.gitignore` - ensure it stays that way
- `.env.example` shows required variables
- All blockchain API keys must be hidden on backend only
- Clients should NEVER access blockchain APIs directly

**Critical Files:**
- `.env` - Local secrets (NEVER commit this)
- `.env.example` - Template for setup
- `.gitignore` - Prevents `.env` from being committed

## Current Application: Python CLI

**Main File:** `Blockchain traker.py` (450+ lines)

**Key Components:**
1. `UltraBlockchainTracker` class - Main application
2. `scan_etherscan_pending()` - Ethereum block monitoring via JSON-RPC
3. `scan_bitcoin_mempool()` - Bitcoin mempool via Blockstream API
4. `scan_blockchain_info()` - Alternative BTC data source
5. `display_dashboard()` - Terminal UI with pandas tables
6. Multi-threaded design with thread-safe transaction storage

**Running the CLI:**
```bash
python "Blockchain traker.py"
```

## Future Phases (Backend & Clients)

### Phase 2: Backend API (Flask)

**Goal:** Create secure API server that:
- Hides all blockchain API keys
- Serves transaction data to multiple clients
- Provides real-time WebSocket updates
- Manages rate limiting

**Proposed Structure:**
```
blockchain-tracker-backend/
├── app.py                 # Flask app
├── config.py             # Configuration from .env
├── models/
│   └── transaction.py    # Data models
├── services/
│   └── blockchain_scanner.py  # Refactored: UltraBlockchainTracker
├── routes/
│   ├── transactions.py   # /api/transactions
│   ├── whales.py        # /api/whales
│   └── prices.py        # /api/prices
├── requirements.txt
├── .env.example
└── docker-compose.yml
```

**API Endpoints to Create:**
- `GET /api/transactions` - Last 100 transactions (filterable by chain)
- `GET /api/whales` - Last whale transactions
- `GET /api/prices` - Current ETH/BTC prices
- `GET /api/stats` - Dashboard statistics
- `WebSocket /ws` - Real-time updates

**Key Refactoring:**
- Extract `UltraBlockchainTracker` logic into `services/blockchain_scanner.py`
- Keep CLI version for backward compatibility
- Backend should use same scanning logic

### Phase 3: Web Client (React)

**Goal:** Web dashboard matching CLI visual style

**Design Notes:**
- Display should match current terminal output
- Separate sections for ETH and BTC
- Show large/small transactions differently
- Live whale alerts section
- Use same emojis and formatting (🐋 🔴 ⚪ ₿ 💎)

**Tech Stack:** React + TypeScript

**UI Sections:**
1. Header with prices (💰 ETH / BTC)
2. Statistics bar (Total TX, Whales, Normal, Errors)
3. ETH Large Transactions (≥ 1.0 ETH)
4. ETH Normal Transactions (< 1.0 ETH)
5. BTC Large Transactions (≥ 0.5 BTC)
6. BTC Normal Transactions (< 0.5 BTC)
7. Whale Alerts section

### Phase 4: Mobile Client (React Native)

**Goal:** iOS/Android/iPad app with same data

**Features:**
- Same dashboard as web (optimized for touch)
- Push notifications for whales
- Can work with iPad (larger screen)

### Phase 5: Desktop Client (Electron)

**Goal:** Windows/Mac/Linux standalone app

**Features:**
- System tray notifications for whales
- Auto-updates
- Same UI as web

## Development Workflow

**When adding features:**
1. Update `.env.example` if new env vars needed
2. Keep `Blockchain traker.py` CLI working
3. For backend phase: refactor logic into modules, keep separation of concerns
4. All API keys must stay on backend only

**When creating clients:**
- Connect to backend API endpoints only
- NEVER make direct calls to Etherscan/Blockstream/Blockchain.info APIs
- Use WebSocket for real-time updates

## Testing

- CLI: `python "Blockchain traker.py"` should show live dashboard
- Backend: Test API endpoints with curl or Postman
- Frontend: Should display data matching CLI visual style

## Deployment

- Backend: Docker container (see `docker-compose.yml`)
- Web: Vercel or Netlify (static hosting)
- Mobile: App Store / Google Play (after development)
- Desktop: Auto-updater with Electron

## Important Notes

- API keys must NEVER appear in git history or client code
- All three data sources (Etherscan, Blockstream, Blockchain.info) should remain available
- WebSocket support is essential for real-time updates
- Maintain thread-safety patterns from CLI version
