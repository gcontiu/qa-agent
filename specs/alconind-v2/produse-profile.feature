Feature: Alcon Ind — Categorie Profile Laminate la Cald

  Background:
    Given utilizatorul accesează pagina categoriei Profile Laminate la Cald la URL-ul /produse/profile-laminate-la-cald

  @id:AC-600 @priority:high
  Scenario: Pagina categoriei Profile se încarcă cu titlul corect
    Then titlul paginii conține "Profile Laminate la Cald"
    And este vizibil un heading H1 cu textul "Profile Laminate la Cald — Oțel Carbon și Aliat"

  @id:AC-601 @priority:high
  Scenario: Subcategoriile disponibile sunt afișate
    Then este vizibil heading-ul "Subcategorii disponibile"
    And este vizibil un heading "Profile Oțel Carbon"
    And este vizibil un heading "Profile Oțel Aliat"

  @id:AC-602 @priority:medium
  Scenario: Există secțiunea Aplicații frecvente
    Then este vizibil heading-ul "Aplicații frecvente"

  @id:AC-603 @priority:medium
  Scenario: Există secțiunea Cerere ofertă de preț
    Then este vizibil heading-ul "Cerere ofertă de preț"
    And este vizibil un link către "/cerere-oferta"
