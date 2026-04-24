Feature: German Brawl — Core Gameplay

  @id:GB-001 @priority:high
  Scenario: PLAY button starts a battle with a visible timer
    Given the lobby is loaded with Shelly visible
    When the player clicks the PLAY button
    Then the battle screen appears with a countdown timer visible

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
  Scenario: Battle presents a word and an input field for translation
    Given the lobby is loaded
    When the player clicks the PLAY button
    Then a word is displayed on the battle screen for translation
    And a text input field is available for the answer

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
