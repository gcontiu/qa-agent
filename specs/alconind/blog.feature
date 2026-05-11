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

