bun, si daca sunt functionalitati care trebuie sa fie adaugate in features dar se intind pe mai multe      
  pagini ?                                                                                                   
                                                                                                             
⏺ Bună întrebare — atinge o limitare arhitecturală reală. Site-ul alconind are clar journeys cross-page      
  (browse Produse → categoria Țevi → "Cere Ofertă" → /cerere-oferta cu context), dar arhitectura actuală nu  
  le acoperă bine.                                                                                           
                                                                                                             
  Ce funcționează acum                                                                                       
   
  Gherkin SUPORTĂ scenarii multi-step:                                                                       
  @id:AC-700 @priority:high                                                                                  
  Scenario: Cere ofertă din pagina de produs                                                                 
    Given utilizatorul accesează /produse/tevi              
    When utilizatorul apasă butonul "Cere Ofertă"                                                            
    Then pagina /cerere-oferta se deschide       
    When utilizatorul completează numele și emailul                                                          
    And apasă butonul Trimite                                                                                
    Then mesajul de confirmare este afișat
                                                                                                             
  LLM-ul executor interpretează pașii ca free text, deci în principiu poate executa flow-urile.
                                                                                                             
  Ce NU funcționează bine
                                                                                                             
  Probleme arhitecturale concrete:                                                                           
  
  1. Parser-ul flatten-uiește steps: când există mai multe When/Then consecutive, parser-ul le concatenează  
  într-un singur string when și un singur string then. Se pierde ordinea — executorul nu mai știe că Then 1
  trebuie verificat după When 1, înainte de When 2.                                                          
  2. _user_message() în agent.py trimite doar 3 câmpuri (given/when/then) la executor, nu lista completă
  ordonată de pași. Modelul vede un mesaj agregat, fără secvență.                                            
  3. When-action guardrail verifică acțiunile la nivelul întregului when string. Dacă ai 2 When-uri,
  guardrail-ul caută orice acțiune în concatenarea lor — funcționează prin coincidență, nu by design.        
  4. Reporter afișează doar expected = then. Pentru un journey cu 3 pași și 3 verificări intermediare,
  raportul nu poate spune "am picat la pasul 2" — doar "Then conditions not met".                            
  5. Analyst-ul nu este instruit să caute cross-page journeys. Prompt-ul actual zice "one feature file per
  page" — opus-ul probabil va respecta și nu va genera niciun scenariu cross-page.                           
                                                            
  Soluție în 3 layere                                                                                        
                                                            
  Layer 1: Analyst prompt — instruiește detectarea de journeys                                               
                                                            
  Adaugă în analyst_system.md o secțiune nouă:                                                               
  - Identifică legături între pagini (CTA-uri care duc la alte pagini)
  - Pentru fiecare CTA semnificativ, întreabă: "ce face un user după click?"                                 
  - Scrie un fișier separat journeys.feature cu scenarii multi-step         
  - Exemple concrete pentru genul ăsta de site (B2B): browse → request quote, blog article → product, contact
   form → confirmation                                                                                       
                                                                                                             
  Layer 2: Spec parser — preservă secvența de pași                                                           
                                                                                                             
  În spec model adaugă steps: list[Step] unde Step = {kind: "given|when|then|and", text: str}. Păstrezi      
  given/when/then ca strings concatenate pentru backward compat (când-action guardrail), dar adaugi lista
  ordonată pentru executor.                                                                                  
                                                            
  Layer 3: Executor — trimite secvența la LLM

  În _user_message(), pe lângă Given/When/Then agregate, adaugă lista ordonată dacă există mai mult de un    
  singur When sau un singur Then:
  Step sequence (execute in order):                                                                          
    1. Given: utilizatorul accesează /produse/tevi          
    2. When:  utilizatorul apasă butonul "Cere Ofertă"                                                       
    3. Then:  pagina /cerere-oferta se deschide       
    4. When:  utilizatorul completează ...                                                                   
    5. ...                                                  
                                                                                                             
  LLM-ul interpretează secvența și execută pașii în ordine. La final raportează verdict global.
                                                                                                             
  Cost și complexitate                                      
                                                                                                             
  ┌────────────────────┬────────┬────────────────────────────────────────────────────────────┐
  │       Layer        │ Effort │                            Risk                            │
  ├────────────────────┼────────┼────────────────────────────────────────────────────────────┤
  │ 1 (analyst prompt) │ 30 min │ Low — doar text în prompt                                  │
  ├────────────────────┼────────┼────────────────────────────────────────────────────────────┤
  │ 2 (parser)         │ 1-2h   │ Medium — schemă schimbare, backward compat necesară        │               
  ├────────────────────┼────────┼────────────────────────────────────────────────────────────┤               
  │ 3 (executor)       │ 1h     │ Low — adaugă info în user message, nu schimbă control flow │               
  └────────────────────┴────────┴────────────────────────────────────────────────────────────┘               
                                                            
  Total: ~3-4h pentru implementare completă.                                                                 
                                                            
  Recomandare                                                                                                
                                                            
  Începe cu Layer 1 — cea mai mare valoare per effort. Vezi dacă Opus, cu prompt-ul updat, identifică        
  journeys reale pe alconind. Dacă da, și scrie journeys.feature valid, atunci layers 2-3 devin obligatorii
  pentru a-l executa corect.                                                                                 
                                                            
  Dacă Opus nu detectează journeys nici cu prompt explicit, atunci înseamnă că journeys nu sunt pe radar — și
   nu merită să mai investești în layers 2-3 înainte de a confirma că analyst-ul produce ceva util.
                                                                                                             
  Vrei să încep cu Layer 1 (prompt update)?  