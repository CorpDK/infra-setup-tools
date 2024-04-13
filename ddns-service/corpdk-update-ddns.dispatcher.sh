#!/bin/bash

# Get the interface name
INTERFACE=$1
# Get the reason for the script being called (up, down, etc.)
ACTION=$2

echo "CorpDK update DDNS Check: ${INTERFACE} -> ${ACTION}"

# dhcp6-change
if [[ "${ACTION}" == "dhcp6-change" ]]; then
    systemctl start corpdk-update-ddns.service
fi
