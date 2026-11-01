# SPDX-License-Identifier: GPL-3.0-or-later
# Image de production de Mail Accounts API (issue #10).
# Versions figées (SOCLE.md « Environnement ») : base Python 3.12.8 slim
# bookworm ; dépendances exclusivement celles de requirements.txt.

FROM python:3.12.8-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Utilisateur dédié non privilégié : l'API n'a besoin d'aucun droit root,
# les écritures se font uniquement dans le répertoire des comptes monté.
RUN groupadd --gid 9000 mailapi \
    && useradd --uid 9000 --gid mailapi --create-home mailapi

WORKDIR /app

# Dépendances d'abord (couche réutilisée tant que requirements.txt ne bouge pas).
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Code applicatif uniquement : ni .env (secret), ni tests, ni CI.
COPY api.py storage.py manage_accounts.py run.py webui.py /app/
# Interface web (issue #9) : page et ressources statiques.
COPY ui /app/ui

# Le fichier des comptes est monté par l'opérateur ; il doit rester absent
# de l'image. MAIL_API_KEY n'a jamais de valeur par défaut : elle est
# fournie à l'exécution.
ENV MAIL_API_HOST=0.0.0.0 \
    MAIL_API_PORT=9941 \
    MAIL_ACCOUNTS_FILE=/app/12-mail/config/postfix-accounts.cf

USER mailapi

EXPOSE 9941

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:9941/health', timeout=2).status == 200 else 1)"

CMD ["python", "run.py"]
