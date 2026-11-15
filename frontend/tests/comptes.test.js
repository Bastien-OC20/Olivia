import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  typesDeCaracteres, erreurMotDePasseFaible, erreurFormulaireMotDePasse,
  erreurReinitialisation, messageMotDePasseChange, messageErreurServeur, actionsCompte,
  libelleChangerRole, questionSuppression, dateCreation, remplacerCompte, trierComptes,
} from '../src/comptes.js'
import { noteSecret } from '../src/secrets.js'

test('typesDeCaracteres compte minuscules, majuscules, chiffres et spéciaux', () => {
  assert.equal(typesDeCaracteres('abc'), 1)
  assert.equal(typesDeCaracteres('Abc1'), 3)
  assert.equal(typesDeCaracteres('Abc1!'), 4)
  assert.equal(typesDeCaracteres('été Été'), 3)
})

test('la règle : 8 caractères et trois types', () => {
  assert.notEqual(erreurMotDePasseFaible('Ab1!'), '')          // trop court
  assert.notEqual(erreurMotDePasseFaible('abcdefgh'), '')      // un seul type
  assert.notEqual(erreurMotDePasseFaible('abcdefg1'), '')      // deux types
  assert.equal(erreurMotDePasseFaible('abcdEFG1'), '')
  assert.equal(erreurMotDePasseFaible('abcd-efg1'), '')
})

test('le formulaire de changement signale le premier problème à corriger', () => {
  const ok = { ancien: 'Ancien1234', nouveau: 'Nouveau1234', confirmation: 'Nouveau1234' }
  assert.equal(erreurFormulaireMotDePasse(ok), '')
  assert.match(erreurFormulaireMotDePasse({ ...ok, ancien: '' }), /actuel/)
  assert.match(erreurFormulaireMotDePasse({ ...ok, nouveau: '' }), /nouveau/)
  assert.match(erreurFormulaireMotDePasse({ ...ok, nouveau: 'abc', confirmation: 'abc' }), /trop faible/)
  assert.match(erreurFormulaireMotDePasse({ ...ok, nouveau: 'Ancien1234' }), /différent/)
  assert.match(erreurFormulaireMotDePasse({ ...ok, confirmation: 'Autre1234' }), /confirmation/)
})

test('la réinitialisation exige un mot de passe conforme', () => {
  assert.notEqual(erreurReinitialisation(''), '')
  assert.notEqual(erreurReinitialisation('faible'), '')
  assert.equal(erreurReinitialisation('Solide1234'), '')
})

test('le message de succès dit combien de sessions ont été fermées', () => {
  assert.match(messageMotDePasseChange(0), /Aucune autre session/)
  assert.match(messageMotDePasseChange(1), /autre session a été fermée/)
  assert.match(messageMotDePasseChange(3), /3 autres sessions ont été fermées/)
  assert.match(messageMotDePasseChange(undefined), /Mot de passe modifié/)
})

test('le message d\'erreur reprend le detail du serveur tel quel', () => {
  assert.equal(messageErreurServeur(400, { detail: 'Mot de passe actuel incorrect.' }),
    'Mot de passe actuel incorrect.')
  assert.match(messageErreurServeur(429, null, '12'), /12 seconde/)
  assert.match(messageErreurServeur(429, {}, null), /Patientez/)
  assert.match(messageErreurServeur(403, null), /responsable/)
  assert.match(messageErreurServeur(500, null), /Réessayez/)
})

test('pas de suppression, réinitialisation ni changement de rôle sur sa propre ligne', () => {
  const moi = actionsCompte({ id: 'a', role: 'responsable', moi: true, bloque: false })
  assert.deepEqual(moi,
    { reinitialiser: false, debloquer: false, changerRole: null, supprimer: false })
})

test('actions sur la ligne d\'un autre compte', () => {
  const membre = actionsCompte({ id: 'b', role: 'membre', moi: false, bloque: false })
  assert.deepEqual(membre,
    { reinitialiser: true, debloquer: false, changerRole: 'responsable', supprimer: true })
  const resp = actionsCompte({ id: 'c', role: 'responsable', moi: false, bloque: true })
  assert.equal(resp.changerRole, 'membre')
  assert.equal(resp.debloquer, true)
  assert.equal(libelleChangerRole('responsable'), 'Passer responsable')
  assert.equal(libelleChangerRole('membre'), 'Passer membre')
})

test('la question de suppression nomme le compte', () => {
  assert.match(questionSuppression({ username: 'marie' }), /« marie »/)
})

test('dateCreation lit des secondes et tolère l\'absence', () => {
  assert.match(dateCreation(1763164800), /2025/)
  assert.equal(dateCreation(undefined), '')
  assert.equal(dateCreation(0), '')
})

test('remplacerCompte garde « moi » et trierComptes met soi en premier', () => {
  const liste = [
    { id: '1', username: 'zoe', role: 'membre', moi: false },
    { id: '2', username: 'ana', role: 'responsable', moi: true },
    { id: '3', username: 'bob', role: 'membre', moi: false },
  ]
  const maj = remplacerCompte(liste, { id: '2', role: 'membre' })
  assert.equal(maj[1].moi, true)
  assert.equal(liste[1].role, 'responsable')   // l'original n'est pas modifié
  assert.deepEqual(trierComptes(liste).map(c => c.username), ['ana', 'bob', 'zoe'])
})

test('noteSecret : avertissement, ligne « en clair » ou rien', () => {
  const nom = 'connectors.imap.password'
  assert.equal(noteSecret({ chiffres: true, a_ressaisir: [nom] }, nom), 'a_ressaisir')
  assert.equal(noteSecret({ chiffres: false, a_ressaisir: [nom] }, nom), 'a_ressaisir')
  assert.equal(noteSecret({ chiffres: false, a_ressaisir: [] }, nom), 'clair')
  assert.equal(noteSecret({ chiffres: true, a_ressaisir: [] }, nom), null)
  assert.equal(noteSecret({ chiffres: true, a_ressaisir: ['autre'] }, nom), null)
  assert.equal(noteSecret(null, nom), null)
  assert.equal(noteSecret(undefined, nom), null)
})
