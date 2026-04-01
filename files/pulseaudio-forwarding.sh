# Forward audio streams to the remove Pulse server
# through the SSH tunnel

#   Pulse Client ---tcp---> localhost:24713 ---ssh---> 24713:SSH client

command -v ss >/dev/null || exit 0
if ss -tnl 2>/dev/null | grep -q ':24713\b'; then
    export PULSE_SERVER=tcp:localhost:24713
fi
