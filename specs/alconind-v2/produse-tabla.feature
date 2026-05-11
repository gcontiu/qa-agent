Feature: Alcon Ind — Categorie Tablă Metalică

  Background:
    Given utilizatorul accesează pagina categoriei Tablă la URL-ul /produse/tabla

  @id:AC-700 @priority:high
  Scenario: Pagina categoriei Tablă se încarcă cu titlul corect
    Then titlul paginii conține "Tablă Metalică"
    And este vizibil un heading H1 cu textul "Tablă Metalică — Toate Tipurile și Grosimile"

  @id:AC-701 @priority:high
  Scenario: Tipurile de tablă disponibile sunt afișate
    Then este vizibil heading-ul "Tipuri de tablă disponibile"
    And este vizibil un heading "Tablă Subțire, Medie și Groasă"
    And este vizibil un heading "Tablă Zincată"
    And este vizibil un heading "Tablă Striată"
    And este vizibil un heading "Tablă Cutată"

  @id:AC-702 @priority:medium
  Scenario: Există secțiunea Aplicații frecvente
    Then este vizibil heading-ul "Aplicații frecvente"

  @id:AC-703 @priority:medium
  Scenario: Există secțiunea Cerere ofertă de preț
    Then este vizibil heading-ul "Cerere ofertă de preț"
    And este vizibil un link către "/cerere-oferta"
