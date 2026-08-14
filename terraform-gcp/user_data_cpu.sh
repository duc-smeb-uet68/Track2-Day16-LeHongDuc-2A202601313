#!/bin/bash
set -euo pipefail

exec > >(tee /var/log/user-data.log | logger -t startup-script -s 2>/dev/console) 2>&1

echo "Starting startup script for CPU LightGBM benchmark node"

export DEBIAN_FRONTEND=noninteractive

for attempt in 1 2 3 4 5; do
  if apt-get update -y; then
    break
  fi
  if [ "$attempt" -eq 5 ]; then
    echo "apt-get update failed after 5 attempts" >&2
    exit 1
  fi
  sleep 15
done

apt-get install -y python3 python3-pip libgomp1 procps iproute2

# Debian 12 marks the system Python as externally managed (PEP 668);
# --break-system-packages is required for a system-wide pip install here.
python3 -m pip install --break-system-packages --retries 10 --timeout 60 --upgrade pip
python3 -m pip install --break-system-packages --retries 10 --timeout 60 \
  lightgbm scikit-learn pandas numpy kaggle

python3 -c "import lightgbm, sklearn, pandas, numpy; print('ML imports: OK')"
kaggle --version

echo "CPU environment ready: lightgbm, scikit-learn, pandas, numpy, kaggle installed system-wide."
