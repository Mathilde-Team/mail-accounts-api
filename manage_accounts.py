#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gestionnaire de comptes mail pour docker-mailserver
Permet d'ajouter, modifier, supprimer et lister les comptes mail
"""

import hashlib
import os
import sys
import argparse
import secrets
from pathlib import Path
from typing import List, Dict, Tuple

ACCOUNTS_FILE = "/app/12-mail/config/postfix-accounts.cf"
DOCKER_CMD = "docker"
SWARM_MODE = True


def sha512_hash(password: str) -> str:
    """Génère un hash SHA512 pour docker-mailserver"""
    return "{sha512}" + hashlib.sha512(password.encode()).hexdigest()


def generate_password(length: int = 16) -> str:
    """Génère un mot de passe sécurisé aléatoire"""
    return secrets.token_urlsafe(length)


def parse_accounts_file() -> List[Dict[str, str]]:
    """Parse le fichier des comptes"""
    accounts = []
    if not os.path.exists(ACCOUNTS_FILE):
        return accounts

    with open(ACCOUNTS_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("|")
            if len(parts) >= 3:
                accounts.append({"email": parts[0], "hash": parts[1], "folder": parts[2]})
    return accounts


def write_accounts_file(accounts: List[Dict[str, str]]) -> None:
    """Écrit les comptes dans le fichier"""
    os.makedirs(os.path.dirname(ACCOUNTS_FILE), exist_ok=True)
    with open(ACCOUNTS_FILE, "w") as f:
        for account in accounts:
            f.write(f"{account['email']}|{account['hash']}|{account['folder']}\n")
    print(f"✅ Fichier des comptes mis à jour: {ACCOUNTS_FILE}")


def list_accounts() -> None:
    """Liste tous les comptes mail"""
    accounts = parse_accounts_file()
    if not accounts:
        print("❌ Aucun compte trouvé")
        return

    print("\n📧 COMPTES MAIL")
    print("=" * 70)
    for i, acc in enumerate(accounts, 1):
        print(f"{i}. {acc['email']:<35} Dossier: {acc['folder']}")
    print("=" * 70)
    print(f"Total: {len(accounts)} compte(s)")


def add_account(email: str, password: str = None, auto_generate: bool = False) -> None:
    """Ajoute un nouveau compte mail"""
    accounts = parse_accounts_file()

    # Vérifier que le compte n'existe pas
    if any(acc["email"] == email for acc in accounts):
        print(f"❌ Le compte {email} existe déjà!")
        return

    # Valider email
    if "@" not in email or "." not in email:
        print(f"❌ Email invalide: {email}")
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

    print(f"\n✅ Compte créé avec succès!")
    print(f"   Email: {email}")
    print(f"   Mot de passe: {password}")
    print(f"   Dossier: /var/mail/dmathilde.fr/{folder}/")

    if auto_generate:
        print("\n⚠️  Mot de passe généré automatiquement - conservez-le de manière sécurisée!")


def modify_account(email: str, new_password: str) -> None:
    """Modifie le mot de passe d'un compte"""
    accounts = parse_accounts_file()

    # Chercher le compte
    account = next((acc for acc in accounts if acc["email"] == email), None)
    if not account:
        print(f"❌ Compte {email} introuvable!")
        return

    # Mettre à jour le mot de passe
    account["hash"] = sha512_hash(new_password)
    write_accounts_file(accounts)

    print(f"✅ Mot de passe mis à jour pour {email}")
    print(f"   Nouveau mot de passe: {new_password}")


def delete_account(email: str, confirm: bool = False) -> None:
    """Supprime un compte mail"""
    accounts = parse_accounts_file()

    # Chercher le compte
    account = next((acc for acc in accounts if acc["email"] == email), None)
    if not account:
        print(f"❌ Compte {email} introuvable!")
        return

    # Demander confirmation
    if not confirm:
        response = input(f"\n⚠️  Êtes-vous sûr de vouloir supprimer {email}? (oui/non): ").strip().lower()
        if response not in ["oui", "o", "yes", "y"]:
            print("❌ Opération annulée")
            return

    # Supprimer le compte
    accounts = [acc for acc in accounts if acc["email"] != email]
    write_accounts_file(accounts)

    print(f"✅ Compte {email} supprimé")


def show_help() -> None:
    """Affiche l'aide"""
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


def main():
    if len(sys.argv) < 2:
        show_help()
        return

    command = sys.argv[1].lower()

    if command == "help":
        show_help()

    elif command == "list":
        list_accounts()

    elif command == "add":
        if len(sys.argv) < 3:
            print("❌ Usage: python3 manage_accounts.py add EMAIL [PASSWORD]")
            sys.exit(1)
        email = sys.argv[2]
        password = sys.argv[3] if len(sys.argv) > 3 else None
        add_account(email, password)

    elif command == "adds":
        if len(sys.argv) < 6:
            print("❌ Usage: python3 manage_accounts.py adds EMAIL [PASSWORD] START END")
            sys.exit(1)
        email, domaine = sys.argv[2].split("@")
        password = sys.argv[3] if len(sys.argv) > 3 else None
        for i in range(int(sys.argv[4]), int(sys.argv[5])):
            add_account(f"{email}{i}@{domaine}", password)

    elif command == "modify":
        if len(sys.argv) < 4:
            print("❌ Usage: python3 manage_accounts.py modify EMAIL PASSWORD")
            sys.exit(1)
        email = sys.argv[2]
        password = sys.argv[3]
        modify_account(email, password)

    elif command == "delete":
        if len(sys.argv) < 3:
            print("❌ Usage: python3 manage_accounts.py delete EMAIL")
            sys.exit(1)
        email = sys.argv[2]
        delete_account(email)

    else:
        print(f"❌ Commande inconnue: {command}")
        print("Tapez 'python3 manage_accounts.py help' pour l'aide")
        sys.exit(1)


if __name__ == "__main__":
    main()
