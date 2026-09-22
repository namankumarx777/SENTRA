#!/usr/bin/env bash
set -euo pipefail

echo "============================================================"
echo " Starting SENTRA Hyperledger Fabric Local Permissioned Ledger"
echo "============================================================"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NETWORK_DIR="${SCRIPT_DIR}/../network"
CHAINCODE_DIR="${SCRIPT_DIR}/../chaincode/sat-sa-integrity"

export COMPOSE_PROJECT_NAME="SENTRA"
export CHANNEL_NAME="SENTRA-channel"
export CC_NAME="SENTRA-integrity"

if ! command -v docker &> /dev/null; then
    echo "[ERROR] Docker is not installed or not in PATH."
    exit 1
fi

echo "[1/4] Launching Fabric containers (Orderer + CSE-A Peer + CSE-B Peer)..."
docker compose -f "${NETWORK_DIR}/docker-compose-test-net.yaml" up -d

echo "[2/4] Waiting for Fabric peers to become ready..."
sleep 3

echo "[3/4] Building Go chaincode binary (${CC_NAME})..."
(cd "${CHAINCODE_DIR}" && go build -o "${CHAINCODE_DIR}/SENTRA-integrity" .)

echo "[4/4] Network started successfully."
echo "Channel: ${CHANNEL_NAME}"
echo "Chaincode: ${CC_NAME}"
echo "Orderer: localhost:7050"
echo "Peer 0 (CSE-A): localhost:7051"
echo "Peer 0 (CSE-B): localhost:9051"
