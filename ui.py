# SPDX-License-Identifier: GPL-3.0-or-later
"""Interface web de Mail Accounts API (issue #9).

Page statique sans outil de build, servie par l'API elle-même (route ``/``).
Entièrement dynamique : toutes les données viennent des routes JSON, en
same-origin (URLs relatives), avec la clé Bearer saisie par l'opérateur et
gardée en ``sessionStorage`` uniquement (jamais ``localStorage``, jamais un
cookie). Aucune ressource externe : la page fonctionne sur un réseau local
sans accès Internet.
"""

PAGE_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mail Accounts — interface</title>
<style>
  :root { color-scheme: light dark; }
  body {
    font-family: system-ui, sans-serif;
    max-width: 60rem;
    margin: 0 auto;
    padding: 1rem;
    line-height: 1.5;
  }
  fieldset { margin: 1rem 0; }
  legend { font-weight: bold; }
  table { border-collapse: collapse; width: 100%; margin: .5rem 0; }
  th, td { border: 1px solid currentColor; padding: .3rem .6rem; text-align: left; }
  code, .mono { font-family: ui-monospace, monospace; }
  .erreur { color: #c0392b; font-weight: bold; }
  .ok { color: #1e7e34; }
  button { cursor: pointer; }
  .champ { display: inline-block; min-width: 8rem; }
</style>
</head>
<body>
<h1>Mail Accounts — interface</h1>
<noscript><p class="erreur">Cette interface nécessite JavaScript : toutes les
données sont fournies dynamiquement par l'API.</p></noscript>

<fieldset id="connexion">
  <legend>Clé API</legend>
  <p>La clé est gardée uniquement dans <code>sessionStorage</code> (onglet
  courant, jamais écrite sur disque par la page). Elle n'est transmise
  qu'en en-tête <code>Authorization</code>, jamais dans l'URL.</p>
  <label><span class="champ">Clé Bearer :</span>
    <input type="password" id="cle" autocomplete="off" size="48"></label>
  <button id="enregistrer">Enregistrer la clé</button>
  <button id="oublier">Oublier la clé</button>
</fieldset>

<p id="etat"></p>

<fieldset>
  <legend>Comptes</legend>
  <button id="rafraichir">Rafraîchir la liste</button>
  <table id="liste"><thead><tr><th>Adresse</th><th>Dossier</th></tr></thead>
    <tbody></tbody></table>
  <p id="total"></p>
</fieldset>

<fieldset>
  <legend>Ajouter un compte</legend>
  <p><label><span class="champ">Adresse :</span>
    <input id="ajout-email" size="32" placeholder="user@example.org"></label>
  <label><span class="champ">Mot de passe :</span>
    <input type="password" id="ajout-mdp" autocomplete="new-password"
      placeholder="vide = généré"></label></p>
  <button id="ajouter">Ajouter</button>
</fieldset>

<fieldset>
  <legend>Ajouter un lot (1 à 100 comptes, atomique)</legend>
  <p>Une ligne par compte : <code>adresse</code> ou
  <code>adresse mot_de_passe</code> (le mot de passe est le reste de la
  ligne). Sans mot de passe : chacun est généré aléatoirement.</p>
  <textarea id="lot-texte" rows="4" cols="60"
    placeholder="alice@example.org
bob@example.org mot de passe de bob"></textarea><br>
  <button id="lot-envoyer">Ajouter le lot</button>
</fieldset>

<fieldset>
  <legend>Ajouter des comptes numérotés</legend>
  <p>Pour <code>user@example.org</code>, premier 1, dernier 4 :
  <code>user1</code>, <code>user2</code>, <code>user3</code>. Le mot de
  passe, s'il est fourni, est partagé par tout le lot.</p>
  <p><label><span class="champ">Adresse :</span>
    <input id="num-email" size="32" placeholder="user@example.org"></label>
  <label>Premier : <input id="num-debut" type="number" value="1" min="1"></label>
  <label>Dernier (exclu) : <input id="num-fin" type="number" value="2" min="2"></label>
  <label>Mot de passe :
    <input type="password" id="num-mdp" autocomplete="new-password"
      placeholder="vide = générés distincts"></label></p>
  <button id="num-envoyer">Ajouter</button>
</fieldset>

<fieldset>
  <legend>Modifier le mot de passe</legend>
  <p><label><span class="champ">Adresse :</span>
    <input id="mod-email" size="32"></label>
  <label>Nouveau mot de passe :
    <input type="password" id="mod-mdp" autocomplete="new-password"></label></p>
  <button id="modifier">Modifier</button>
</fieldset>

<fieldset>
  <legend>Supprimer un compte</legend>
  <p>La suppression ne touche pas les données de la boîte sur disque.</p>
  <p><label><span class="champ">Adresse :</span>
    <input id="sup-email" size="32"></label>
  <button id="supprimer">Supprimer</button></p>
</fieldset>

<fieldset>
  <legend>Mots de passe générés</legend>
  <p>Affichés une seule fois, ici même, à la création. Ils ne sont plus
  lisibles ensuite : les mots de passe ne sont jamais renvoyés par
  l'API.</p>
  <table id="cree"><thead><tr><th>Adresse</th><th>Mot de passe</th></tr></thead>
    <tbody></tbody></table>
</fieldset>

<script>
"use strict";

const CLE = "mailAccountsCle";

function cleApi() {
  return sessionStorage.getItem(CLE) || "";
}

function entetes() {
  return { "Authorization": "Bearer " + cleApi() };
}

function etat(message, classe) {
  const zone = document.getElementById("etat");
  zone.textContent = message;
  zone.className = classe || "";
}

function videTables() {
  document.querySelector("#liste tbody").innerHTML = "";
  document.querySelector("#cree tbody").innerHTML = "";
}

async function api(chemin, options) {
  const reponse = await fetch(chemin, Object.assign({
    headers: entetes(),
    cache: "no-store"
  }, options || {}));
  if (reponse.status === 401) {
    throw new Error("Clé absente ou incorrecte (401).");
  }
  if (reponse.status === 503) {
    throw new Error("Stockage indisponible : fichier de comptes absent ou mal formé (503).");
  }
  if (reponse.status === 204) {
    return null;
  }
  const corps = await reponse.json().catch(() => null);
  if (!reponse.ok) {
    const detail = corps && corps.detail;
    let message = "Erreur " + reponse.status;
    if (detail === "Account already exists") { message = "Compte déjà existant (409)."; }
    else if (detail === "Account not found") { message = "Compte absent (404)."; }
    else if (reponse.status === 422) { message = "Requête invalide (422) : " + JSON.stringify(detail); }
    throw new Error(message);
  }
  return corps;
}

async function rafraichir() {
  try {
    const corps = await api("/accounts");
    const lignes = document.querySelector("#liste tbody");
    lignes.innerHTML = "";
    for (const compte of corps.accounts) {
      const tr = document.createElement("tr");
      for (const valeur of [compte.email, compte.folder]) {
        const td = document.createElement("td");
        td.textContent = valeur;
        tr.appendChild(td);
      }
      lignes.appendChild(tr);
    }
    document.getElementById("total").textContent =
      corps.total + " compte" + (corps.total > 1 ? "s" : "") + ".";
    etat("Liste rafraîchie.", "ok");
  } catch (erreur) {
    etat(erreur.message, "erreur");
  }
}

function afficherCrees(comptes) {
  const lignes = document.querySelector("#cree tbody");
  for (const compte of comptes) {
    if (compte.password === undefined) { continue; }
    const tr = document.createElement("tr");
    const tdAdresse = document.createElement("td");
    tdAdresse.textContent = compte.email;
    const tdMot = document.createElement("td");
    tdMot.textContent = compte.password;
    tdMot.className = "mono";
    tr.appendChild(tdAdresse);
    tr.appendChild(tdMot);
    lignes.appendChild(tr);
  }
}

function lireLot() {
  const comptes = [];
  for (const ligne of document.getElementById("lot-texte").value.split("\\n")) {
    const nettoyee = ligne.trim();
    if (!nettoyee) { continue; }
    const separateur = nettoyee.indexOf(" ");
    const compte = separateur === -1
      ? { email: nettoyee }
      : { email: nettoyee.slice(0, separateur), password: nettoyee.slice(separateur + 1) };
    comptes.push(compte);
  }
  return comptes;
}

document.getElementById("enregistrer").addEventListener("click", () => {
  sessionStorage.setItem(CLE, document.getElementById("cle").value);
  etat("Clé enregistrée pour cet onglet.", "ok");
});

document.getElementById("oublier").addEventListener("click", () => {
  sessionStorage.removeItem(CLE);
  document.getElementById("cle").value = "";
  videTables();
  etat("Clé oubliée.");
});

document.getElementById("rafraichir").addEventListener("click", rafraichir);

document.getElementById("ajouter").addEventListener("click", async () => {
  const corps = { email: document.getElementById("ajout-email").value.trim() };
  const mot = document.getElementById("ajout-mdp").value;
  if (mot) { corps.password = mot; }
  try {
    const cree = await api("/accounts", {
      method: "POST",
      headers: Object.assign({ "Content-Type": "application/json" }, entetes()),
      body: JSON.stringify(corps)
    });
    afficherCrees([cree]);
    etat("Compte créé.", "ok");
    await rafraichir();
  } catch (erreur) {
    etat(erreur.message, "erreur");
  }
});

document.getElementById("lot-envoyer").addEventListener("click", async () => {
  const comptes = lireLot();
  if (comptes.length === 0) { etat("Lot vide.", "erreur"); return; }
  try {
    const crees = await api("/accounts/batch", {
      method: "POST",
      headers: Object.assign({ "Content-Type": "application/json" }, entetes()),
      body: JSON.stringify({ accounts: comptes })
    });
    afficherCrees(crees);
    etat(comptes.length + " compte(s) créé(s).", "ok");
    await rafraichir();
  } catch (erreur) {
    etat(erreur.message, "erreur");
  }
});

document.getElementById("num-envoyer").addEventListener("click", async () => {
  const corps = {
    email: document.getElementById("num-email").value.trim(),
    start: Number(document.getElementById("num-debut").value),
    end: Number(document.getElementById("num-fin").value)
  };
  const mot = document.getElementById("num-mdp").value;
  if (mot) { corps.password = mot; }
  try {
    const crees = await api("/accounts/numbered", {
      method: "POST",
      headers: Object.assign({ "Content-Type": "application/json" }, entetes()),
      body: JSON.stringify(corps)
    });
    afficherCrees(crees);
    etat(crees.length + " compte(s) créé(s).", "ok");
    await rafraichir();
  } catch (erreur) {
    etat(erreur.message, "erreur");
  }
});

document.getElementById("modifier").addEventListener("click", async () => {
  const email = document.getElementById("mod-email").value.trim();
  const corps = { password: document.getElementById("mod-mdp").value };
  try {
    await api("/accounts/" + encodeURIComponent(email), {
      method: "PATCH",
      headers: Object.assign({ "Content-Type": "application/json" }, entetes()),
      body: JSON.stringify(corps)
    });
    etat("Mot de passe modifié.", "ok");
  } catch (erreur) {
    etat(erreur.message, "erreur");
  }
});

document.getElementById("supprimer").addEventListener("click", async () => {
  const email = document.getElementById("sup-email").value.trim();
  if (!window.confirm("Supprimer " + email + " ? (les données de la boîte restent sur disque)")) {
    return;
  }
  try {
    await api("/accounts/" + encodeURIComponent(email), { method: "DELETE" });
    etat("Compte supprimé.", "ok");
    await rafraichir();
  } catch (erreur) {
    etat(erreur.message, "erreur");
  }
});

if (cleApi()) { etat("Clé déjà enregistrée pour cet onglet.", "ok"); }
</script>
</body>
</html>
"""
