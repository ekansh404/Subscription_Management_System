# Deploying (free) on PythonAnywhere

PythonAnywhere's free plan suits this project: it runs Django directly, keeps the SQLite database on a
persistent disk, serves the static files itself, and does not sleep between visits. The address is
`https://<username>.pythonanywhere.com`. Replace `USERNAME` below with your PythonAnywhere username.

## 1. Get the code (PythonAnywhere → Consoles → Bash)

```bash
git clone https://github.com/ekansh404/Subscription_Management_System.git
cd Subscription_Management_System
python3.13 -m venv .venv          # any Python 3.12+ offered by your account works
source .venv/bin/activate
pip install -r requirements.txt
python -c "import secrets; print(secrets.token_urlsafe(50))"   # copy the output for DJANGO_SECRET_KEY
nano .env
```

Put this in `.env` (Ctrl+O, Enter, Ctrl+X to save):

```
DJANGO_SECRET_KEY=<the value printed above>
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=USERNAME.pythonanywhere.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://USERNAME.pythonanywhere.com
EMAIL_BACKEND=outbox
```

Then prepare the database and static files:

```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py seed_demo --reset
```

## 2. Create the web app (PythonAnywhere → Web)

1. **Add a new web app** → *Manual configuration* (not "Django") → the same Python version as above.
2. **Source code**: `/home/USERNAME/Subscription_Management_System`
3. **Virtualenv**: `/home/USERNAME/Subscription_Management_System/.venv`
4. **WSGI configuration file**: open it, delete everything, paste:

   ```python
   import os, sys
   path = "/home/USERNAME/Subscription_Management_System"
   if path not in sys.path:
       sys.path.insert(0, path)
   os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
   from django.core.wsgi import get_wsgi_application
   application = get_wsgi_application()
   ```

5. **Static files**: URL `/static/` → directory `/home/USERNAME/Subscription_Management_System/staticfiles`
6. **Force HTTPS**: enabled.
7. Click **Reload**, then open `https://USERNAME.pythonanywhere.com` and sign in as `admin@brightloop.com` / `Admin#12345`.

## Updating after new commits

```bash
cd ~/Subscription_Management_System && source .venv/bin/activate
git pull
python manage.py migrate
python manage.py collectstatic --noinput
```

Then **Reload** on the Web tab.

## Notes

* Free accounts can only reach whitelisted websites, so outgoing SMTP is not available: keep
  `EMAIL_BACKEND=outbox`; emails appear under **Email outbox** for administrators.
* Free web apps stay up for three months at a time; click *Run until 3 months from today* on the Web
  tab to extend.
* If sign-in says "CSRF verification failed", check `DJANGO_CSRF_TRUSTED_ORIGINS` (it must start with
  `https://`) and Reload.
* Error log: Web tab → *Log files* → error log.
