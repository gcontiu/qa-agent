Feature: Alcon Ind — Pagina Despre

  Background:
    Given utilizatorul accesează pagina de informații la URL-ul /despre

  @id:AC-200 @priority:high
  Scenario: Pagina Despre conține istoricul companiei
    Then o descriere a istoricului sau misiunii companiei este vizibilă pe pagină
    And mențiunea anului de înființare sau a experienței companiei este vizibilă

  @id:AC-201 @priority:high
  Scenario: Valori și principii ale companiei sunt prezentate
    Then o referință la valorile companiei (calitate, inovație, etc.) este vizibilă
    And o declarație de principii sau angajamente este prezentă

  @id:AC-202 @priority:high
  Scenario: Echipa de conducere este prezentată cu detalii de contact
    Then cel puțin o fotografie sau nume de persoană din echipă este vizibil
    And o metodă de contact pentru o persoană din echipă este disponibilă

  @id:AC-203 @priority:medium
  Scenario: Certificări și acreditări sunt listate pe pagină
    Then o referință la ISO, CE, sau alte certificări este vizibilă
    And mențiuni de standarde de calitate sunt prezente

  @id:AC-204 @priority:medium
  Scenario: Parteneri strategici sunt menționați
    Then o listă sau referință la parteneri comerciali este vizibilă
    And logos de parteneri sunt prezentați pe pagină

  @id:AC-205 @priority:low
  Scenario: Descărcarea raportului de sustenabilitate este disponibilă
    Then un link pentru descărcarea unui raport anual sau document de sustenabilitate este vizibil
    And formatul documentului (PDF) este clar indicat
