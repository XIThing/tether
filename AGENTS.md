# Setup Instructions for AI Agents

Help the user set up and run Tether.

## Prerequisites

- Python 3.10+
- Node.js 20+
- Git

## Setup

```bash
# Clone the repository
git clone https://github.com/XIThing/tether.git
cd tether

# Install dependencies
make install

# Start the agent
make start
```

## Verify

Run the verify script (checks both agent API and UI):

```bash
make verify
```

Or manually:
1. Open http://localhost:8787 in a browser
2. The Tether UI should load

## Phone Access

To access Tether from a phone on the same network:

1. Find the computer's IP address
2. Open the firewall port:

   **Linux (firewalld):**
   ```bash
   sudo firewall-cmd --add-port=8787/tcp --permanent && sudo firewall-cmd --reload
   ```

   **Linux (ufw):**
   ```bash
   sudo ufw allow 8787/tcp
   ```

   **macOS:**
   System Settings > Network > Firewall > Options > Allow incoming connections

3. Open `http://<computer-ip>:8787` on the phone

## Docker Alternative

If the user has trouble with Python/Node dependencies, Docker can be used as a backup:

```bash
make docker-start
```

**Important:** The Docker setup requires mapping host directories for the agent to access code repositories. Add volume mounts to `docker-compose.yml`:

```yaml
services:
  agent:
    volumes:
      - /path/to/repos:/path/to/repos
```

The native setup (`make start`) is recommended as it has direct file system access.

## Troubleshooting

If `make install` fails:
- Check Python version: `python --version` (needs 3.10+)
- Check Node version: `node --version` (needs 20+)

If `make start` fails:
- Check if port 8787 is in use: `lsof -i :8787`
- Check the error output for missing dependencies

## Next Steps

Once running, the user can:
- Access from phone: open `http://<computer-ip>:8787` on the same network
- See README.md for configuration options
- See CONTRIBUTING.md for development setup
