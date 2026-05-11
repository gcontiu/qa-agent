Feature: Alcon Ind — Catalog Produse

  Background:
    Given utilizatorul accesează pagina Produse la URL-ul /produse

  @id:AC-200 @priority:high
  Scenario: Pagina Produse se încarcă cu titlul corect
    Then titlul paginii conține "Produse Metalurgice"
    And este vizibil un heading H1 cu textul "Produse Metalurgice"

  @id:AC-201 @priority:high
  Scenario: Categoria Țevi este afișată cu subcategoriile sale
    Then este vizibil un heading H2 "Țevi"
    And este vizibil un link către "/produse/tevi/tevi-sudate" cu titlul "Țevi Sudate"
    And este vizibil un link către "/produse/tevi/tevi-fara-sudura" cu titlul "Țevi Fără Sudură"
    And este vizibil un link "Cere ofertă pentru Țevi" către "/cerere-oferta"

  @id:AC-202 @priority:high
  Scenario: Categoria Profile Laminate la Cald este afișată cu subcategoriile sale
    Then este vizibil un heading H2 "Profile Laminate la Cald"
    And este vizibil un link către "/produse/profile-laminate-la-cald/profile-otel-carbon" cu titlul "Profile Oțel Carbon"
    And este vizibil un link către "/produse/profile-laminate-la-cald/profile-otel-aliat" cu titlul "Profile Oțel Aliat"
    And este vizibil un link "Cere ofertă pentru Profile Laminate la Cald" către "/cerere-oferta"

  @id:AC-203 @priority:high
  Scenario: Categoria Tablă Metalică este afișată cu cele patru subcategorii
    Then este vizibil un heading H2 "Tablă Metalică"
    And este vizibil un link către "/produse/tabla/tabla-subtire-mijlocie-groasa" cu titlul "Tablă Subțire, Medie și Groasă"
    And este vizibil un link către "/produse/tabla/tabla-zincata" cu titlul "Tablă Zincată"
    And este vizibil un link către "/produse/tabla/tabla-striata" cu titlul "Tablă Striată"
    And este vizibil un link către "/produse/tabla/tabla-cutata" cu titlul "Tablă Cutată"
    And este vizibil un link "Cere ofertă pentru Tablă Metalică" către "/cerere-oferta"

  @id:AC-204 @priority:medium
  Scenario: Descrierea fiecărei categorii principale este vizibilă
    Then descrierea categoriei Țevi menționează "sudate și fără sudură"
    And descrierea categoriei Profile menționează "oțel carbon și oțel aliat"
    And descrierea categoriei Tablă menționează "subțire, medie, groasă, zincată, striată și cutată"
