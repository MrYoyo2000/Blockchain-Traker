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

# Seuils WHALE
WHALE_THRESHOLD = {
    'ETH': 0.1,  # BAISSÉ pour voir plus de whales
    'BTC': 0.5,  # BAISSÉ pour voir plus de whales
}


class UltraBlockchainTracker:

    def __init__(self, eth_api_key=None):
        self.eth_api_key = eth_api_key

        # Stockage
        self.all_transactions = deque(maxlen=500)
        self.whale_transactions = deque(maxlen=100)
        self.normal_transactions = deque(maxlen=100)
        self.seen_hashes = set()

        # Prix
        self.prices = {'ETH': 3200, 'BTC': 98000}

        # Stats
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
        """Ajoute une transaction"""
        with self.lock:
            tx_hash = tx_data.get('hash', '')

            if not tx_hash or tx_hash in self.seen_hashes:
                return False

            self.seen_hashes.add(tx_hash)

            # Classification
            is_whale = tx_data['value'] >= WHALE_THRESHOLD.get(tx_data['chain'], 999999)
            tx_data['type'] = '🐋' if is_whale else '📊'

            # Ajout
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
        """Récupère les prix"""
        try:
            response = requests.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={'ids': 'bitcoin,ethereum', 'vs_currencies': 'usd'},
                timeout=5
            )
            data = response.json()
            self.prices['ETH'] = data.get('ethereum', {}).get('usd', 3200)
            self.prices['BTC'] = data.get('bitcoin', {}).get('usd', 98000)
            print(f"✅ Prix mis à jour: ETH ${self.prices['ETH']:,.0f} | BTC ${self.prices['BTC']:,.0f}")
        except Exception as e:
            print(f"⚠️ Erreur prix: {e}")

    def scan_etherscan_pending(self):
        """Scan les pending transactions Etherscan using web3-like approach"""
        print("🔍 Démarrage scan Etherscan pending...")

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
                    print(f"✅ {len(txs)} transactions dans le block {next_block}")

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

                time.sleep(10)  # Wait pour nouveau block (~12 sec)

            except requests.exceptions.RequestException as e:
                print(f"❌ Request error ({rpc_endpoints[current_endpoint_idx]}): {e}")
                current_endpoint_idx = (current_endpoint_idx + 1) % len(rpc_endpoints)
                self.stats['errors'] += 1
                time.sleep(5)
            except Exception as e:
                print(f"❌ Erreur Etherscan: {e}")
                self.stats['errors'] += 1
                time.sleep(5)

    def scan_bitcoin_mempool(self):
        """Scan Bitcoin mempool"""
        print("🔍 Démarrage scan Bitcoin mempool...")

        while self.running:
            try:
                # Blockstream API
                response = requests.get("https://blockstream.info/api/mempool/recent", timeout=5)
                txs = response.json()

                print(f"💰 {len(txs)} transactions BTC récupérées")

                for tx in txs[:50]:
                    try:
                        total_value = sum(vout.get('value', 0) for vout in tx.get('vout', []))
                        btc_value = total_value / 10 ** 8

                        if btc_value < 0.001:
                            continue

                        tx_data = {
                            'time': datetime.now().strftime('%H:%M:%S'),
                            'chain': 'BTC',
                            'from': f"{len(tx.get('vin', []))} inputs",
                            'to': f"{len(tx.get('vout', []))} outputs",
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
                print(f"❌ Erreur Bitcoin: {e}")
                self.stats['errors'] += 1
                time.sleep(5)

    def scan_blockchain_info(self):
        """Scan blockchain.info (source alternative)"""
        print("🔍 Démarrage scan Blockchain.info...")

        while self.running:
            try:
                response = requests.get(
                    "https://blockchain.info/unconfirmed-transactions?format=json",
                    timeout=5
                )
                data = response.json()

                txs = data.get('txs', [])
                print(f"🌐 {len(txs)} TX blockchain.info")

                for tx in txs[:30]:
                    try:
                        btc_value = sum(out.get('value', 0) for out in tx.get('out', [])) / 10 ** 8

                        if btc_value < 0.001:
                            continue

                        tx_data = {
                            'time': datetime.now().strftime('%H:%M:%S'),
                            'chain': 'BTC',
                            'from': 'Multiple',
                            'to': 'Multiple',
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
                print(f"❌ Erreur Blockchain.info: {e}")
                self.stats['errors'] += 1
                time.sleep(10)

    def display_dashboard(self):
        """Dashboard avec debug"""
        print("🖥️  Démarrage dashboard...")
        time.sleep(5)  # Attend un peu avant d'afficher

        while self.running:
            try:
                os.system('clear' if os.name == 'posix' else 'cls')

                print("╔" + "═" * 148 + "╗")
                print("║" + " ⚡ ULTRA BLOCKCHAIN TRACKER - LIVE ⚡ ".center(148) + "║")
                print("╚" + "═" * 148 + "╝")
                print()

                # Stats
                elapsed = (datetime.now() - self.last_update).total_seconds()
                status = "🟢 ACTIF" if elapsed < 30 else "🟡 ATTENTE"

                print(f"💰 ETH: ${self.prices['ETH']:,.0f} | BTC: ${self.prices['BTC']:,.0f}")
                print(
                    f"📊 Total: {self.stats['total_tx']} TX | 🐋 Whales: {self.stats['whales']} | 📊 Normal: {self.stats['normal']} | {status}")
                print(
                    f"📈 Vol: ETH {self.stats['eth_vol']:.2f} | BTC {self.stats['btc_vol']:.4f} | ❌ Erreurs: {self.stats['errors']}")
                print(f"⚙️  Seuils: ETH ≥{WHALE_THRESHOLD['ETH']} | BTC ≥{WHALE_THRESHOLD['BTC']}")
                print(f"🕐 Dernière TX: il y a {elapsed:.0f}s")
                print()

                # FLUX LIVE
                print("⚡" + "═" * 147 + "⚡")
                print(" TOUTES LES TRANSACTIONS (40 dernières)".center(149))
                print("⚡" + "═" * 147 + "⚡")

                with self.lock:
                    recent = list(self.all_transactions)[-40:]

                if recent:
                    data = [{
                        'T': tx['type'],
                        'Heure': tx['time'],
                        'Chain': tx['chain'],
                        'De': tx['from'][:12] + '..',
                        'Vers': tx['to'][:12] + '..',
                        'Montant': f"{tx['value']:.6f}",
                        'USD': f"${tx['usd']:,.0f}",
                        'Hash': tx['hash'][:12] + '..'
                    } for tx in recent]

                    df = pd.DataFrame(data)
                    print(df.to_string(index=False))
                else:
                    print("⏳ En attente de transactions...".center(149))
                    print("   (Ça peut prendre 10-30 secondes au démarrage)".center(149))

                print()

                # WHALES
                print("🐋" + "═" * 147 + "🐋")
                print(f" WHALES (ETH ≥{WHALE_THRESHOLD['ETH']} | BTC ≥{WHALE_THRESHOLD['BTC']})".center(149))
                print("🐋" + "═" * 147 + "🐋")

                with self.lock:
                    whales = list(self.whale_transactions)[-20:]

                if whales:
                    data = [{
                        'Heure': tx['time'],
                        'Chain': tx['chain'],
                        'De': tx['from'][:12] + '..',
                        'Vers': tx['to'][:12] + '..',
                        'Montant': f"{tx['value']:.6f}",
                        'USD': f"${tx['usd']:,.0f}",
                        'Hash': tx['hash'][:12] + '..'
                    } for tx in whales]

                    df = pd.DataFrame(data)
                    print(df.to_string(index=False))
                else:
                    print("⏳ Aucune whale détectée pour le moment...".center(149))

                print()
                print("─" * 150)
                print(f"🕐 {datetime.now().strftime('%H:%M:%S')} | Refresh: 3 sec | Ctrl+C = Stop")
                print("─" * 150)

                time.sleep(3)

            except Exception as e:
                print(f"❌ Erreur dashboard: {e}")
                time.sleep(3)

    def run(self):
        """Lance tout"""
        print("\n" + "═" * 150)
        print("⚡ ULTRA BLOCKCHAIN TRACKER".center(150))
        print("═" * 150)
        print()

        if not self.eth_api_key:
            print("⚠️  Pas de clé Etherscan!")
            return

        print(f"✅ Clé: {self.eth_api_key[:10]}...")
        print()

        # Get prix
        print("📊 Chargement des prix...")
        self.get_prices()
        print()

        print("🚀 Lancement des scanners...")
        print("   • Etherscan (blocks)")
        print("   • Bitcoin Blockstream")
        print("   • Bitcoin Blockchain.info")
        print("   • Dashboard")
        print()
        print("⏳ Les premières transactions arrivent dans 10-30 secondes...")
        print()

        # Lance threads
        threads = [
            threading.Thread(target=self.scan_etherscan_pending, daemon=True),
            threading.Thread(target=self.scan_bitcoin_mempool, daemon=True),
            threading.Thread(target=self.scan_blockchain_info, daemon=True),
            threading.Thread(target=self.display_dashboard, daemon=True)
        ]

        for t in threads:
            t.start()

        # Main loop avec update prix
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
        print("❌ ERREUR: Configure ETHERSCAN_API_KEY!")
        exit(1)

    print(f"✅ Clé: {ETHERSCAN_API_KEY[:10]}...{ETHERSCAN_API_KEY[-4:]}")
    print(f"\n⚙️  Seuils: ETH ≥{WHALE_THRESHOLD['ETH']} | BTC ≥{WHALE_THRESHOLD['BTC']}")
    print("\n💡 TIPS:")
    print("   • Attends 10-30 sec pour les premières TX")
    print("   • Les messages de debug s'affichent en temps réel")
    print("   • Le dashboard se lance après 5 secondes")
    print()

    input("▶️  ENTRÉE pour lancer...\n")

    tracker = UltraBlockchainTracker(eth_api_key=ETHERSCAN_API_KEY)
    tracker.run()