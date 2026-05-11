Feature: Alcon Ind — Țevi Sudate

  Background:
    Given utilizatorul accesează pagina produsului Țevi Sudate la URL-ul /produse/tevi/tevi-sudate

  @id:AC-400 @priority:high
  Scenario: Pagina Țevi Sudate se încarcă cu titlul corect
    Then titlul paginii conține "Țevi Sudate"
    And este vizibil un heading H1 cu textul "Țevi Sudate"

  @id:AC-401 @priority:high
  Scenario: Breadcrumb-ul afișează ierarhia paginii
    Then breadcrumb-ul conține "Acasă"
    And breadcrumb-ul conține "Produse"
    And breadcrumb-ul conține "Țevi"
    And breadcrumb-ul conține "Țevi Sudate"

  @id:AC-402 @priority:high
  Scenario: Tabelul cu specificații tehnice este afișat
    Then este vizibil heading-ul "Specificații tehnice"
    And este vizibil un tabel pe pagină
    And tabelul conține rândul "Instalații negre/zincate" cu standardul "EN 10255 / EN 10240"
    And tabelul conține rândul "Construcții rotunde" cu dimensiunile "Ø 17.1 – 114 mm"
    And tabelul conține mențiunea mărcilor de oțel "S235, S275, S355"

  @id:AC-403 @priority:medium
  Scenario: Lista de utilizări și aplicații este vizibilă
    Then este vizibil heading-ul "Utilizări și aplicații"
    And este vizibil textul "Instalații de apă potabilă și caldă"
    And este vizibil textul "Rețele de gaze industriale"
    And este vizibil textul "Cadre și structuri metalice sudate"

  @id:AC-404 @priority:medium
  Scenario: Secțiunea de cerere ofertă afișează CTA-urile
    Then este vizibil heading-ul "Cerere ofertă de preț"
    And este vizibil mențiunea "Nu deținem stoc fix"
    And este vizibil un link "Cere Ofertă" către "/cerere-oferta"
    And este vizibil un link telefonic către "0745.593.587"
    And este vizibil un link WhatsApp către "https://wa.me/40745593587"

  @id:AC-405 @priority:low
  Scenario: Sunt afișate produse similare
    Then este vizibil heading-ul "Produse similare"
    And este vizibil un link "Țevi Fără Sudură" către "/produse/tevi/tevi-fara-sudura"
    And este vizibil un link "Profile Oțel Carbon" către "/produse/profile-laminate-la-cald/profile-otel-carbon"
