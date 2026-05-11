Feature: Alcon Ind — Cerere Ofertă

  Background:
    Given utilizatorul accesează pagina Cerere Ofertă la URL-ul /cerere-oferta

  @id:AC-900 @priority:high
  Scenario: Pagina Cerere Ofertă se încarcă cu titlul corect
    Then titlul paginii conține "Cerere Ofertă Produse Metalurgice"
    And este vizibil un heading H1 cu textul "Solicită o ofertă de preț personalizată"

  @id:AC-901 @priority:medium
  Scenario: Sunt afișate avantajele cererii de ofertă
    Then este vizibil textul "Fără obligații"
    And este vizibil textul "Răspuns rapid"
    And este vizibil textul "Prețuri competitive"
    And este vizibil textul "Livrare organizată"

  @id:AC-902 @priority:medium
  Scenario: Sunt afișate alternativele de contact direct
    Then este vizibil textul "Preferi să suni direct?"
    And este vizibil un link telefonic către "0745.593.587"
    And este vizibil un link "WhatsApp" către "https://wa.me/40745593587"

  @id:AC-903 @priority:high
  Scenario: Formularul afișează câmpurile de identificare
    Then este vizibil heading-ul "Cerere de Ofertă"
    And este vizibil un câmp "Nume și Prenume" marcat ca obligatoriu
    And este vizibil un câmp "Telefon" marcat ca obligatoriu
    And este vizibil un câmp "Firmă" marcat ca obligatoriu
    And este vizibil un câmp "Email"

  @id:AC-904 @priority:high
  Scenario: Formularul afișează câmpurile de detaliere a cererii
    Then este vizibil un câmp "Localitate" marcat ca obligatoriu
    And este vizibil eticheta "Categorie produs" marcată ca obligatorie
    And este vizibil butonul de selecție "Țevi"
    And este vizibil butonul de selecție "Profile Laminate la Cald"
    And este vizibil butonul de selecție "Tablă"
    And este vizibil butonul de selecție "Nu știu / Altele"
    And este vizibil un câmp "Descrieți cererea dvs." marcat ca obligatoriu

  @id:AC-905 @priority:high
  Scenario: Butonul de trimitere și nota GDPR sunt vizibile
    Then este vizibil butonul "Trimite Cererea de Ofertă"
    And este vizibil textul "Datele dvs. sunt confidențiale și nu vor fi transmise terților"

  @id:AC-906 @priority:medium
  Scenario: Selectarea unei categorii de produs activează opțiunea respectivă
    When utilizatorul apasă butonul "Țevi"
    Then categoria "Țevi" este marcată ca selectată

  @id:AC-907 @priority:high
  Scenario: Trimiterea formularului fără câmpurile obligatorii nu este permisă
    When utilizatorul apasă butonul "Trimite Cererea de Ofertă" fără a completa câmpurile obligatorii
    Then formularul nu este trimis
    And browser-ul afișează validarea pentru câmpurile obligatorii

  @id:AC-908 @priority:medium
  Scenario: Câmpurile obligatorii sunt indicate cu asterisc
    Then eticheta "Nume și Prenume" conține caracterul "*"
    And eticheta "Telefon" conține caracterul "*"
    And eticheta "Firmă" conține caracterul "*"
    And eticheta "Localitate" conține caracterul "*"
    And eticheta "Categorie produs" conține caracterul "*"
    And eticheta "Descrieți cererea dvs." conține caracterul "*"
