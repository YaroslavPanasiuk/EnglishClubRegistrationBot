podman build -t registration_bot .
podman run -v ./data:/app/data --sysctl net.ipv6.conf.all.disable_ipv6=1 registration_bot