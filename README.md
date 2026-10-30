# Mail Accounts API

API REST pour le gestionnaire `manage_accounts.py` de docker-mailserver.
L'API reutilise les fonctions de hash SHA512 et de generation de mots de passe
du CLI. Aucun compte reel, hash, certificat ou identifiant n'est inclus dans
ce depot.

## Socle qualite

Depot conforme au [socle qualite Mathilde-Team](https://github.com/Mathilde-Team/.github/blob/main/SOCLE.md) :
licence GPL-3.0-or-later, branches `main` (livraison) et `dev` (integration),
protections versionnees dans `.github/branch-protection/`, journalisation
loguru (sections 7 et 8 du socle), couverture de tests >= 95 %.

```sh
uv sync
make test    # pytest + couverture (seuil lu dans pyproject.toml)
make lint    # ruff check + ruff format --check
```

## Installation

Python 3.10+ sur Linux (verrouillage POSIX).

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
chmod 600 .env
```

Renseigner `MAIL_API_KEY` dans `.env` avec une cle aleatoire d'au moins
32 caracteres, par exemple generee par `secrets.token_urlsafe(48)`.
Ne jamais versionner ce fichier. `MAIL_ACCOUNTS_FILE` doit pointer sur le
fichier **existant** de docker-mailserver. Un fichier absent ou malforme
provoque une erreur 503, jamais la creation silencieuse d'un fichier vide.

```sh
.venv/bin/python run.py
```

Par defaut, sans configuration d'hote, l'ecoute est sur `127.0.0.1:9941`.
Le modele `.env.example` active explicitement `0.0.0.0` pour un reseau local.
Le port occupe provoque un echec visible : aucun autre port n'est choisi
silencieusement.

## Authentification et routes

Toutes les routes `/accounts` demandent `Authorization: Bearer <MAIL_API_KEY>`.
La cle ne doit pas etre passee dans l'URL. `/health`, `/docs` et `/openapi.json`
sont publics et ne revelent ni comptes ni secrets. Swagger permet de saisir
la cle via **Authorize**.

| Methode | Route | Action |
|---|---|---|
| GET | `/health` | Etat du processus, sans verification du stockage |
| GET | `/accounts` | Liste `{accounts: [{email, folder}], total}` |
| GET | `/accounts/{email}` | Lire un compte |
| POST | `/accounts` | Creer avec `{email, password?}` |
| POST | `/accounts/batch` | Creer atomiquement `{accounts: [{email, password?}, ...]}`, 1 a 100 comptes |
| POST | `/accounts/numbered` | Commande `adds` : `{email, password?, start, end}` ; fin exclusive, 1 a 100 comptes |
| PATCH | `/accounts/{email}` | Changer le mot de passe avec `{password}` |
| DELETE | `/accounts/{email}` | Supprimer le compte du fichier, reponse 204 |

Un mot de passe omis (ou `null`) a la creation est genere et renvoye
**uniquement dans la reponse de creation**. Un mot de passe fourni n'est jamais
renvoye. Les hashes ne sont jamais exposes par l'API. Les erreurs de validation
ne renvoient pas les valeurs d'entree. Les journaux d'acces sont desactives.
Ne pas journaliser les corps ou en-tetes d'authentification dans un proxy.

Exemples (cle chargee dans la variable d'environnement du shell) :

```sh
curl -H "Authorization: Bearer $MAIL_API_KEY" http://127.0.0.1:9941/accounts
curl -X POST -H "Authorization: Bearer $MAIL_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"email":"user@example.org"}' http://127.0.0.1:9941/accounts
```

Codes : 201 creation, 204 suppression, 401 authentification, 404 compte absent,
409 doublon, 422 entree invalide, 503 erreur de stockage. Ne pas relancer
aveuglement une mutation apres une erreur d'E/S : relire l'etat auparavant.

L'equivalent de `manage_accounts.py adds user@example.org PASSWORD 1 4` est :

```json
{"email":"user@example.org","password":"PASSWORD","start":1,"end":4}
```

Il cree `user1`, `user2` et `user3` atomiquement. Sans mot de passe fourni,
chaque compte recoit son propre mot de passe genere. Les lots sont limites a
100 comptes par requete. La commande CLI `help` est remplacee par le Swagger
interactif `/docs`, ReDoc `/redoc` et le schema `/openapi.json`.
Une copie du schema genere est aussi fournie dans [openapi.json](./openapi.json).
Les fonctions internes de lecture/ecriture et de hash ne sont pas exposees :
elles passent par les routes metier pour ne pas divulguer les hashes.

La suppression ne supprime pas le contenu des boites mail. Le format existant
`email|{sha512}HASH|folder` reste compatible ; les commentaires, les champs
supplementaires, le proprietaire et les permissions sont preserves.
L'API valide les nouvelles adresses (syntaxe ASCII usuelle, domaine avec point).
Les ecritures sont atomiques et serialisees par verrou de fichier et de thread.
Ce verrou coordonne les instances de **cette API**, pas le script CLI historique :
ne pas executer ce dernier ou un autre editeur en ecriture pendant les mutations
API. Le fichier ne doit pas etre un lien symbolique.

## Service systemd sur docker45

Installateur fourni (a executer apres copie du depot sur docker45) :

```sh
sudo sh deploy/install.sh
```

Il verifie le port avant une premiere installation, installe le code, genere
une cle sans l'afficher et active le service. Lors d'une mise a jour, le `.env`
existant est conserve. Ne pas l'executer sur un autre service ou repertoire
preexistant sans en verifier l'origine.
Il utilise `/usr/bin/python3` et le paquet systeme `python3-venv`, pour que
`ProtectHome=true` ne bloque pas un interpreteur pyenv situe sous `/root`.
La mise a jour arrete brievement le service et recree son environnement virtuel
dedie, pour eviter de melanger deux installations Python.

Installer le code et son environnement virtuel dans `/opt/mail-accounts-api`.
Creer `/etc/mail-accounts-api` (root, mode 700), puis y installer `.env`
(root, mode 600) avec les valeurs de `.env.example` et une cle generee.
Le fichier `.env` est hors du depot. systemd le charge via `EnvironmentFile`.
Pour changer le chemin des comptes, adapter egalement `ReadWritePaths` et
`RequiresMountsFor` dans l'unite.

```sh
sudo install -m 644 deploy/mail-accounts-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mail-accounts-api
sudo systemctl status mail-accounts-api --no-pager
sudo journalctl -u mail-accounts-api -n 50 --no-pager
```

Le service utilise root pour conserver le proprietaire du fichier existant
(root dans cette installation) lors du remplacement atomique. Il est cloisonne
par systemd : systeme de fichiers en lecture seule sauf le repertoire de config
mail, privileges et familles de sockets restreints, aucun acces au socket Docker.
Le montage `/app` doit etre disponible avant le demarrage.
Apres modification du `.env` : `systemctl restart mail-accounts-api`.

Le port vise est **9941/TCP**. Ne pas l'exposer sur Internet. Limiter par pare-feu
aux clients autorises et utiliser HTTPS via un proxy ou un tunnel SSH : HTTP
seul ne chiffre ni la cle ni les mots de passe, meme sur un LAN.
L'API ne redemarre et ne redeploie pas Docker. La prise en compte depend du
detecteur de changements de docker-mailserver ; verifier cette fonction dans
l'installation avant de considerer un compte utilisable en SMTP/IMAP.

## Tests

```sh
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

Les tests utilisent uniquement des fichiers temporaires, jamais les comptes
de production. Le script CLI conserve son interface d'origine et son chemin
historique `/app/12-mail/config/postfix-accounts.cf`.
