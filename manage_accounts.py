#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""Gestionnaire de comptes mail pour docker-mailserver.

Permet d'ajouter, modifier, supprimer et lister les comptes mail. Le mot de
passe généré est affiché une seule fois à la création (sortie standard,
comme la réponse de l'API) : il n'apparaît jamais dans les messages du
journal (SOCLE §8, règle 6).
"""

import hashlib
import secrets
import sys
from pathlib import Path

from loguru import logger

ACCOUNTS_FILE = "/app/12-mail/config/postfix-accounts.cf"


def sha512_hash(password: str) -> str:
    """Génère un hash SHA512 pour docker-mailserver"""
    return "{sha512}" + hashlib.sha512(password.encode()).hexdigest()


def generate_password(length: int = 16) -> str:
    """Génère un mot de passe sécurisé aléatoire"""
    return secrets.token_urlsafe(length)


def parse_accounts_file() -> list[dict[str, str]]:
    """Parse le fichier des comptes"""
    logger.debug("parse_accounts_file : entrée")
    accounts = []
    path = Path(ACCOUNTS_FILE)
    if not path.exists():
        logger.debug("parse_accounts_file : sortie (fichier absent, 0 compte)")
        return accounts

    with path.open("r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("|")
            if len(parts) >= 3:
                accounts.append({"email": parts[0], "hash": parts[1], "folder": parts[2]})
    logger.debug("parse_accounts_file : sortie ({} comptes)", len(accounts))
    return accounts


def write_accounts_file(accounts: list[dict[str, str]]) -> None:
    """Écrit les comptes dans le fichier"""
    logger.debug("write_accounts_file : entrée ({} comptes)", len(accounts))
    path = Path(ACCOUNTS_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for account in accounts:
            f.write(f"{account['email']}|{account['hash']}|{account['folder']}\n")
    logger.info("fichier des comptes mis à jour : {}", ACCOUNTS_FILE)


def list_accounts() -> None:
    """Liste tous les comptes mail"""
    logger.debug("list_accounts : entrée")
    accounts = parse_accounts_file()
    if not accounts:
        logger.warning("aucun compte trouvé")
        return

    print("\n📧 COMPTES MAIL")
    print("=" * 70)
    for i, acc in enumerate(accounts, 1):
        print(f"{i}. {acc['email']:<35} Dossier: {acc['folder']}")
    print("=" * 70)
    print(f"Total: {len(accounts)} compte(s)")
    logger.debug("list_accounts : sortie ({} comptes affichés)", len(accounts))


def add_account(email: str, password: str | None = None, auto_generate: bool = False) -> None:
    """Ajoute un nouveau compte mail"""
    logger.debug("add_account : entrée (email={}, mot de passe fourni={})", email, password is not None)
    accounts = parse_accounts_file()

    # Vérifier que le compte n'existe pas
    if any(acc["email"] == email for acc in accounts):
        logger.error("le compte {} existe déjà", email)
        return

    # Valider email
    if "@" not in email or "." not in email:
        logger.error("email invalide : {}", email)
        return

    # Générer le mot de passe si nécessaire
    if password is None:
        password = generate_password()
        auto_generate = True

    # Extraire la partie locale (avant @) pour le dossier
    folder = email.split("@")[0]

    # Créer le compte
    hash_pwd = sha512_hash(password)
    accounts.append({"email": email, "hash": hash_pwd, "folder": folder})

    write_accounts_file(accounts)

    logger.info("compte créé : {} (dossier {})", email, folder)
    # Sortie standard (et non journal) : le mot de passe n'est affiché qu'ici,
    # une seule fois, comme la réponse de l'API à la création.
    print(f"   Mot de passe: {password}")
    print(f"   Dossier: /var/mail/dmathilde.fr/{folder}/")

    if auto_generate:
        logger.warning("mot de passe généré automatiquement — conservez-le de manière sécurisée")
    logger.debug("add_account : sortie")


def modify_account(email: str, new_password: str) -> None:
    """Modifie le mot de passe d'un compte"""
    logger.debug("modify_account : entrée (email={})", email)
    accounts = parse_accounts_file()

    # Chercher le compte
    account = next((acc for acc in accounts if acc["email"] == email), None)
    if not account:
        logger.error("compte {} introuvable", email)
        return

    # Mettre à jour le mot de passe
    account["hash"] = sha512_hash(new_password)
    write_accounts_file(accounts)

    logger.info("mot de passe mis à jour pour {}", email)
    # Sortie standard : affichage unique du mot de passe, comme la création.
    print(f"   Nouveau mot de passe: {new_password}")
    logger.debug("modify_account : sortie")


def delete_account(email: str, confirm: bool = False) -> None:
    """Supprime un compte mail"""
    logger.debug("delete_account : entrée (email={}, confirm={})", email, confirm)
    accounts = parse_accounts_file()

    # Chercher le compte
    account = next((acc for acc in accounts if acc["email"] == email), None)
    if not account:
        logger.error("compte {} introuvable", email)
        return

    # Demander confirmation
    if not confirm:
        response = input(f"\n⚠️  Êtes-vous sûr de vouloir supprimer {email}? (oui/non): ").strip().lower()
        if response not in ["oui", "o", "yes", "y"]:
            logger.info("opération annulée par l'utilisateur")
            return

    # Supprimer le compte
    accounts = [acc for acc in accounts if acc["email"] != email]
    write_accounts_file(accounts)

    logger.info("compte {} supprimé", email)


def show_help() -> None:
    """Affiche l'aide"""
    logger.debug("show_help : entrée")
    print("""
╔════════════════════════════════════════════════════════════════════════╗
║         GESTIONNAIRE DE COMPTES MAIL - docker-mailserver               ║
╚════════════════════════════════════════════════════════════════════════╝

UTILISATION:
    python3 manage_accounts.py [COMMANDE] [OPTIONS]

COMMANDES:

  list                      Lister tous les comptes mail

  add EMAIL [PASSWORD]      Ajouter un nouveau compte
                            Si PASSWORD omis → génération automatique

  modify EMAIL PASSWORD     Modifier le mot de passe d'un compte

  delete EMAIL              Supprimer un compte (demande confirmation)

  help                      Afficher cette aide

EXEMPLES:

  # Lister les comptes
  python3 manage_accounts.py list

  # Ajouter un compte avec mot de passe auto-généré
  python3 manage_accounts.py add user@dmathilde.fr

  # Ajouter un compte avec mot de passe spécifique
  python3 manage_accounts.py add user@dmathilde.fr "MonMotDePasse123!"

  # Modifier le mot de passe
  python3 manage_accounts.py modify user@dmathilde.fr "NouveauMotDePasse456!"

  # Supprimer un compte
  python3 manage_accounts.py delete user@dmathilde.fr

APRÈS MODIFICATION:

  Redéployer le service mail:
    docker stack deploy -c docker-compose.yml 12
""")
    logger.debug("show_help : sortie")


def main() -> None:
    logger.debug("main : entrée (argv={})", sys.argv[1:])
    if len(sys.argv) < 2:
        show_help()
        logger.debug("main : sortie (aucune commande, aide affichée)")
        return

    command = sys.argv[1].lower()

    if command == "help":
        show_help()

    elif command == "list":
        list_accounts()

    elif command == "add":
        if len(sys.argv) < 3:
            logger.error("usage : python3 manage_accounts.py add EMAIL [PASSWORD]")
            sys.exit(1)
        email = sys.argv[2]
        password = sys.argv[3] if len(sys.argv) > 3 else None
        add_account(email, password)

    elif command == "adds":
        if len(sys.argv) < 6:
            logger.error("usage : python3 manage_accounts.py adds EMAIL [PASSWORD] START END")
            sys.exit(1)
        email, domaine = sys.argv[2].split("@")
        password = sys.argv[3] if len(sys.argv) > 3 else None
        for i in range(int(sys.argv[4]), int(sys.argv[5])):
            add_account(f"{email}{i}@{domaine}", password)

    elif command == "modify":
        if len(sys.argv) < 4:
            logger.error("usage : python3 manage_accounts.py modify EMAIL PASSWORD")
            sys.exit(1)
        email = sys.argv[2]
        password = sys.argv[3]
        modify_account(email, password)

    elif command == "delete":
        if len(sys.argv) < 3:
            logger.error("usage : python3 manage_accounts.py delete EMAIL")
            sys.exit(1)
        email = sys.argv[2]
        delete_account(email)

    else:
        logger.error("commande inconnue : {}", command)
        logger.info("tapez 'python3 manage_accounts.py help' pour l'aide")
        sys.exit(1)

    logger.debug("main : sortie (commande={})", command)


if __name__ == "__main__":
    main()
