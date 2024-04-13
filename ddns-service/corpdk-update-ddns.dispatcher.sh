#!/bin/bash

# Get the interface name
INTERFACE=$1

# Get the reason for the script being called (up, down, etc.)
ACTION=$2

echo "CorpDK update DDNS Check: ${INTERFACE} -> ${ACTION}"
