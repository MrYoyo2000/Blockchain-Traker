import os
import requests
import time
import sys
import pandas as pd
from datetime import datetime
from collections import deque
import threading

# === Configuration ===
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "WGJ2Z5USQYMT8SKQXMCKRG8Z58TMX1NZMB")

# WHALE Thresholds
WHALE_THRESHOLD = {
    'ETH': 0.1,  # Lowered to detect more whales
    'BTC': 0.5,  # Lowered to detect more whales
}


class UltraBlockchainTracker:

    def __init__(self, eth_api_key=None):
        self.eth_api_key = eth_api_key

        # Storage
        self.all_transactions = deque(maxlen=1000)
        self.whale_transactions = deque(maxlen=200)
        self.normal_transactions = deque(maxlen=200)
        self.seen_hashes = set()

        # Prices
        self.prices = {'ETH': 3200, 'BTC': 98000}

        # Statistics
        self.stats = {
            'total_tx': 0,
            'whales': 0,
            'normal': 0,
            'eth_vol': 0,
            'btc_vol': 0,
            'errors': 0
        }

        self.running = True
        self.lock = threading.Lock()
        self.last_update = datetime.now()
        self.last_eth_block = None  # Keep track of the last scanned block

    def add_transaction(self, tx_data):
        """Add a transaction to the tracker"""
        with self.lock:
            tx_hash = tx_data.get('hash', '')

            if not tx_hash or tx_hash in self.seen_hashes:
                return False

            self.seen_hashes.add(tx_hash)

            # Classify transaction
            is_whale = tx_data['value'] >= WHALE_THRESHOLD.get(tx_data['chain'], 999999)
            tx_data['type'] = '🐋' if is_whale else '📊'

            # Add to storage
            self.all_transactions.append(tx_data)

            if is_whale:
                self.whale_transactions.append(tx_data)
                self.stats['whales'] += 1
                print(f"\n🚨 WHALE {tx_data['chain']}: {tx_data['value']:.4f} = ${tx_data['usd']:,.0f} 🚨")
            else:
                self.normal_transactions.append(tx_data)
                self.stats['normal'] += 1

            self.stats['total_tx'] += 1

            if tx_data['chain'] == 'ETH':
                self.stats['eth_vol'] += tx_data['value']
            elif tx_data['chain'] == 'BTC':
                self.stats['btc_vol'] += tx_data['value']

            self.last_update = datetime.now()

            return True

    def get_prices(self):
        """Fetch current cryptocurrency prices"""
        try:
            response = requests.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={'ids': 'bitcoin,ethereum', 'vs_currencies': 'usd'},
                timeout=5
            )
            data = response.json()
            self.prices['ETH'] = data.get('ethereum', {}).get('usd', 3200)
            self.prices['BTC'] = data.get('bitcoin', {}).get('usd', 98000)
            print(f"✅ Prices updated: ETH ${self.prices['ETH']:,.0f} | BTC ${self.prices['BTC']:,.0f}")
        except Exception as e:
            print(f"⚠️ Price fetch error: {e}")

    def scan_etherscan_pending(self):
        """Scan Ethereum pending transactions using JSON-RPC approach"""
        print("🔍 Starting Etherscan pending scan...")

        rpc_endpoints = [
            "https://eth.llamarpc.com",
            "https://eth.rpc.blxrbdn.com",
            "https://rpc.flashbots.net"
        ]
        current_endpoint_idx = 0

        while self.running:
            try:
                rpc_url = rpc_endpoints[current_endpoint_idx]

                # Get block number if not already set
                if self.last_eth_block is None:
                    payload = {
                        "jsonrpc": "2.0",
                        "method": "eth_blockNumber",
                        "params": [],
                        "id": 1
                    }
                    response = requests.post(rpc_url, json=payload, timeout=5)
                    response.raise_for_status()

                    try:
                        data = response.json()
                    except ValueError:
                        print(f"⚠️ Invalid JSON from {rpc_url}, trying next endpoint...")
                        current_endpoint_idx = (current_endpoint_idx + 1) % len(rpc_endpoints)
                        time.sleep(2)
                        continue

                    result = data.get('result')
                    if result and isinstance(result, str) and result.startswith('0x'):
                        self.last_eth_block = int(result, 16)
                        print(f"📦 Starting from block: {self.last_eth_block}")
                    else:
                        print(f"⚠️ Failed to get block number: {data}")
                        time.sleep(5)
                        continue

                # Get next block number
                next_block = self.last_eth_block + 1
                block_hex = hex(next_block)

                # Get block transactions
                payload = {
                    "jsonrpc": "2.0",
                    "method": "eth_getBlockByNumber",
                    "params": [block_hex, True],
                    "id": 1
                }
                response = requests.post(rpc_url, json=payload, timeout=5)
                response.raise_for_status()

                try:
                    block_data = response.json().get('result', {})
                except ValueError:
                    print(f"⚠️ Invalid JSON response, trying next endpoint...")
                    current_endpoint_idx = (current_endpoint_idx + 1) % len(rpc_endpoints)
                    time.sleep(2)
                    continue

                if block_data and 'transactions' in block_data:
                    txs = block_data['transactions']
                    print(f"✅ {len(txs)} transactions in block {next_block}")

                    for tx in txs:
                        try:
                            value_wei = int(tx.get('value', '0x0'), 16)
                            value_eth = value_wei / 10 ** 18

                            if value_eth < 0.01:  # Minimum 0.01 ETH
                                continue

                            tx_data = {
                                'time': datetime.now().strftime('%H:%M:%S'),
                                'chain': 'ETH',
                                'from': tx.get('from', 'N/A')[:42],
                                'to': tx.get('to', 'Contract')[:42] if tx.get('to') else 'Contract',
                                'value': value_eth,
                                'usd': value_eth * self.prices['ETH'],
                                'hash': tx.get('hash', 'N/A'),
                                'block': next_block
                            }

                            self.add_transaction(tx_data)
                        except Exception as e:
                            continue

                    # Update last scanned block
                    self.last_eth_block = next_block
                else:
                    # If the block is empty, wait a bit
                    time.sleep(5)

                time.sleep(10)  # Wait for next block (~12 sec)

            except requests.exceptions.RequestException as e:
                print(f"❌ Request error ({rpc_endpoints[current_endpoint_idx]}): {e}")
                current_endpoint_idx = (current_endpoint_idx + 1) % len(rpc_endpoints)
                self.stats['errors'] += 1
                time.sleep(5)
            except Exception as e:
                print(f"❌ Etherscan error: {e}")
                self.stats['errors'] += 1
                time.sleep(5)

    def scan_bitcoin_mempool(self):
        """Scan Bitcoin mempool for transactions"""
        print("🔍 Starting Bitcoin mempool scan...")

        while self.running:
            try:
                # Blockstream API
                response = requests.get("https://blockstream.info/api/mempool/recent", timeout=5)
                txs = response.json()

                print(f"💰 {len(txs)} BTC transactions retrieved")

                for tx in txs[:50]:
                    try:
                        total_value = sum(vout.get('value', 0) for vout in tx.get('vout', []))
                        btc_value = total_value / 10 ** 8

                        if btc_value < 0.001:
                            continue

                        # Get first input and output addresses
                        from_addr = "Unknown"
                        to_addr = "Unknown"

                        if tx.get('vin') and len(tx['vin']) > 0:
                            from_addr = tx['vin'][0].get('prevout', {}).get('scriptpubkey_address', 'Unknown')

                        if tx.get('vout') and len(tx['vout']) > 0:
                            to_addr = tx['vout'][0].get('scriptpubkey_address', 'Unknown')

                        tx_data = {
                            'time': datetime.now().strftime('%H:%M:%S'),
                            'chain': 'BTC',
                            'from': from_addr if from_addr != 'Unknown' else f"{len(tx.get('vin', []))} inputs",
                            'to': to_addr if to_addr != 'Unknown' else f"{len(tx.get('vout', []))} outputs",
                            'value': btc_value,
                            'usd': btc_value * self.prices['BTC'],
                            'hash': tx.get('txid', 'N/A'),
                            'block': 'Mempool'
                        }

                        self.add_transaction(tx_data)
                    except Exception as e:
                        continue

                time.sleep(5)

            except Exception as e:
                print(f"❌ Bitcoin error: {e}")
                self.stats['errors'] += 1
                time.sleep(5)

    def scan_blockchain_info(self):
        """Scan blockchain.info for unconfirmed transactions (alternative source)"""
        print("🔍 Starting Blockchain.info scan...")

        while self.running:
            try:
                response = requests.get(
                    "https://blockchain.info/unconfirmed-transactions?format=json",
                    timeout=5
                )
                data = response.json()

                txs = data.get('txs', [])
                print(f"🌐 {len(txs)} TXs from blockchain.info")

                for tx in txs[:30]:
                    try:
                        btc_value = sum(out.get('value', 0) for out in tx.get('out', [])) / 10 ** 8

                        if btc_value < 0.001:
                            continue

                        # Get first input and output addresses
                        from_addr = "Unknown"
                        to_addr = "Unknown"

                        if tx.get('inputs') and len(tx['inputs']) > 0:
                            from_addr = tx['inputs'][0].get('prev_out', {}).get('addr', 'Unknown')

                        if tx.get('out') and len(tx['out']) > 0:
                            to_addr = tx['out'][0].get('addr', 'Unknown')

                        tx_data = {
                            'time': datetime.now().strftime('%H:%M:%S'),
                            'chain': 'BTC',
                            'from': from_addr if from_addr != 'Unknown' else 'Multiple',
                            'to': to_addr if to_addr != 'Unknown' else 'Multiple',
                            'value': btc_value,
                            'usd': btc_value * self.prices['BTC'],
                            'hash': str(tx.get('hash', 'N/A')),
                            'block': 'Unconfirmed'
                        }

                        self.add_transaction(tx_data)
                    except:
                        continue

                time.sleep(8)

            except Exception as e:
                print(f"❌ Blockchain.info error: {e}")
                self.stats['errors'] += 1
                time.sleep(10)

    def display_dashboard(self):
        """Display live dashboard with transaction data"""
        print("🖥️  Starting dashboard...")
        time.sleep(5)  # Wait a bit before displaying

        while self.running:
            try:
                os.system('clear' if os.name == 'posix' else 'cls')

                print("╔" + "═" * 200 + "╗")
                print("║" + " ⚡ ULTRA BLOCKCHAIN TRACKER - LIVE ⚡ ".center(200) + "║")
                print("╚" + "═" * 200 + "╝")
                print()

                # Statistics
                elapsed = (datetime.now() - self.last_update).total_seconds()
                status = "🟢 ACTIVE" if elapsed < 30 else "🟡 WAITING"

                print(f"💰 ETH: ${self.prices['ETH']:,.0f} | BTC: ${self.prices['BTC']:,.0f}")
                print(
                    f"📊 Total: {self.stats['total_tx']} TX | 🐋 Whales: {self.stats['whales']} | 📊 Normal: {self.stats['normal']} | {status}")
                print(
                    f"📈 Volume: ETH {self.stats['eth_vol']:.2f} | BTC {self.stats['btc_vol']:.4f} | ❌ Errors: {self.stats['errors']}")
                print(f"⚙️  Thresholds: ETH ≥{WHALE_THRESHOLD['ETH']} | BTC ≥{WHALE_THRESHOLD['BTC']}")
                print(f"🕐 Last TX: {elapsed:.0f}s ago")
                print()

                with self.lock:
                    all_recent = list(self.all_transactions)

                # Get last 100 transactions and separate by chain
                eth_txs = [tx for tx in all_recent if tx['chain'] == 'ETH'][-100:]
                btc_txs = [tx for tx in all_recent if tx['chain'] == 'BTC'][-100:]

                # ETHEREUM - Large amounts
                eth_large = [tx for tx in eth_txs if tx['value'] >= 1.0]
                eth_small = [tx for tx in eth_txs if tx['value'] < 1.0]

                if eth_large:
                    print("═" * 200)
                    print("💎 ETHEREUM - LARGE TRANSACTIONS (≥ 1.0 ETH)")
                    print("═" * 200)
                    print()

                    for tx in eth_large[-20:]:
                        print(f"  🔴 {tx['time']}  │  {tx['value']:.6f} ETH = ${tx['usd']:,.2f}")
                        print(f"  ├─ FROM: {tx['from']}")
                        print(f"  ├─ TO:   {tx['to']}")
                        print(f"  └─ HASH: {tx['hash']}")
                        print()

                # ETHEREUM - Small amounts
                if eth_small:
                    print("═" * 200)
                    print("💎 ETHEREUM - NORMAL TRANSACTIONS (< 1.0 ETH)")
                    print("═" * 200)
                    print()

                    for tx in eth_small[-20:]:
                        print(f"  ⚪ {tx['time']}  │  {tx['value']:.6f} ETH = ${tx['usd']:,.2f}")
                        print(f"  ├─ FROM: {tx['from']}")
                        print(f"  ├─ TO:   {tx['to']}")
                        print(f"  └─ HASH: {tx['hash']}")
                        print()

                # BITCOIN - Large amounts
                btc_large = [tx for tx in btc_txs if tx['value'] >= 0.5]
                btc_small = [tx for tx in btc_txs if tx['value'] < 0.5]

                if btc_large:
                    print("═" * 200)
                    print("₿ BITCOIN - LARGE TRANSACTIONS (≥ 0.5 BTC)")
                    print("═" * 200)
                    print()

                    for tx in btc_large[-20:]:
                        print(f"  🔴 {tx['time']}  │  {tx['value']:.6f} BTC = ${tx['usd']:,.2f}")
                        print(f"  ├─ FROM: {tx['from']}")
                        print(f"  ├─ TO:   {tx['to']}")
                        print(f"  └─ HASH: {tx['hash']}")
                        print()

                # BITCOIN - Small amounts
                if btc_small:
                    print("═" * 200)
                    print("₿ BITCOIN - NORMAL TRANSACTIONS (< 0.5 BTC)")
                    print("═" * 200)
                    print()

                    for tx in btc_small[-20:]:
                        print(f"  ⚪ {tx['time']}  │  {tx['value']:.6f} BTC = ${tx['usd']:,.2f}")
                        print(f"  ├─ FROM: {tx['from']}")
                        print(f"  ├─ TO:   {tx['to']}")
                        print(f"  └─ HASH: {tx['hash']}")
                        print()

                if not eth_txs and not btc_txs:
                    print("⏳ Waiting for transactions...".center(200))
                    print("   (This may take 10-30 seconds at startup)".center(200))
                    print()

                # WHALES SECTION
                with self.lock:
                    all_whales = list(self.whale_transactions)

                if all_whales:
                    eth_whales = [tx for tx in all_whales if tx['chain'] == 'ETH'][-10:]
                    btc_whales = [tx for tx in all_whales if tx['chain'] == 'BTC'][-10:]

                    if eth_whales or btc_whales:
                        print("═" * 200)
                        print("🐋 WHALE ALERTS")
                        print("═" * 200)
                        print()

                        if eth_whales:
                            print("💎 ETHEREUM WHALES")
                            print("─" * 200)
                            for tx in eth_whales:
                                print(f"  🚨 {tx['time']}  │  AMOUNT: {tx['value']:.4f} ETH = ${tx['usd']:,.2f}")
                                print(f"     ├─ FROM: {tx['from']}")
                                print(f"     ├─ TO:   {tx['to']}")
                                print(f"     └─ HASH: {tx['hash']}")
                                print()

                        if btc_whales:
                            print("₿ BITCOIN WHALES")
                            print("─" * 200)
                            for tx in btc_whales:
                                print(f"  🚨 {tx['time']}  │  AMOUNT: {tx['value']:.4f} BTC = ${tx['usd']:,.2f}")
                                print(f"     ├─ FROM: {tx['from']}")
                                print(f"     ├─ TO:   {tx['to']}")
                                print(f"     └─ HASH: {tx['hash']}")
                                print()

                print("═" * 200)
                print(f"🕐 {datetime.now().strftime('%H:%M:%S')} | Refresh: 3 sec | Ctrl+C = Stop")
                print("═" * 200)

                time.sleep(3)

            except Exception as e:
                print(f"❌ Dashboard error: {e}")
                time.sleep(3)

    def run(self):
        """Start all scanning threads and main loop"""
        print("\n" + "═" * 150)
        print("⚡ ULTRA BLOCKCHAIN TRACKER".center(150))
        print("═" * 150)
        print()

        if not self.eth_api_key:
            print("⚠️  No Etherscan key configured!")
            return

        print(f"✅ Key: {self.eth_api_key[:10]}...")
        print()

        # Load prices
        print("📊 Loading prices...")
        self.get_prices()
        print()

        print("🚀 Launching scanners...")
        print("   • Etherscan (blocks)")
        print("   • Bitcoin Blockstream")
        print("   • Bitcoin Blockchain.info")
        print("   • Dashboard")
        print()
        print("⏳ First transactions will arrive in 10-30 seconds...")
        print()

        # Start scanner threads
        threads = [
            threading.Thread(target=self.scan_etherscan_pending, daemon=True),
            threading.Thread(target=self.scan_bitcoin_mempool, daemon=True),
            threading.Thread(target=self.scan_blockchain_info, daemon=True),
            threading.Thread(target=self.display_dashboard, daemon=True)
        ]

        for t in threads:
            t.start()

        # Main loop with price updates
        try:
            while self.running:
                time.sleep(30)
                self.get_prices()
        except KeyboardInterrupt:
            print("\nShutting down scanner...")
            self.running = False
            # Small delay to allow threads to notice the flag
            time.sleep(1)

        finally:
            # Ensure all threads are stopped
            self.running = False

if __name__ == "__main__":
    print("\n⚡ ULTRA BLOCKCHAIN TRACKER v2.0\n")

    if not ETHERSCAN_API_KEY:
        print("❌ ERROR: Configure ETHERSCAN_API_KEY!")
        exit(1)

    print(f"✅ Key: {ETHERSCAN_API_KEY[:10]}...{ETHERSCAN_API_KEY[-4:]}")
    print(f"\n⚙️  Thresholds: ETH ≥{WHALE_THRESHOLD['ETH']} | BTC ≥{WHALE_THRESHOLD['BTC']}")
    print("\n💡 TIPS:")
    print("   • Wait 10-30 sec for the first transactions")
    print("   • Debug messages display in real-time")
    print("   • Dashboard starts after 5 seconds")
    print()

    input("▶️  PRESS ENTER to launch...\n")

    tracker = UltraBlockchainTracker(eth_api_key=ETHERSCAN_API_KEY)
    tracker.run()