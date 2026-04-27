Feature: Alcon Ind — Pagina Cerere Ofertă

  Background:
    Given utilizatorul accesează pagina de cerere ofertă la URL-ul /cerere-oferta

  @id:AC-400 @priority:high
  Scenario: Formular de cerere ofertă este complet și clar
    Then un formular cu título Cerere Ofertă este vizibil
    And câmpurile pentru Nume, Email, Telefon sunt prezente
    And un câmp pentru Descrierea Produsului este disponibil

  @id:AC-401 @priority:high
  Scenario: Selecție de tipuri de produse în formular
    Then o listă derulantă sau optiuni pentru Țevi este vizibilă
    And selecția pentru Profile Laminate este disponibilă
    And selecția pentru Tablă Metalică este disponibilă

  @id:AC-402 @priority:high
  Scenario: Câmp de cantitate și specificații tehnice
    Then un câmp pentru Cantitate (cu unitate de măsură) este prezent
    And un câmp text pentru Specificații Tehnice sau Note este disponibil
    And exemplu sau placeholder cu format așteptat este prezent

  @id:AC-403 @priority:medium
  Scenario: Opțiuni de livrare sunt oferite în formular
    Then o selecție pentru Modalitate de Livrare (livrare la sediu, ridicare) este vizibilă
    And un câmp pentru Data de Livrare Dorită este prezent
    And estimare de costuri sau timpi de livrare este menționată

  @id:AC-404 @priority:medium
  Scenario: Confirmarea și recomandare de contactare după trimitere
    When utilizatorul completează formularul și apasă butonul Trimite
    Then o confirmare că cererea a fost trimisă este afișată
    And informația că o echipă va contacta utilizatorul este prezentă
    And un email de confirmare sau referință comenzi este furnizat

  @id:AC-405 @priority:medium
  Scenario: Documentație descărcabilă pentru cerere ofertă
    Then un link pentru descărcarea unui șablon de cerere ofertă este vizibil
    And informații despre cum să completeze cererea sunt disponibile
    And formatul documentului este clar indicat (PDF, Excel, etc.)

  @id:AC-406 @priority:low
  Scenario: Chat live sau asistență în timp real
    Then o opțiune de contact live (chat, WhatsApp, Viber) este vizibilă
    Then o informație despre disponibilitate (ore de lucru) este prezentă pentru chat
