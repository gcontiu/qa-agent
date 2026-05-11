Feature: Alcon Ind — Contact

  Background:
    Given utilizatorul accesează pagina Contact la URL-ul /contact

  @id:AC-800 @priority:high
  Scenario: Pagina Contact se încarcă cu titlul corect
    Then titlul paginii conține "Contact"
    And titlul paginii conține "Alcon Ind"
    And este vizibil un heading H1 cu textul "Luați legătura cu noi"

  @id:AC-801 @priority:high
  Scenario: Adresa companiei este afișată
    Then este vizibil textul "Adresă"
    And este vizibil textul "Str. Infratirii nr. 28/15"
    And este vizibil textul "Târgu Mureș, județul Mureș"

  @id:AC-802 @priority:high
  Scenario: Numărul de telefon mobil/WhatsApp este afișat
    Then este vizibil textul "Mobil / WhatsApp"
    And există un link telefonic către "0745.593.587"

  @id:AC-803 @priority:medium
  Scenario: Programul de lucru este afișat
    Then este vizibil textul "Program"
    And este vizibil textul "Luni – Vineri: 08:00 – 17:00"
    And este vizibil textul "Sâmbătă – Duminică: Închis"

  @id:AC-804 @priority:medium
  Scenario: Linkul către Google Maps este disponibil
    Then este vizibil un link "Deschide în Google Maps" către "https://maps.google.com/?q=Str.+Infratirii+nr.+28%2F15+Targu+Mures"

  @id:AC-805 @priority:medium
  Scenario: Există un buton WhatsApp în secțiunea de contact
    Then este vizibil un link "Contactează-ne pe WhatsApp" către "https://wa.me/40745593587"

  @id:AC-806 @priority:medium
  Scenario: CTA-ul către cererea de ofertă online este vizibil
    Then este vizibil heading-ul "Preferați o ofertă online?"
    And este vizibil un link "Cerere Ofertă Online" către "/cerere-oferta"
