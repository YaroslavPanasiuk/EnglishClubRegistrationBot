docker build -t registration_bot .
docker run -v ./data:/app/data --sysctl net.ipv6.conf.all.disable_ipv6=1 registration_bot