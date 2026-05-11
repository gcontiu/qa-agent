Feature: Alcon Ind — Țevi Fără Sudură

  Background:
    Given utilizatorul accesează pagina produsului Țevi Fără Sudură la URL-ul /produse/tevi/tevi-fara-sudura

  @id:AC-500 @priority:high
  Scenario: Pagina Țevi Fără Sudură se încarcă cu titlul corect
    Then titlul paginii conține "Țevi Fără Sudură"
    And titlul paginii conține "Uz General, Cazane, Gaze și Petrol"
    And este vizibil un heading H1 cu textul "Țevi Fără Sudură"

  @id:AC-501 @priority:high
  Scenario: Tabelul cu specificații tehnice este afișat
    Then este vizibil heading-ul "Specificații tehnice"
    And este vizibil un tabel pe pagină

  @id:AC-502 @priority:medium
  Scenario: Sunt prezente secțiunile de utilizări și cerere ofertă
    Then este vizibil heading-ul "Utilizări și aplicații"
    And este vizibil heading-ul "Cerere ofertă de preț"
    And este vizibil un link "Cere Ofertă" către "/cerere-oferta"
