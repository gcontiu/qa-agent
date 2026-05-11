Feature: Alcon Ind — Articol Blog

  Background:
    Given utilizatorul accesează un articol de pe blog la URL-ul /blog/cum-obtii-o-oferta-de-pret-corecta-pentru-produse-metalurgice

  @id:AC-1100 @priority:high
  Scenario: Pagina articolului se încarcă cu titlul corect
    Then titlul paginii conține "Cum obții o ofertă de preț corectă pentru produse metalurgice"
    And titlul paginii conține "Alcon Ind"
    And este vizibil un heading H1 cu textul "Cum obții o ofertă de preț corectă pentru produse metalurgice"

  @id:AC-1101 @priority:high
  Scenario: Conținutul articolului este structurat pe secțiuni
    Then este vizibil heading-ul "De ce contează o cerere de ofertă bine pregătită"
    And este vizibil heading-ul "Ce informații trebuie incluse în cererea de ofertă"
    And este vizibil heading-ul "Greșeli frecvente care duc la oferte incorecte"
    And este vizibil heading-ul "Cum compari ofertele primite"

  @id:AC-1102 @priority:medium
  Scenario: Articolul detaliază punctele cheie ale cererii de ofertă
    Then este vizibil heading-ul "1. Tipul exact al produsului"
    And este vizibil heading-ul "2. Dimensiunile și toleranțele"
    And este vizibil heading-ul "3. Cantitatea solicitată"
    And este vizibil heading-ul "4. Termenul de livrare"

  @id:AC-1103 @priority:medium
  Scenario: Articolul include CTA către pagina de cerere ofertă
    Then este vizibil heading-ul "Contactați Alcon Ind pentru o ofertă personalizată"
    And este vizibil un link către "/cerere-oferta"

  @id:AC-1104 @priority:medium
  Scenario: Există un link înapoi către lista articolelor
    Then este vizibil un link către "/blog"

  @id:AC-1105 @priority:medium
  Scenario: La finalul articolului există CTA-ul standard
    Then este vizibil heading-ul "Aveți nevoie de produse metalurgice?"
