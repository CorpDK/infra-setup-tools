#!/bin/bash

if [[ "$1" == "routable" ]]; then
  echo "Network is now routable!"
  systemctl start corpdk-update-ddns.service
fi
