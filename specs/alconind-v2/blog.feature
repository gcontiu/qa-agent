Feature: Alcon Ind — Blog Tehnic

  Background:
    Given utilizatorul accesează pagina Blog la URL-ul /blog

  @id:AC-1000 @priority:high
  Scenario: Pagina Blog se încarcă cu titlul corect
    Then titlul paginii conține "Blog Tehnic"
    And este vizibil un heading H1 cu textul "Ghiduri și articole despre produse metalurgice"

  @id:AC-1001 @priority:high
  Scenario: Sunt afișate cardurile articolelor
    Then este vizibil un link către "/blog/cum-obtii-o-oferta-de-pret-corecta-pentru-produse-metalurgice"
    And este vizibil un link către "/blog/tevi-pentru-instalatii-de-gaze-cerinte-tehnice-si-furnizori"
    And este vizibil un link către "/blog/tabla-groasa-pentru-constructii-grosimi-standarde-si-aplicatii"
    And este vizibil un link către "/blog/livrare-produse-metalurgice-in-transilvania-ce-trebuie-sa-stii"
    And este vizibil un link către "/blog/profile-metalice-pentru-hale-industriale-ghid-de-comanda"

  @id:AC-1002 @priority:medium
  Scenario: Articolele afișează categoria/eticheta corespunzătoare
    Then este vizibil textul "GHID-TEHNIC" pe cel puțin un card
    And este vizibil textul "TEVI" pe cel puțin un card
    And este vizibil textul "TABLA" pe cel puțin un card
    And este vizibil textul "PROFILE" pe cel puțin un card

  @id:AC-1003 @priority:medium
  Scenario: Lista include cel puțin opt articole tehnice distincte
    Then sunt afișate cel puțin 8 articole pe pagină

  @id:AC-1004 @priority:medium
  Scenario: Navigarea către un articol funcționează
    When utilizatorul accesează link-ul articolului "Cum obții o ofertă de preț corectă pentru produse metalurgice"
    Then URL-ul devine "/blog/cum-obtii-o-oferta-de-pret-corecta-pentru-produse-metalurgice"
    And este vizibil un heading H1 cu textul "Cum obții o ofertă de preț corectă pentru produse metalurgice"
