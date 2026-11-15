// Jeu d'icônes de l'interface : données pures, testées sans DOM.
// Chaque icône est une liste d'attributs `d` de <path>, sur une grille 24 × 24,
// dessinés pour un trait de 1,75 sans remplissage (traits ronds, formes simples,
// lisibles de 16 à 20 px). Dessinées pour Oliv'IA : aucun paquet importé, rien
// de téléchargé (la CSP interdit toute ressource distante).
// Les cercles sont tracés par deux demi-arcs : « M x-r y a r r 0 1 0 2r 0 a r r 0 1 0 -2r 0 ».

export const ICONES = {
  maison: [
    'M3 10.5 12 3l9 7.5',
    'M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5',
  ],
  bulle: [
    'M4 5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H9l-5 4z',
  ],
  dossier: [
    'M3 6.5A1.5 1.5 0 0 1 4.5 5H9l2 2.5h8.5A1.5 1.5 0 0 1 21 9v9.5a1.5 1.5 0 0 1-1.5 1.5h-15'
      + 'A1.5 1.5 0 0 1 3 18.5z',
  ],
  document: [
    'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z',
    'M14 3v5h5',
    'M9 13h6',
    'M9 17h6',
  ],
  // Tableau blanc sur chevalet (les « tableaux » d'Oliv'IA sont des tableaux blancs).
  tableau: [
    'M3 4h18',
    'M4 4v11a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1V4',
    'M12 16v4',
    'M8 21l4-5 4 5',
  ],
  engrenage: [
    'M5.5 12a6.5 6.5 0 1 0 13 0a6.5 6.5 0 1 0-13 0',
    'M9.5 12a2.5 2.5 0 1 0 5 0a2.5 2.5 0 1 0-5 0',
    'M12 3v2.5',
    'M12 18.5V21',
    'M3 12h2.5',
    'M18.5 12H21',
    'M5.64 5.64l1.76 1.76',
    'M16.6 16.6l1.76 1.76',
    'M5.64 18.36l1.76-1.76',
    'M16.6 7.4l1.76-1.76',
  ],
  utilisateur: [
    'M8 8a4 4 0 1 0 8 0a4 4 0 1 0-8 0',
    'M4 21a8 8 0 0 1 16 0',
  ],
  utilisateurs: [
    'M5.5 8a3.5 3.5 0 1 0 7 0a3.5 3.5 0 1 0-7 0',
    'M2 20a7 7 0 0 1 14 0',
    'M16 4.6a3.5 3.5 0 0 1 0 6.8',
    'M18 14.2A7 7 0 0 1 22 20',
  ],
  sortie: [
    'M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4',
    'M16 17l5-5-5-5',
    'M21 12H9',
  ],
  plus: [
    'M12 5v14',
    'M5 12h14',
  ],
  envoyer: [
    'M22 2 11 13',
    'M22 2l-7 20-4-9-9-4z',
  ],
  stop: [
    'M7 5h10a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z',
  ],
  globe: [
    'M3 12a9 9 0 1 0 18 0a9 9 0 1 0-18 0',
    'M3 12h18',
    'M12 3a14 14 0 0 1 0 18a14 14 0 0 1 0-18z',
  ],
  trombone: [
    'M20.5 11.5l-8.6 8.6a5.5 5.5 0 0 1-7.8-7.8l8.6-8.6a3.7 3.7 0 0 1 5.2 5.2l-8.6 8.6'
      + 'a1.8 1.8 0 0 1-2.6-2.6l7.9-7.9',
  ],
  crayon: [
    'M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4z',
    'M14.5 5.5l3 3',
  ],
  corbeille: [
    'M4 7h16',
    'M10 11v6',
    'M14 11v6',
    'M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12',
    'M9 7V4.5A1.5 1.5 0 0 1 10.5 3h3A1.5 1.5 0 0 1 15 4.5V7',
  ],
  telecharger: [
    'M12 3v12',
    'M7 10l5 5 5-5',
    'M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2',
  ],
  oeil: [
    'M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z',
    'M9 12a3 3 0 1 0 6 0a3 3 0 1 0-6 0',
  ],
  fermer: [
    'M6 6l12 12',
    'M18 6 6 18',
  ],
  loupe: [
    'M4 11a7 7 0 1 0 14 0a7 7 0 1 0-14 0',
    'M21 21l-5-5',
  ],
  eclair: [
    'M13 2 4 14h7l-1 8 9-12h-7z',
  ],
  // Puce électronique : le processeur ou la carte graphique (choix du moteur).
  puce: [
    'M7 5h10a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z',
    'M9.5 9.5h5v5h-5z',
    'M9 2v3',
    'M15 2v3',
    'M9 19v3',
    'M15 19v3',
    'M2 9h3',
    'M2 15h3',
    'M19 9h3',
    'M19 15h3',
  ],
  // Plume d'écriture, pour le mode « Léger ».
  plume: [
    'M6 18C6 10 11 4 20 4c0 9-6 14-14 14z',
    'M3 21l9-9',
  ],
  cloche: [
    'M6 16v-5a6 6 0 0 1 12 0v5l2 2H4z',
    'M10 21a2 2 0 0 0 4 0',
  ],
  mail: [
    'M5 5h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z',
    'M3 7l9 6 9-6',
  ],
  calendrier: [
    'M5 4h14a2 2 0 0 1 2 2v13a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z',
    'M3 10h18',
    'M8 2v4',
    'M16 2v4',
  ],
  cadenas: [
    'M6 11h12a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1v-8a1 1 0 0 1 1-1z',
    'M8 11V7a4 4 0 0 1 8 0v4',
  ],
  alerte: [
    'M10.3 3.9 2.4 17.5a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z',
    'M12 9v4',
    'M12 17h.01',
  ],
  coche: [
    'M20 6 9 17l-5-5',
  ],
  'chevron-bas': [
    'M6 9l6 6 6-6',
  ],
  'chevron-droite': [
    'M9 6l6 6-6 6',
  ],
  'chevron-gauche': [
    'M15 6l-6 6 6 6',
  ],
  menu: [
    'M4 6h16',
    'M4 12h16',
    'M4 18h16',
  ],
  // Trois points horizontaux (menu « plus d'actions »).
  points: [
    'M4 12a1 1 0 1 0 2 0a1 1 0 1 0-2 0',
    'M11 12a1 1 0 1 0 2 0a1 1 0 1 0-2 0',
    'M18 12a1 1 0 1 0 2 0a1 1 0 1 0-2 0',
  ],
  soleil: [
    'M8 12a4 4 0 1 0 8 0a4 4 0 1 0-8 0',
    'M12 2v2',
    'M12 20v2',
    'M2 12h2',
    'M20 12h2',
    'M4.93 4.93l1.41 1.41',
    'M17.66 17.66l1.41 1.41',
    'M4.93 19.07l1.41-1.41',
    'M17.66 6.34l1.41-1.41',
  ],
  lune: [
    'M12 3a6.5 6.5 0 0 0 9 9a9 9 0 1 1-9-9z',
  ],
  // Écran d'ordinateur : « Suivre Windows » dans le choix du thème.
  ecran: [
    'M4 4h16a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z',
    'M8 20h8',
    'M12 16v4',
  ],
  etincelles: [
    'M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z',
    'M19 15v4',
    'M17 17h4',
    'M5 3v3',
    'M3.5 4.5h3',
  ],
  // Panneau latéral (afficher / masquer la colonne).
  panneau: [
    'M5 4h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z',
    'M9 4v16',
  ],
  actualiser: [
    'M20 11a8 8 0 0 0-14.3-4.9L4 8',
    'M4 4v4h4',
    'M4 13a8 8 0 0 0 14.3 4.9L20 16',
    'M20 20v-4h-4',
  ],
  copier: [
    'M10 8h9a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-9a2 2 0 0 1-2-2v-9a2 2 0 0 1 2-2z',
    'M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3',
  ],
  livre: [
    'M2 5h6a4 4 0 0 1 4 4v12a3 3 0 0 0-3-3H2z',
    'M22 5h-6a4 4 0 0 0-4 4v12a3 3 0 0 1 3-3h7z',
  ],
  image: [
    'M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z',
    'M8 9.5a1.5 1.5 0 1 0 3 0a1.5 1.5 0 1 0-3 0',
    'M21 15l-5-5L5 21',
  ],
}

export const NOMS_ICONES = Object.keys(ICONES)
