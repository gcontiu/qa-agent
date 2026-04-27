Feature: Alcon Ind — GDPR și Politica de Confidențialitate

  Background:
    Given utilizatorul accesează pagina de politică de confidențialitate la URL-ul /politica-confidentialitate

  @id:AC-600 @priority:high
  Scenario: Politica de confidențialitate este completă și ușor de găsit
    Then titlul Politica de Confidențialitate sau Privacy Policy este vizibil
    And data ultimei actualizări a politicii este prezentată
    And o descriere a modului în care sunt colectate datele este prezentă

  @id:AC-601 @priority:high
  Scenario: Informații despre drepturi GDPR sunt menționate
    Then mențiunea dreptului de acces la date personale este prezentă
    And dreptul de ștergere ("dreptul să fii uitat") este explicat
    And dreptul de portabilitate a datelor este menționat

  @id:AC-602 @priority:medium
  Scenario: Contact pentru responsabilul cu protecția datelor
    Then contact pentru Data Protection Officer (DPO) este vizibil
    Then o adresă de email pentru cererile GDPR este furnizată
    And procedura de depunere a unei plângeri este explicată
