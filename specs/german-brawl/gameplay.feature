Feature: German Brawl — Core Gameplay

  @id:GB-001 @priority:high
  Scenario: Clicking PLAY leaves the lobby and starts the battle flow
    Given the lobby is loaded
    When the player clicks the PLAY button
    Then the lobby main screen is no longer shown
    And a queue indicator, countdown timer, or battle screen element is visible

  @id:GB-002 @priority:high
  Scenario: Lobby displays all required navigation buttons
    Given the app is loaded
    Then the Shop button is visible
    And the Brawlers button is visible
    And the GAMEMODES button is visible
    And the PLAY button is visible
    And the Quest button is visible
    And the Brawl Pass progress bar is visible

  @id:GB-003 @priority:high
  Scenario: Battle screen shows a word to translate and an input field
    Given the lobby is loaded
    When the player clicks the PLAY button and waits for the battle to begin
    Then a word or phrase is visible on screen for translation
    And a text input field is present for typing the answer

  @id:GB-004 @priority:medium
  Scenario: Resource counters are displayed in the lobby
    Given the app is loaded
    Then the Coins counter is visible
    And the Gems counter is visible

  @id:GB-005 @priority:medium
  Scenario: GAMEMODES button shows all available battle modes
    Given the lobby is loaded
    When the player clicks the GAMEMODES button
    Then the game mode options are shown
    And DE to RO mode option is visible
    And RO to DE mode option is visible

  @id:GB-006 @priority:low
  Scenario: Daily Reward button is visible in lobby
    Given the app is loaded
    Then a Daily Reward button or notification is visible in the lobby
