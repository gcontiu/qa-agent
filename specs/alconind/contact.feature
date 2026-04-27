Feature: Alcon Ind — Pagina Contact

  Background:
    Given utilizatorul accesează pagina de contact la URL-ul /contact

  @id:AC-300 @priority:high
  Scenario: Informații de contact principale sunt vizibile
    Then un număr de telefon este vizibil pe pagină
    And o adresă de email de contact este vizibilă
    And o adresă fizică (sediu) este prezentată

  @id:AC-301 @priority:high
  Scenario: Hartă cu locația sediului este afișată
    Then o hartă (embed Google Maps sau similar) este vizibilă pe pagină
    And marcatorii locației sau adresa sunt indicate pe hartă

  @id:AC-302 @priority:high
  Scenario: Formular de contact cu câmpuri esențiale
    Then un formular cu câmpul Nume este vizibil
    And un câmp Email este prezent
    And un câmp Mesaj este prezent
    And un buton Trimite sau Contact este vizibil

  @id:AC-303 @priority:medium
  Scenario: Ore de funcționare sunt listate
    Then horarul de lucru (luni-vineri, ore) este vizibil pe pagină
    And informația despre zilele de repaus este prezentă

  @id:AC-304 @priority:medium
  Scenario: Departamente cu contacte specifice sunt enumerate
    Then contacte pentru departamente (vânzări, suport tehnic, etc.) sunt vizibile
    And fiecare departament are o metodă de contact disponibilă

  @id:AC-305 @priority:low
  Scenario: Link de urmărire pe rețelele sociale este disponibil
    Then link-uri către profile de rețele sociale (LinkedIn, Facebook) sunt vizibile
    And link-urile sunt funcționale și deschid paginile corecte
