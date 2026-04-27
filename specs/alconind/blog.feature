Feature: Alcon Ind — Pagina Blog și Articole

  Background:
    Given utilizatorul accesează pagina de blog la URL-ul /blog

  @id:AC-500 @priority:high
  Scenario: Lista de articole recent publicate este vizibilă
    Then cel puțin o articol sau post de blog este vizibil pe pagină
    And fiecare articol afișează titlu și dată de publicare
    And o imagine miniatura sau preview al articolului este prezentă

  @id:AC-501 @priority:high
  Scenario: Detalii articol sunt accesibile prin click
    When utilizatorul apasă pe o articol din lista
    Then articolul se deschide și conținutul complet este vizibil
    And data publicării și autorul sunt afișate

  @id:AC-502 @priority:medium
  Scenario: Categoriile articolelor sunt filtrate
    Then o meniu lateral sau butoane de filtrare a categoriilor sunt vizibile
    And categoriile includ teme relevante industriei (inovație, durabilitate, etc.)
    And filtrarea reduce corect lista de articole

  @id:AC-503 @priority:medium
  Scenario: Funcție de căutare în blog
    Then un câmp de căutare este disponibil pe pagină
    And căutarea după cuvinte-cheie returnează articole relevante
    And mesaj "Nicio articol găsită" este afișat dacă nu există rezultate

  @id:AC-504 @priority:low
  Scenario: Opțiuni de partajare pe rețelele sociale
    Then butoane de Share pe Facebook, LinkedIn sunt vizibile la fiecare articol
    Then o opțiune de copiere a link-ului articolului este disponibilă
