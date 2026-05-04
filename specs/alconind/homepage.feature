Feature: Alcon Ind — Homepage și navigare

  @id:AC-001 @priority:high
  Scenario: Homepage se încarcă cu elementele principale vizibile
    Given utilizatorul accesează site-ul
    Then numele companiei sau logo-ul Alcon Ind este vizibil
    And un buton CTA principal este vizibil pe homepage

  @id:AC-002 @priority:high
  Scenario: Meniul de navigare conține toate secțiunile principale
    Given utilizatorul accesează site-ul
    Then meniul conține linkul Acasă
    And meniul conține linkul Produse
    And meniul conține linkul Contact
    And meniul conține linkul Cerere Ofertă

  @id:AC-003 @priority:high
  Scenario: Pagina Produse este accesibilă și afișează categorii
    Given utilizatorul accesează site-ul
    When utilizatorul apasă pe linkul Produse din meniu
    Then pagina de produse se deschide
    And cel puțin o categorie de produse este vizibilă

  @id:AC-004 @priority:high
  Scenario: Informațiile de contact sunt vizibile pe pagina Contact
    Given utilizatorul accesează site-ul
    When utilizatorul apasă pe linkul Contact din meniu
    Then pagina de contact se deschide
    And un număr de telefon este vizibil pe pagină

  @id:AC-005 @priority:medium
  Scenario: Formularul de cerere ofertă este accesibil
    Given utilizatorul accesează site-ul
    When utilizatorul apasă pe linkul Cerere Ofertă din meniu
    Then pagina de cerere ofertă se deschide
    And un formular sau câmpuri de completat sunt vizibile pe pagină

  @id:AC-006 @priority:medium
  Scenario: Statisticile companiei sunt vizibile pe homepage
    Given utilizatorul accesează site-ul
    Then o referință la experiența sau numărul de clienți ai companiei este vizibilă

  @id:AC-007 @priority:low
  Scenario: Footer conține linkuri GDPR și politică de confidențialitate
    Given utilizatorul accesează site-ul
    Then footer-ul conține un link către politica de confidențialitate sau GDPR
