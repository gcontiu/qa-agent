Feature: Alcon Ind — Categorie Țevi

  Background:
    Given utilizatorul accesează pagina categoriei Țevi la URL-ul /produse/tevi

  @id:AC-300 @priority:high
  Scenario: Pagina categoriei Țevi se încarcă cu titlul corect
    Then titlul paginii conține "Țevi Metalice"
    And este vizibil un heading H1 cu textul "Țevi Metalice — Sudate și Fără Sudură"

  @id:AC-301 @priority:high
  Scenario: Breadcrumb-ul este vizibil
    Then este vizibil un link "Acasă" către "/"
    And este vizibil un link "Produse" către "/produse"

  @id:AC-302 @priority:high
  Scenario: Subcategoriile disponibile sunt afișate
    Then este vizibil heading-ul "Subcategorii disponibile"
    And este vizibil un link către "/produse/tevi/tevi-sudate" cu titlul "Țevi Sudate"
    And este vizibil un link către "/produse/tevi/tevi-fara-sudura" cu titlul "Țevi Fără Sudură"

  @id:AC-303 @priority:medium
  Scenario: Secțiunea Aplicații frecvente este vizibilă
    Then este vizibil heading-ul "Aplicații frecvente"

  @id:AC-304 @priority:medium
  Scenario: Secțiunea Cerere ofertă include CTA-uri de contact
    Then este vizibil heading-ul "Cerere ofertă de preț"
    And este vizibil un link "Cere Ofertă" către "/cerere-oferta"
    And este vizibil un link telefonic către "0745.593.587"
    And este vizibil un link WhatsApp către "https://wa.me/40745593587"

  @id:AC-305 @priority:low
  Scenario: Sunt afișate categoriile conexe
    Then este vizibil heading-ul "Categorii conexe"
    And este vizibil un link "Profile Laminate la Cald" către "/produse/profile-laminate-la-cald"
    And este vizibil un link "Tablă Metalică" către "/produse/tabla"
