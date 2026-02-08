# Lounge Coin — Implementation Guide

Complete guide for testing locally and deploying to production at **loungecoin.trade**.

---

## Table of Contents

1. [Local Development Setup](#1-local-development-setup)
2. [Running Tests](#2-running-tests)
3. [Google OAuth Setup](#3-google-oauth-setup)
4. [Custom Font Setup](#4-custom-font-setup)
5. [Server Provisioning (DigitalOcean)](#5-server-provisioning-digitalocean)
6. [DNS Configuration (Namecheap)](#6-dns-configuration-namecheap)
7. [Application Deployment](#7-application-deployment)
8. [SSL Certificate (Let's Encrypt)](#8-ssl-certificate-lets-encrypt)
9. [Nginx Configuration](#9-nginx-configuration)
10. [systemd Services](#10-systemd-services)
11. [GitHub Actions CI/CD](#11-github-actions-cicd)
12. [Post-Deployment Verification](#12-post-deployment-verification)
13. [Maintenance & Operations](#13-maintenance--operations)
14. [Troubleshooting](#14-troubleshooting)

---

## 1. Local Development Setup

### Prerequisites

- Python 3.12
- Node.js 20+ (for Tailwind CSS build)
- Git

### Initial Setup

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/loungecoin.git
cd loungecoin

# Create and activate virtual environment
python3.12 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Install Node dependencies (Tailwind CSS)
npm install

# Build Tailwind CSS
npm run build:css
```

### Environment Configuration

```bash
# Copy the example env file
cp .env.example .env
```

Edit `.env` with your values:

```
DJANGO_SECRET_KEY=any-random-string-for-dev
DJANGO_SETTINGS_MODULE=config.settings.development
USE_SQLITE=true
```

Setting `USE_SQLITE=true` lets you develop without PostgreSQL. For production or if you prefer PostgreSQL locally, set it to `false` and configure the `DB_*` variables.

### Database Setup

```bash
# Run migrations
python manage.py migrate

# Create a superuser (for Django admin panel)
python manage.py createsuperuser
```

### Running the Development Server

```bash
# Standard HTTP server (most development)
python manage.py runserver

# If testing WebSocket features (coin flip game), use Daphne instead:
daphne -b 127.0.0.1 -p 8000 config.asgi:application
```

The app will be available at `http://127.0.0.1:8000/`.

### Tailwind CSS Development

In a separate terminal, run the Tailwind watcher to auto-rebuild CSS on template changes:

```bash
npm run watch:css
```

### Making a User an Admin

Admins can mint coins and access the mint page at `/economy/mint/`.

```bash
# Via management command
python manage.py makeadmin <username>

# Or via Django admin panel at /admin/
# Edit the user's UserProfile and check "is_admin_user"
```

### Key URLs

| URL | Description |
|-----|-------------|
| `/` | Landing page |
| `/accounts/signup/` | Registration |
| `/accounts/login/` | Login |
| `/profile/` | User profile (balance, history, settings) |
| `/economy/trade/` | Send coins to another user |
| `/economy/mint/` | Mint coins (admin only) |
| `/economy/history/` | Transaction history |
| `/games/` | Coin flip game lobby |
| `/leaderboard/` | User rankings by balance |
| `/notifications/` | Notification list |
| `/admin/` | Django admin panel |

---

## 2. Running Tests

### Run All Tests

```bash
python manage.py test
```

This runs 56 tests across all apps. Expected output:

```
Found 56 test(s).
........................................................
Ran 56 tests in ~25s
OK
```

### Run Tests for a Specific App

```bash
python manage.py test apps.accounts
python manage.py test apps.economy
python manage.py test apps.games
python manage.py test apps.notifications
python manage.py test apps.leaderboard
```

### What the Tests Cover

**accounts (14 tests)**
- UserProfile auto-creation on signup
- Profile page access (authenticated vs anonymous)
- Profile editing (display name, avatar)
- Display name change cooldown (1-day enforcement)
- Dark mode toggle
- User search endpoint
- Landing page access

**economy (13 tests)**
- Coin transfer between users (valid transfer, insufficient funds)
- Trade view (GET form, POST submission, overdraft rejection)
- Mint view (admin access, non-admin 403 rejection)
- Transaction history display

**games (13 tests)**
- Game challenge creation (valid, invalid choice, self-challenge, duplicate prevention)
- Challenge with insufficient balance
- Lobby page access (authenticated vs anonymous)

**notifications (10 tests)**
- Notification creation and display
- Mark single notification as read (POST required)
- Mark all notifications as read (POST required)
- GET requests rejected for mark-read endpoints
- Cross-user notification security (can't mark others' notifications)
- Notification badge count

**leaderboard (3 tests)**
- Leaderboard page access
- Users displayed with balances
- Correct ordering by balance (highest first)

### Testing with PostgreSQL

If you want to test against PostgreSQL (closer to production):

```bash
# Set USE_SQLITE=false in .env and configure DB_* variables, then:
python manage.py test
```

---

## 3. Google OAuth Setup

### Create Google OAuth Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select existing)
3. Navigate to **APIs & Services > Credentials**
4. Click **Create Credentials > OAuth 2.0 Client ID**
5. Application type: **Web application**
6. Add authorized redirect URIs:
   - Development: `http://127.0.0.1:8000/accounts/google/login/callback/`
   - Production: `https://loungecoin.trade/accounts/google/login/callback/`
7. Copy the **Client ID** and **Client Secret**

### Configure in Django

Add to your `.env` file:

```
GOOGLE_CLIENT_ID=your-client-id-here
GOOGLE_CLIENT_SECRET=your-client-secret-here
```

### Set Up the Site in Django Admin

1. Go to `/admin/` and log in as superuser
2. Navigate to **Sites** and edit the default site:
   - Domain name: `loungecoin.trade` (production) or `127.0.0.1:8000` (development)
   - Display name: `Lounge Coin`
3. Navigate to **Social applications** > **Add**:
   - Provider: Google
   - Name: Google
   - Client ID: (paste from above)
   - Secret key: (paste from above)
   - Sites: Move your site to "Chosen sites"

The Google sign-in button will automatically appear on the login and signup pages once a social provider is configured.

---

## 4. Custom Font Setup

The design uses **URW Venus Light**. Place font files in `static/fonts/`:

```
static/fonts/urw-venus-light.woff2
static/fonts/urw-venus-light.woff
```

The font is loaded in `static/css/input.css` via `@font-face`. If you don't have the font files, the app falls back to the system sans-serif stack and works fine without them.

---

## 5. Server Provisioning (DigitalOcean)

### Create the Droplet

1. Log into [DigitalOcean](https://cloud.digitalocean.com/)
2. **Create > Droplets**
3. Choose:
   - **Image**: Ubuntu 22.04 LTS
   - **Plan**: Basic, $6/mo (1GB RAM, 25GB disk)
   - **Region**: Choose closest to your users
   - **Authentication**: SSH key (add your public key)
4. Click **Create Droplet** and note the IP address

### Initial Server Hardening

SSH into your droplet as root:

```bash
ssh root@YOUR_DROPLET_IP
```

Run these commands:

```bash
# Create deploy user
adduser deploy
usermod -aG sudo deploy

# Set up SSH for deploy user
mkdir -p /home/deploy/.ssh
cp ~/.ssh/authorized_keys /home/deploy/.ssh/
chown -R deploy:deploy /home/deploy/.ssh
chmod 700 /home/deploy/.ssh
chmod 600 /home/deploy/.ssh/authorized_keys

# Disable root login and password auth
sed -i 's/PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart sshd

# Enable firewall
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw enable

# Install fail2ban
apt update && apt install -y fail2ban
systemctl enable fail2ban

# Add 1GB swap
fallocate -l 1G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

Log out and reconnect as the deploy user:

```bash
ssh deploy@YOUR_DROPLET_IP
```

### Install System Dependencies

```bash
sudo apt update && sudo apt install -y \
    python3.12 python3.12-venv python3.12-dev \
    postgresql postgresql-contrib \
    nginx certbot python3-certbot-nginx \
    git curl

# Install Node.js 20
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

### Set Up PostgreSQL

```bash
sudo -u postgres psql <<EOF
CREATE USER loungecoin WITH PASSWORD 'CHOOSE_A_STRONG_PASSWORD';
CREATE DATABASE loungecoin OWNER loungecoin;
GRANT ALL PRIVILEGES ON DATABASE loungecoin TO loungecoin;
EOF
```

Remember this password — you'll put it in the `.env` file.

---

## 6. DNS Configuration (Namecheap)

### Point Namecheap to DigitalOcean

1. Log into [Namecheap](https://www.namecheap.com/)
2. Go to **Domain List** > click **Manage** on `loungecoin.trade`
3. Under **Nameservers**, select **Custom DNS**
4. Enter:
   ```
   ns1.digitalocean.com
   ns2.digitalocean.com
   ns3.digitalocean.com
   ```
5. Click the green checkmark to save

### Add Domain in DigitalOcean

1. In DigitalOcean dashboard, go to **Networking > Domains**
2. Add domain: `loungecoin.trade`
3. Create DNS records:
   - **A record**: Hostname `@`, Value: your droplet IP
   - **CNAME record**: Hostname `www`, Value: `@`

DNS propagation can take minutes to 24 hours. Test with:

```bash
dig loungecoin.trade +short
# Should return your droplet's IP
```

---

## 7. Application Deployment

SSH into your server as the deploy user:

```bash
ssh deploy@YOUR_DROPLET_IP
```

### Clone and Set Up the Application

```bash
# Clone repository
sudo mkdir -p /var/www/loungecoin
sudo chown deploy:www-data /var/www/loungecoin
git clone https://github.com/YOUR_USERNAME/loungecoin.git /var/www/loungecoin
cd /var/www/loungecoin

# Create virtual environment
python3.12 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
npm ci

# Build CSS
npm run build:css
```

### Configure Environment

```bash
cp .env.example .env
nano .env
```

Set production values:

```
DJANGO_SECRET_KEY=GENERATE_A_LONG_RANDOM_STRING
DJANGO_SETTINGS_MODULE=config.settings.production
DB_NAME=loungecoin
DB_USER=loungecoin
DB_PASSWORD=YOUR_POSTGRESQL_PASSWORD
DB_HOST=localhost
DB_PORT=5432
ALLOWED_HOSTS=loungecoin.trade
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
```

Generate a secret key:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### Initialize the Database

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
```

### Create Media Directory

```bash
mkdir -p /var/www/loungecoin/media/avatars
sudo chown -R deploy:www-data /var/www/loungecoin/media
chmod -R 775 /var/www/loungecoin/media
```

---

## 8. SSL Certificate (Let's Encrypt)

Before running Certbot, set up a minimal Nginx config so it can verify domain ownership:

```bash
sudo nano /etc/nginx/sites-available/loungecoin
```

Paste this temporary config:

```nginx
server {
    listen 80;
    server_name loungecoin.trade www.loungecoin.trade;

    location / {
        proxy_pass http://unix:/var/www/loungecoin/gunicorn.sock;
        proxy_set_header Host $host;
    }
}
```

Enable it:

```bash
sudo ln -s /etc/nginx/sites-available/loungecoin /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

Now run Certbot:

```bash
sudo certbot --nginx -d loungecoin.trade -d www.loungecoin.trade
```

Follow the prompts. Certbot will obtain the certificate and modify the Nginx config. After this succeeds, replace the Nginx config with the full production version (next section).

---

## 9. Nginx Configuration

Replace the Nginx config with the full production version:

```bash
sudo cp /var/www/loungecoin/deployment/nginx/loungecoin.conf /etc/nginx/sites-available/loungecoin
```

Verify the SSL certificate paths in the file match what Certbot created (they should if your domain is `loungecoin.trade`):

```bash
sudo nginx -t
```

If the test passes:

```bash
sudo systemctl reload nginx
```

### What the Nginx Config Does

- Redirects all HTTP (port 80) to HTTPS (port 443)
- Serves static files directly from `/var/www/loungecoin/staticfiles/` with 30-day cache
- Serves media files from `/var/www/loungecoin/media/` with 7-day cache
- Proxies `/ws/` requests to Daphne (port 8001) with WebSocket upgrade headers
- Proxies all other requests to Gunicorn via Unix socket
- Limits upload size to 5MB

---

## 10. systemd Services

### Install the Service Files

```bash
sudo cp /var/www/loungecoin/deployment/systemd/gunicorn.service /etc/systemd/system/
sudo cp /var/www/loungecoin/deployment/systemd/daphne.service /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable gunicorn daphne
sudo systemctl start gunicorn daphne
```

### Verify Services Are Running

```bash
sudo systemctl status gunicorn
sudo systemctl status daphne
```

Both should show `active (running)`.

### Service Architecture

```
Internet
  │
  ▼
Nginx (port 80/443)
  ├── /static/  →  filesystem (staticfiles/)
  ├── /media/   →  filesystem (media/)
  ├── /ws/      →  Daphne (127.0.0.1:8001) — WebSocket connections
  └── /         →  Gunicorn (unix socket) — HTTP requests
```

- **Gunicorn** (2 workers): Handles all regular HTTP requests via the WSGI interface
- **Daphne**: Handles WebSocket connections for the real-time coin flip game via the ASGI interface

### Allow Deploy User to Restart Services

For CI/CD to work, the deploy user needs passwordless sudo for service restarts:

```bash
sudo visudo -f /etc/sudoers.d/deploy
```

Add:

```
deploy ALL=(ALL) NOPASSWD: /bin/systemctl restart gunicorn, /bin/systemctl restart daphne
```

---

## 11. GitHub Actions CI/CD

### How It Works

Every push to the `main` branch triggers:

1. **Test job**: Spins up PostgreSQL, installs dependencies, builds CSS, runs all 56 tests
2. **Deploy job** (only if tests pass): SSHes into your server, pulls code, installs dependencies, runs migrations, collects static files, restarts services

### Set Up GitHub Secrets

In your GitHub repository, go to **Settings > Secrets and variables > Actions** and add:

| Secret | Value |
|--------|-------|
| `DO_SERVER_IP` | Your droplet's IP address |
| `DO_USER` | `deploy` |
| `SSH_PRIVATE_KEY` | Contents of your private SSH key (the one whose public key is on the server) |

To get your SSH private key:

```bash
# On your LOCAL machine
cat ~/.ssh/id_ed25519
# (or id_rsa, whichever you used)
```

Copy the entire output including the `-----BEGIN` and `-----END` lines.

### Initialize the Git Repository

```bash
cd /path/to/loungecoin   # your local project directory

git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/loungecoin.git
git branch -M main
git push -u origin main
```

This first push will trigger CI/CD. Make sure your server is set up first (Sections 5-10).

### Manual Deployment (Without CI/CD)

If you need to deploy manually:

```bash
ssh deploy@YOUR_DROPLET_IP
cd /var/www/loungecoin
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
npm ci
npm run build:css
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart gunicorn
sudo systemctl restart daphne
```

---

## 12. Post-Deployment Verification

After deploying, verify everything works:

### Basic Checks

```bash
# On the server
sudo systemctl status gunicorn    # Should be active
sudo systemctl status daphne      # Should be active
sudo systemctl status nginx       # Should be active

# Check for errors
sudo journalctl -u gunicorn --since "5 minutes ago"
sudo journalctl -u daphne --since "5 minutes ago"
```

### Functional Verification

Open `https://loungecoin.trade` in your browser and test:

1. **Landing page loads** — styled correctly with gold accents
2. **Sign up** — create a new account at `/accounts/signup/`
3. **Log in / log out** — verify session works
4. **Profile page** — shows balance of 0, edit display name
5. **Admin minting** — log in as admin, go to `/economy/mint/`, mint coins to a user
6. **Trading** — log in as a user with coins, go to `/economy/trade/`, send coins to another user
7. **Leaderboard** — `/leaderboard/` shows users ranked by balance
8. **Notifications** — check that coin receipt creates a notification
9. **Coin flip game** — open `/games/` in two browser windows (two different users), create a challenge from one, accept from the other
10. **Dark mode** — toggle via profile settings, verify all pages render correctly
11. **Mobile** — resize browser or test on phone, check responsive layout
12. **Google OAuth** (if configured) — test "Continue with Google" button on login/signup

### SSL Verification

```bash
# Test SSL grade
curl -I https://loungecoin.trade
# Should show HTTP/2 200 with Strict-Transport-Security header
```

You can also check at [SSL Labs](https://www.ssllabs.com/ssltest/) — should score A or A+.

---

## 13. Maintenance & Operations

### Expire Old Game Challenges

Pending challenges older than 24 hours should be expired. Run manually or set up a cron job:

```bash
# Manual
cd /var/www/loungecoin
source venv/bin/activate
python manage.py expire_challenges

# Cron job (runs daily at 3am)
crontab -e
# Add:
0 3 * * * cd /var/www/loungecoin && /var/www/loungecoin/venv/bin/python manage.py expire_challenges
```

### View Logs

```bash
# Gunicorn logs
sudo journalctl -u gunicorn -f

# Daphne logs (WebSocket)
sudo journalctl -u daphne -f

# Nginx access/error logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### Database Backup

```bash
# Backup
sudo -u postgres pg_dump loungecoin > /home/deploy/backups/loungecoin_$(date +%Y%m%d).sql

# Restore
sudo -u postgres psql loungecoin < /home/deploy/backups/loungecoin_YYYYMMDD.sql
```

Set up automated backups:

```bash
mkdir -p /home/deploy/backups
crontab -e
# Add (daily at 2am, keep 14 days):
0 2 * * * sudo -u postgres pg_dump loungecoin > /home/deploy/backups/loungecoin_$(date +\%Y\%m\%d).sql && find /home/deploy/backups -name "*.sql" -mtime +14 -delete
```

### SSL Certificate Renewal

Certbot auto-renews via a systemd timer. Verify it's active:

```bash
sudo systemctl status certbot.timer
```

Test renewal:

```bash
sudo certbot renew --dry-run
```

### Monitoring Memory Usage

With 1GB RAM, keep an eye on usage:

```bash
free -h
```

Expected:

```
PostgreSQL:           ~100MB
Gunicorn (2 workers): ~200MB
Daphne:               ~80MB
Nginx:                ~20MB
OS + buffer:          ~250MB
Swap (safety net):    1GB on disk
Remaining:            ~374MB headroom
```

### Updating Dependencies

```bash
cd /var/www/loungecoin
source venv/bin/activate

# Update Python packages
pip install --upgrade -r requirements.txt

# Update Node packages
npm update

# Rebuild CSS after Node updates
npm run build:css

# Restart services
sudo systemctl restart gunicorn daphne
```

---

## 14. Troubleshooting

### "502 Bad Gateway" from Nginx

Gunicorn isn't running or the socket doesn't exist.

```bash
sudo systemctl status gunicorn
# If failed:
sudo journalctl -u gunicorn -n 50
# Common fix:
sudo systemctl restart gunicorn
```

### WebSocket Connection Fails

Daphne isn't running or Nginx isn't proxying `/ws/` correctly.

```bash
sudo systemctl status daphne
# Check Daphne is listening on port 8001:
ss -tlnp | grep 8001
```

### Static Files Not Loading (404s)

```bash
cd /var/www/loungecoin
source venv/bin/activate
python manage.py collectstatic --noinput
sudo systemctl restart nginx
```

### Database Connection Refused

```bash
sudo systemctl status postgresql
# If stopped:
sudo systemctl start postgresql
# Verify credentials:
psql -U loungecoin -h localhost -d loungecoin
```

### CSS Not Updating

Rebuild Tailwind and collect static:

```bash
cd /var/www/loungecoin
npm run build:css
source venv/bin/activate
python manage.py collectstatic --noinput
```

If using WhiteNoise's manifest storage, the filename hash changes on rebuild, so browser caching isn't an issue.

### "CSRF Verification Failed" on Forms

Ensure `CSRF_TRUSTED_ORIGINS` in `config/settings/production.py` includes your domain:

```python
CSRF_TRUSTED_ORIGINS = ['https://loungecoin.trade']
```

### Migration Errors After Pull

```bash
source venv/bin/activate
python manage.py showmigrations  # See what's pending
python manage.py migrate          # Apply them
```

### Server Ran Out of Memory

```bash
# Check swap usage
free -h

# If swap is full, identify the culprit
top -o %MEM

# Reduce Gunicorn workers if needed (edit the service file)
sudo systemctl edit gunicorn
# Override ExecStart with --workers 1
```

### Permission Errors on Media Uploads

```bash
sudo chown -R deploy:www-data /var/www/loungecoin/media
sudo chmod -R 775 /var/www/loungecoin/media
```
