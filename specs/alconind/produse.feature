Feature: Alcon Ind — Pagina Produse

  Background:
    Given utilizatorul accesează pagina de produse la URL-ul /produse

  @id:AC-100 @priority:high
  Scenario: Pagina Produse afișează toate cele trei categorii principale
    Then categoria Țevi este vizibilă pe pagină
    And categoria Profile Laminate la Cald este vizibilă pe pagină
    And categoria Tablă Metalică este vizibilă pe pagină

  @id:AC-101 @priority:high
  Scenario: Categoria Țevi listează subcategoriile Sudate și Fără Sudură
    Then o referință la Țevi Sudate este vizibilă
    And o referință la Țevi Fără Sudură este vizibilă

  @id:AC-102 @priority:high
  Scenario: Categoria Profile listează subcategoriile Oțel Carbon și Oțel Aliat
    Then o referință la Profile Oțel Carbon este vizibilă
    And o referință la Profile Oțel Aliat este vizibilă

  @id:AC-103 @priority:high
  Scenario: Categoria Tablă listează toate cele patru variante
    Then o referință la Tablă Subțire, Medie sau Groasă este vizibilă
    And o referință la Tablă Zincată este vizibilă
    And o referință la Tablă Striată este vizibilă
    And o referință la Tablă Cutată este vizibilă

  @id:AC-104 @priority:medium
  Scenario: Fiecare categorie afișează un link sau buton de detalii
    Then cel puțin un link sau buton cu textul Detalii este vizibil pe pagină

  @id:AC-105 @priority:medium
  Scenario: Pagina conține butoane Cere Ofertă pentru fiecare categorie
    Then cel puțin un buton sau link cu textul Cere ofertă este vizibil pe pagină

  @id:AC-106 @priority:medium
  Scenario: Specificații tehnice cu standarde EN sunt menționate pe pagină
    Then o referință la un standard EN sau la dimensiuni tehnice este vizibilă

  @id:AC-107 @priority:low
  Scenario: Pagina de detaliu pentru Țevi Sudate este accesibilă
    When utilizatorul apasă pe linkul Detalii din secțiunea Țevi Sudate
    Then o pagină dedicată produsului Țevi Sudate se deschide
    And o descriere extinsă sau specificații tehnice sunt vizibile
