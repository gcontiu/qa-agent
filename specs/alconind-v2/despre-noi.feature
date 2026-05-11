Feature: Alcon Ind — Despre Noi

  Background:
    Given utilizatorul accesează pagina Despre Noi la URL-ul /despre-noi

  @id:AC-100 @priority:high
  Scenario: Pagina Despre Noi se încarcă cu titlul corect
    Then titlul paginii conține "Despre Noi"
    And titlul paginii conține "Alcon Ind"

  @id:AC-101 @priority:high
  Scenario: Eticheta și heading-ul principal sunt vizibile
    Then este vizibil textul "Despre Noi"
    And este vizibil un heading H1 care conține "Alcon Ind — Partenerul tău de încredere în produse metalurgice"

  @id:AC-102 @priority:medium
  Scenario: Sunt prezente paragrafele de prezentare a companiei
    Then conținutul paginii menționează "Târgu Mureș"
    And conținutul paginii menționează "produse metalurgice"
    And conținutul paginii menționează "intermediere"

  @id:AC-103 @priority:medium
  Scenario: Sunt afișate cele trei valori-cheie ale companiei
    Then este vizibil heading-ul "Experiență"
    And este vizibil textul "Peste 15 ani de activitate"
    And este vizibil heading-ul "Încredere"
    And este vizibil heading-ul "Rapiditate"
    And este vizibil textul "24 ore lucrătoare"

  @id:AC-104 @priority:high
  Scenario: Secțiunea Date de contact prezintă informațiile complete
    Then este vizibil heading-ul "Date de contact"
    And este vizibil textul "Str. Infratirii nr. 28/15, Târgu Mureș"
    And există un link telefonic către "0745.593.587"
    And este vizibil textul "Lun–Vin: 08:00–17:00"

  @id:AC-105 @priority:medium
  Scenario: CTA către cererea de ofertă este vizibil
    Then este vizibil un link "Solicită o ofertă de preț" către "/cerere-oferta"
