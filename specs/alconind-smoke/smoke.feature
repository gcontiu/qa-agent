Feature: Alcon Ind — Smoke Test (3 scenarii)

  @id:AC-001 @priority:high
  Scenario: Homepage se încarcă cu elementele principale vizibile
    Given utilizatorul accesează site-ul
    Then numele companiei sau logo-ul Alcon Ind este vizibil
    And un buton CTA principal este vizibil pe homepage

  @id:AC-003 @priority:high
  Scenario: Pagina Produse este accesibilă și afișează categorii
    Given utilizatorul accesează site-ul
    When utilizatorul apasă pe linkul Produse din meniu
    Then pagina de produse se deschide
    And cel puțin o categorie de produse este vizibilă

  @id:AC-100 @priority:high
  Scenario: Pagina Produse afișează toate cele trei categorii principale
    Given utilizatorul accesează pagina de produse la URL-ul /produse
    Then categoria Țevi este vizibilă pe pagină
    And categoria Profile Laminate la Cald este vizibilă pe pagină
    And categoria Tablă Metalică este vizibilă pe pagină
