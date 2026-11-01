// SPDX-License-Identifier: GPL-3.0-or-later
// Interface dynamique Mail Accounts API (issue #9) : tous les échanges
// passent par les routes /accounts existantes ; la clé Bearer reste en
// sessionStorage, jamais dans l'URL ni un cookie.

"use strict";

const CLE_STOCKAGE = "mail_api_key";

const elements = {
  pastille: document.getElementById("pastille"),
  etatTexte: document.getElementById("etat-texte"),
  formCle: document.getElementById("form-cle"),
  cle: document.getElementById("cle"),
  boutonOublier: document.getElementById("bouton-oublier"),
  contenu: document.getElementById("contenu"),
  message: document.getElementById("message"),
  corpsTableau: document.getElementById("corps-tableau"),
  total: document.getElementById("total"),
  filtre: document.getElementById("filtre"),
  formCreation: document.getElementById("form-creation"),
  formNumerote: document.getElementById("form-numerote"),
  formLot: document.getElementById("form-lot"),
};

function cle() {
  return window.sessionStorage.getItem(CLE_STOCKAGE) || "";
}

function definirCle(valeur) {
  if (valeur) {
    window.sessionStorage.setItem(CLE_STOCKAGE, valeur);
  } else {
    window.sessionStorage.removeItem(CLE_STOCKAGE);
  }
  afficherCadre();
}

function entetes() {
  return { "Authorization": "Bearer " + cle(), "Content-Type": "application/json" };
}

async function requete(chemin, options) {
  const reponse = await window.fetch(chemin, options);
  if (!reponse.ok) {
    const detail = await reponse.json().catch(() => ({}));
    throw new Error((detail.detail && String(detail.detail)) || "Erreur " + reponse.status);
  }
  return reponse;
}

function message(texte, classe, motDePasse) {
  elements.message.textContent = texte;
  elements.message.className = classe;
  elements.message.replaceChildren(document.createTextNode(texte));
  if (motDePasse) {
    const bloc = document.createElement("code");
    bloc.textContent = motDePasse;
    elements.message.append(bloc);
  }
}

async function verifierSante() {
  try {
    await window.fetch("/health");
    elements.pastille.className = "pastille saine";
    elements.etatTexte.textContent = "service sain";
  } catch (erreur) {
    elements.pastille.className = "pastille hors-service";
    elements.etatTexte.textContent = "service injoignable";
  }
}

function afficherCadre() {
  const connecte = cle() !== "";
  elements.contenu.hidden = !connecte;
  elements.boutonOublier.hidden = !connecte;
  if (connecte) {
    chargerComptes();
  }
}

async function chargerComptes() {
  try {
    const reponse = await requete("/accounts", { headers: entetes() });
    const donnees = await reponse.json();
    dessinerComptes(donnees.accounts);
  } catch (erreur) {
    message("Impossible de lister les comptes : " + erreur.message, "erreur");
  }
}

function dessinerComptes(comptes) {
  const terme = elements.filtre.value.trim().toLowerCase();
  const visibles = comptes.filter((compte) =>
    !terme || compte.email.toLowerCase().includes(terme) || compte.folder.toLowerCase().includes(terme)
  );
  elements.total.textContent = "(" + visibles.length + " / " + comptes.length + ")";
  elements.corpsTableau.replaceChildren();
  for (const compte of visibles) {
    const ligne = document.createElement("tr");

    const adresse = document.createElement("td");
    adresse.textContent = compte.email;

    const dossier = document.createElement("td");
    dossier.textContent = compte.folder;

    const actions = document.createElement("td");
    actions.append(boutonMotDePasse(compte.email), boutonSuppression(compte.email));

    ligne.append(adresse, dossier, actions);
    elements.corpsTableau.append(ligne);
  }
}

function boutonMotDePasse(email) {
  const bouton = document.createElement("button");
  bouton.type = "button";
  bouton.textContent = "Changer le mot de passe";
  bouton.addEventListener("click", () => changerMotDePasse(email));
  return bouton;
}

function boutonSuppression(email) {
  const bouton = document.createElement("button");
  bouton.type = "button";
  bouton.textContent = "Supprimer";
  bouton.addEventListener("click", () => supprimerCompte(email));
  return bouton;
}

async function changerMotDePasse(email) {
  const motDePasse = window.prompt("Nouveau mot de passe pour " + email + " :");
  if (motDePasse === null) {
    return;
  }
  try {
    const reponse = await requete("/accounts/" + encodeURIComponent(email), {
      method: "PATCH",
      headers: entetes(),
      body: JSON.stringify({ password: motDePasse }),
    });
    const compte = await reponse.json();
    message("Mot de passe de " + compte.email + " modifié.", "succes");
  } catch (erreur) {
    message("Échec du changement de mot de passe : " + erreur.message, "erreur");
  }
}

async function supprimerCompte(email) {
  if (!window.confirm("Supprimer le compte " + email + " ? (les données de la boîte restent sur disque)")) {
    return;
  }
  try {
    await requete("/accounts/" + encodeURIComponent(email), { method: "DELETE", headers: entetes() });
    message("Compte " + email + " supprimé.", "succes");
    chargerComptes();
  } catch (erreur) {
    message("Échec de la suppression : " + erreur.message, "erreur");
  }
}

async function creer(compte) {
  try {
    const reponse = await requete("/accounts", {
      method: "POST",
      headers: entetes(),
      body: JSON.stringify(compte),
    });
    const cree = await reponse.json();
    message("Compte " + cree.email + " créé.", "succes", cree.password || undefined);
    chargerComptes();
  } catch (erreur) {
    message("Échec de la création : " + erreur.message, "erreur");
  }
}

elements.formCle.addEventListener("submit", (evenement) => {
  evenement.preventDefault();
  definirCle(elements.cle.value.trim());
  elements.cle.value = "";
});

elements.boutonOublier.addEventListener("click", () => definirCle(""));

elements.filtre.addEventListener("input", () => chargerComptes());

elements.formCreation.addEventListener("submit", (evenement) => {
  evenement.preventDefault();
  const motDePasse = document.getElementById("mot-de-passe").value;
  creer({
    email: document.getElementById("email").value,
    password: motDePasse === "" ? null : motDePasse,
  });
});

elements.formNumerote.addEventListener("submit", (evenement) => {
  evenement.preventDefault();
  const motDePasse = window.prompt(
    "Mot de passe partagé pour le lot (annuler : un mot de passe distinct par compte) :"
  );
  const corps = {
    email: document.getElementById("base").value,
    start: Number(document.getElementById("debut").value),
    end: Number(document.getElementById("fin").value),
  };
  if (motDePasse !== null && motDePasse !== "") {
    corps.password = motDePasse;
  }
  creer(corps);
});

elements.formLot.addEventListener("submit", (evenement) => {
  evenement.preventDefault();
  const comptes = document.getElementById("emails").value
    .split("\n")
    .map((ligne) => ligne.trim())
    .filter((ligne) => ligne !== "")
    .map((email) => ({ email: email }));
  creerLot(comptes);
});

async function creerLot(comptes) {
  try {
    const reponse = await requete("/accounts/batch", {
      method: "POST",
      headers: entetes(),
      body: JSON.stringify({ accounts: comptes }),
    });
    const crees = await reponse.json();
    message(comptes.length + " comptes créés.", "succes");
    for (const compte of crees) {
      if (compte.password) {
        message("Mot de passe de " + compte.email + " :", "succes", compte.password);
      }
    }
    chargerComptes();
  } catch (erreur) {
    message("Échec du lot : " + erreur.message, "erreur");
  }
}

window.setInterval(verifierSante, 30000);
verifierSante();
afficherCadre();
