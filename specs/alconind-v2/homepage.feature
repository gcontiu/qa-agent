Feature: Alcon Ind — Pagina principală

  Background:
    Given utilizatorul accesează pagina principală la URL-ul /

  @id:AC-001 @priority:high
  Scenario: Pagina principală se încarcă cu titlul corect
    When pagina este încărcată
    Then titlul paginii conține "Alcon Ind"
    And titlul paginii conține "Produse Metalurgice"

  @id:AC-002 @priority:high
  Scenario: Bara superioară afișează datele de contact
    Then este vizibil textul "Str. Infratirii nr. 28/15, Târgu Mureș"
    And este vizibil textul "Lun–Vin: 08:00–17:00"
    And există un link telefonic către "0745.593.587"

  @id:AC-003 @priority:high
  Scenario: Header-ul afișează logo-ul și meniul principal
    Then este vizibil textul "Alcon Ind"
    And este vizibil un link "Acasă" către "/"
    And este vizibil un link "Despre Noi" către "/despre-noi"
    And este vizibil un link "Produse" către "/produse"
    And este vizibil un link "Blog" către "/blog"
    And este vizibil un link "Contact" către "/contact"
    And este vizibil un link "Cerere Ofertă" către "/cerere-oferta"

  @id:AC-004 @priority:high
  Scenario: Hero-ul afișează titlul principal și CTA-urile
    Then este vizibil un heading H1 care conține "Țevi, Profile"
    And este vizibil un heading H1 care conține "Tablă Metalică"
    And este vizibil un link "Cere o Ofertă Acum" către "/cerere-oferta"
    And este vizibil un link "Vezi Produsele" către "/produse"

  @id:AC-005 @priority:medium
  Scenario: Hero-ul afișează indicatorii cheie ai companiei
    Then este vizibil textul "15+" alături de "Ani experiență"
    And este vizibil textul "500+" alături de "Clienți mulțumiți"
    And este vizibil textul "24h" alături de "Timp răspuns ofertă"
    And este vizibil textul "100%" alături de "Produse certificate"

  @id:AC-006 @priority:high
  Scenario: Catalogul de produse afișează cele trei categorii principale
    Then este vizibil heading-ul "Ce Produse Comercializăm"
    And este vizibil un card "Țevi" cu link către "/produse/tevi"
    And este vizibil un card "Profile Laminate la Cald" cu link către "/produse/profile-laminate-la-cald"
    And este vizibil un card "Tablă Metalică" cu link către "/produse/tabla"

  @id:AC-007 @priority:medium
  Scenario: Secțiunea procesului prezintă cei 4 pași
    Then este vizibil heading-ul "Cum obții oferta ta în 4 pași simpli"
    And este vizibil pasul "1" cu titlul "Completezi formularul"
    And este vizibil pasul "2" cu titlul "Contactăm furnizorii"
    And este vizibil pasul "3" cu titlul "Primești oferta noastră"
    And este vizibil pasul "4" cu titlul "Livrăm la destinație"

  @id:AC-008 @priority:medium
  Scenario: Secțiunea avantaje afișează beneficiile cheie
    Then este vizibil heading-ul "De ce clienții aleg Alcon Ind"
    And este vizibil titlul "Acces la furnizori multipli"
    And este vizibil titlul "Produse certificate EN/ISO"
    And este vizibil titlul "Livrare în toată România"
    And este vizibil titlul "Răspuns în 24 de ore"

  @id:AC-009 @priority:medium
  Scenario: Secțiunea Blog afișează articole recente
    Then este vizibil heading-ul "Articole recente"
    And este vizibil un link către articolul "Cum obții o ofertă de preț corectă pentru produse metalurgice"
    And este vizibil un link către articolul "Țevi pentru instalații de gaze"
    And este vizibil un link "Toate articolele" către "/blog"

  @id:AC-010 @priority:medium
  Scenario: CTA final pentru cerere ofertă
    Then este vizibil heading-ul "Aveți nevoie de produse metalurgice?"
    And este vizibil un link "Cerere Ofertă Online" către "/cerere-oferta"
    And este vizibil un link telefonic "0745.593.587"

  @id:AC-011 @priority:low
  Scenario: Butonul flotant WhatsApp este disponibil
    Then există un link către "https://wa.me/40745593587"

  @id:AC-012 @priority:low
  Scenario: Footer-ul afișează coloanele cu produse, companie și cerere ofertă
    Then footer-ul conține heading-ul "Produse"
    And footer-ul conține heading-ul "Companie"
    And footer-ul conține heading-ul "Cerere Ofertă"
    And footer-ul conține textul "© 2026 Alcon Ind SRL"
